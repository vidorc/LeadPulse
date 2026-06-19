# LeadPulse — Architecture

LeadPulse is a multi-tenant lead-automation and revenue-recovery backend. It
captures leads, qualifies them with an LLM, routes them, drives follow-up
sequences, and — its defining feature — detects *revenue leaks*: deals and
contacts that are silently going cold because an expected action never happened.

This document explains the system shape, the cross-cutting invariants
(tenancy, authorization), the workflow-engine substrate that makes the async
behavior durable, and the leak-detection thesis the product is built around.

---

## System overview

```
                         ┌─────────────────────────┐
                         │   React + Vite frontend  │
                         │      (frontend/)         │
                         └────────────┬────────────┘
                                      │ HTTPS  (Bearer JWT)
                                      ▼
        ┌──────────────────────────────────────────────────────────┐
        │                  FastAPI app  (app/main.py)                │
        │  CORS · /api/v1 routers · /health/*                        │
        │  ┌──────────────────────────────────────────────────────┐ │
        │  │ 4-stage authz pipeline  (app/api/deps.py)             │ │
        │  │  authenticate → resolve tenant → scope → authorize    │ │
        │  └──────────────────────────────────────────────────────┘ │
        │  routes: auth · leads · opportunities · follow-ups · leak  │
        └───────────────┬───────────────────────────┬───────────────┘
                        │ TenantContext             │
                        ▼                            ▼
        ┌───────────────────────────┐   ┌──────────────────────────────┐
        │  Services (domain logic)  │   │  Tenant-scoped repositories   │
        │  auth · opportunity ·     │   │  (app/db/repository.py)       │
        │  followup · leak_detection│   │  every query filtered by      │
        │  routing · ingestion ·    │   │  org_id; soft-delete aware    │
        │  timeline · scheduler ·   │   └───────────────┬──────────────┘
        │  outbox                   │                   │
        └───────┬───────────┬───────┘                   │
                │           │                           ▼
                │           │                ┌────────────────────────┐
                │           └───────────────▶│   PostgreSQL 15        │
                │  enqueue (same txn)         │  leads · opps · events │
                │                             │  outbox · scheduled_   │
                ▼                             │  jobs · sla_policies   │
        ┌────────────────────┐               │  leak_alerts · ...     │
        │  Redis 7           │◀──────────────┤  (system of record)    │
        │  Celery broker +   │  results      └────────────────────────┘
        │  result backend +  │                           ▲
        │  rate-limit store  │                           │
        └─────────┬──────────┘                           │
                  │                                       │
        ┌─────────┴───────────┐   ┌─────────────────────┐│
        │  Celery worker      │   │  Celery beat        ││
        │  process_lead_ai    │   │  every  60s: dispatch_scheduled_jobs
        │  scheduled-job      │   │  every  30s: relay_outbox
        │  handlers           │   │  every 300s: scan_leaks
        │  outbox delivery    │   └──────────┬──────────┘│
        └─────────────────────┘              │           │
                  │  Groq LLM / SMTP / webhook            │
                  └───────────────────────────────────────┘
```

Two planes:

- **Synchronous plane** — the FastAPI app handles requests, runs the authz
  pipeline, and performs reads/writes through tenant-scoped repositories and
  services. Anything paid or slow (LLM qualification) is offloaded, not done
  inline.
- **Asynchronous plane** — Celery workers execute background work; Celery beat
  emits the periodic heartbeat. The async plane has no HTTP principal, so it
  carries tenant scope explicitly via each job's `org_id`.

---

## Multi-tenancy: `org_id` everywhere

Every business row carries an `org_id` foreign key to `organizations`
(`ON DELETE CASCADE`). Tenancy is enforced in depth:

1. **The principal carries the tenant.** `TenantContext`
   (`app/core/tenant.py`) is an immutable, per-request value object holding
   `org_id`, `user_id`, `email`, and `role`. It is built once by the authz
   pipeline and threaded explicitly into services and repositories — no service
   or query runs "unscoped".

2. **Repositories cannot forget the scope.** `TenantRepository`
   (`app/db/repository.py`) is the sanctioned read/write path. Its
   `scoped_query()` always injects `org_id == ctx.org_id` and excludes
   soft-deleted rows; `get()` returns `None` for a row that exists but belongs
   to another tenant (no cross-tenant disclosure); `add()` forces the new row's
   `org_id` to the caller's scope. A query that forgets the tenant filter is
   simply not expressible through this base.

3. **Cross-entity lookups re-check ownership.** Where code fetches by raw id
   (e.g. proposals, meetings, alerts), it verifies `obj.org_id == ctx.org_id`
   before acting and raises 404 otherwise.

This closes the classic IDOR / "every user sees all leads" failure mode at the
data-access layer rather than relying on every handler to remember a `WHERE`
clause.

---

## The 4-stage authorization pipeline

Every protected request flows through `app/api/deps.py` in four stages. No
protected endpoint may skip stages 2–4.

```
  1. authenticate    decode_token(): verify JWT signature + expiry,
                     require token "type" == "access", extract sub + org_id

  2. resolve tenant  load the User from the DB and reject if inactive/deleted;
                     load the active Membership for (user, org) from the DB —
                     NOT from token claims. No membership → 403.

  3. scope           build the immutable TenantContext (org_id, user_id,
                     email, role) from the DB-resolved values

  4. authorize       require_role(minimum) gates by role rank; below the
                     minimum raises 403
```

The critical design choice: **roles and active-state are resolved from the
database on every request, not trusted from the token.** Access tokens
deliberately do *not* carry the role. A deactivated user or a demoted member is
rejected immediately, not at token expiry. Refresh tokens are persisted by
`jti` and are server-side revocable, so logout and rotation take effect at once.

Roles are ranked `OWNER (4) > ADMIN (3) > MANAGER (2) > AGENT (1)`
(`app/core/enums.py`). `require_manager` and `require_admin` are the gate
factories; for example, creating SLA policies, follow-up sequences, lead
overrides, and on-demand scans require manager-or-above.

---

## The workflow-engine substrate

Three durable primitives, all in PostgreSQL, make the async behavior reliable.
They are the foundation the follow-up engine and leak detection are built on.

### 1. Timeline events (immutable log)

`app/services/timeline.py` + the `events` table. Every meaningful state change
appends an immutable `Event(org_id, entity_type, entity_id, event_type,
payload, actor, occurred_at)`. Events are appended **within the caller's
transaction** (flush, not commit), so an event lands atomically with the state
change it records — there is no window where state moved but the timeline
didn't. `latest_event_at(...)` is the primitive leak detection uses to ask "has
any transition happened within the window?".

### 2. Durable scheduler (ScheduledJob)

`app/services/scheduler.py` + the `scheduled_jobs` table. Unlike Celery's `eta`
(opaque, un-queryable, un-cancellable), a `ScheduledJob` is a row: queryable,
cancellable, and auditable. `schedule()` writes a `PENDING` job with a `run_at`.
Beat's `dispatch_scheduled_jobs` calls `dispatch_due()`, which claims due jobs
with `FOR UPDATE SKIP LOCKED` (so multiple workers never double-execute), marks
them `RUNNING`, runs the registered handler for the job's `job_type`, and
records `DONE`/`FAILED` per job in its own committed unit. Domains register
handlers at import time (the follow-up engine registers `followup_step`).
`cancel_for_entity()` flips pending jobs to `CANCELLED` — which is exactly how a
follow-up sequence is stopped the moment a rep engages a lead.

### 3. Transactional outbox

`app/services/outbox_service.py` + the `outbox` table. Side effects
(emails, webhooks, in-app notifications) are never sent inline. Producers
`enqueue()` a row **in the same transaction** as the state change, with a
`dedupe_key` and an `ON CONFLICT DO NOTHING` on `(org_id, dedupe_key)` — so the
same logical notification is written at most once even if the producing task
retries. Beat's `relay_outbox` calls `relay_pending()`, which claims due rows
(`FOR UPDATE SKIP LOCKED`), delivers via the channel adapter, and marks `SENT`
or schedules an exponential-backoff retry, dead-lettering after `max_attempts`.

Together these give the lead pipeline **exactly-once-effect** semantics: state,
timeline events, and the outbox enqueue all commit in one transaction; delivery
happens later via the relay, so a task retry can never double-send.

---

## Revenue Leak Detection: the thesis

The product's headline claim is that revenue leaks out of a pipeline not through
dramatic failures but through *absence* — a lead nobody contacted, a deal that
stopped moving, a meeting that quietly passed, a proposal that was sent and then
forgotten. LeadPulse reframes this as a precise, queryable idea:

> **Leak detection is transition-absence detection over the timeline + entity
> state, and SLA policies are data.**

`app/services/leak_detection.py` realizes it. An `SLAPolicy` row is configuration
stored in the database: a `(leak_type, threshold_hours, severity, is_active,
notify)` tuple, one per leak type per org. The scanner reads each active policy
and finds the entities breaching its window:

| Leak type | Breach condition |
|-----------|------------------|
| `LEAD_IGNORED` | a lead created more than `threshold_hours` ago, still in an uncontacted status (`new`/`qualifying`/`qualified`/`manual_review`) |
| `OPP_STALLED` | an opportunity whose `stage_changed_at` is older than the window and is not in a terminal stage (`won`/`lost`) |
| `MEETING_MISSED` | a meeting whose `scheduled_at` has passed (threshold can be 0) and is still `scheduled` (not completed/cancelled) |
| `PROPOSAL_COLD` | a `sent` proposal past the window with no `PROPOSAL_FOLLOWUP` timeline event since it was sent |

Because policies are data, an org tunes its own definition of "too slow" without
a code change. When a breach is found, the scanner raises a `LeakAlert`
**idempotently** — a unique constraint ensures one OPEN alert per
`(org, leak_type, entity_type, entity_id, status)`, so a leak that persists
across scans does not spam duplicate alerts. It also appends a `LEAK_DETECTED`
timeline event and, if the policy says `notify`, enqueues an in-app outbox
notification (deduped by `leak:{type}:{entity}:{id}`).

The scanner runs every 5 minutes via beat (SLA windows are hours/days, so a
5-minute resolution is ample) and can also be triggered on demand by a manager
via `POST /api/v1/leak-detection/scan`. It is org-agnostic at the top: it
iterates active policies across all tenants, each carrying its own `org_id`.

This is why the substrate matters. Leak detection is only trustworthy if the
timeline is complete and atomic — every stage change, send, schedule, and
completion stamps a first-class timestamp and emits an event in the same
transaction (`opportunity_service.py`), giving the scanner authoritative data to
query against.

---

## Request lifecycle (example: create a lead)

1. `POST /api/v1/leads/` arrives with a `Bearer` access token.
2. The authz pipeline authenticates the token, resolves the user + active
   membership from the DB, builds the `TenantContext`, and (for this endpoint)
   requires a valid member.
3. The handler creates a `Lead` through `LeadRepository.add()`, which forces
   `org_id = ctx.org_id`, and commits.
4. It dispatches `process_lead_ai.delay(lead.id, ctx.org_id)` — paid LLM work is
   offloaded to the async plane, tenant-scoped by the passed `org_id`.
5. A Celery worker runs `process_lead_ai`: it is idempotent (a processed lead is
   skipped), validates raw LLM output through `QualificationContract`
   (bounded score, coerced enums), updates lead state, appends timeline events,
   and — if the decision is a hot lead — enqueues an outbox notification, all in
   **one** transaction.
6. Beat's `relay_outbox` later delivers the notification; beat's `scan_leaks`
   later evaluates SLA policies against the lead's timeline.

---

## Why these choices

- **DB-backed authz, role-not-in-token.** Security state must be revocable
  immediately. Trusting token claims for role/active-state means a 15-minute
  window where a fired employee still has access. Re-resolving from the DB
  closes it; the short access token + revocable refresh token keep the cost low.
- **Repository-enforced tenancy.** Per-handler `WHERE org_id = ...` is a single
  forgotten clause away from a cross-tenant breach. Making the scope structural
  (you cannot build an unscoped query) removes a whole bug class.
- **Outbox + durable scheduler instead of inline effects / Celery eta.** Inline
  emails inside a transaction either send-then-fail-to-commit or
  commit-then-fail-to-send. The outbox makes effects part of the transaction and
  delivery a separate, retryable, deduplicated step. `ScheduledJob` rows are
  cancellable and queryable where `eta` is neither — essential for stopping a
  follow-up sequence mid-flight.
- **Immutable timeline as the source of truth for "what happened when."** Leak
  detection, audit, and the per-entity history view all read the same append-only
  log, so they can never disagree.
- **Leak policies as data.** The product's value is that each org defines its own
  SLAs. Encoding them as rows (not code) makes that self-serve and per-tenant.
- **Two-plane split.** A paid, latency-variable LLM call must never block an HTTP
  request or a DB transaction. Offloading to Celery keeps the API fast and makes
  qualification retryable in isolation.
