# LeadPulse — Architecture Review (Phase 2)

**Date:** 2026-05-31
**Author:** Founding CTO / Principal Architect
**Inputs:** `AUDIT_REPORT.md` (Phase 1)
**Status:** Review only. No implementation. No refactoring.
**Horizon:** Decisions are made for a 3-year maintenance window, optimizing for a small team shipping fast without painting itself into a corner.

---

## 0. The Thesis (read this first)

Every downstream decision in this document follows from one observation:

> **LeadPulse is not a CRM. It is a temporal SLA engine.**

A CRM stores the *current state* of leads. LeadPulse's entire value proposition — "Revenue Leak Detection + Follow-Up Intelligence" — is about the **absence of expected state transitions within a time window**:

| Product feature | Restated as a temporal SLA |
|---|---|
| "Lead ignored too long" | No *contact* transition within N hours of *created* |
| "Opportunity stalled" | No *stage change* within N days of last stage change |
| "Meeting missed" | A *meeting* whose scheduled time passed with no *completed* transition |
| "Proposal not followed up" | No *follow-up* event within N days of *proposal sent* |

These are **the same primitive**: a timestamped expectation that a transition occurs, plus a scanner that fires when it doesn't. If the architecture treats this as a first-class concern — an immutable event timeline + durable scheduled expectations + an SLA scanner — then leak detection and the follow-up engine are *the same subsystem viewed from two angles* (one watches for absence, one schedules presence). If we don't, we will rebuild this logic ad hoc in five places and the product's headline feature will be fragile.

The current codebase treats leads as mutable rows with magic-string statuses. That is a CRM shape, and it is the central architectural mismatch.

---

## 1. Current Architecture Review

### 1.1 What we have today

```
                 ┌─────────────────────────────────────────────┐
                 │  Browser (React 19 / JSX, bespoke CSS)        │
                 │  Login · Dashboard · ReviewQueue · LeadDetail │
                 └───────────────┬─────────────────────────────┘
                                 │ axios + Bearer (localStorage)
                                 ▼
       ┌───────────────────────────────────────────────────────┐
       │  FastAPI (single sync uvicorn process)                 │
       │   /auth/login     (JWT, SHA-256 hash, hardcoded key)   │
       │   POST /leads     (PUBLIC, unauth — triggers paid AI)  │
       │   GET  /leads     (db.query(Lead).all() — no scoping)  │
       │   /metrics, /review-queue ×3, /dashboard/summary ×3    │
       └───────┬───────────────────────────────┬───────────────┘
               │ .delay(lead.id)                │ sync ORM
               ▼                                ▼
       ┌───────────────┐               ┌──────────────────┐
       │ Celery worker │               │  PostgreSQL 15   │
       │ process_lead_ai│──────────────│  users / leads / │
       │  → Groq LLM    │   (no Alembic)│  lead_events     │
       │  → score/route │               └──────────────────┘
       │  → email/webhook (BEFORE commit)│
       └───────┬───────┘
               │ broker + result backend
               ▼
       ┌───────────────┐   ┌───────────────┐
       │   Redis 7     │   │ celery_beat   │ ← runs, but schedules NOTHING
       └───────────────┘   └───────────────┘
```

### 1.2 Honest assessment of the current architecture

**The one thing that is architecturally right:** the async-offload pattern. `POST /leads` persists synchronously and offloads the slow, paid LLM work to Celery (`leads.py:38`). For an external-AI dependency that is the correct instinct, and it's the seed we build on.

**Everything structural around it is a prototype, not a system:**

- **No tenancy plane.** `db.query(Lead).all()` returns every lead to every authenticated user. There is no `org_id` anywhere. This isn't a bug to patch; it's a missing architectural dimension.
- **The domain is modeled as mutable rows with string statuses,** not as a timeline of transitions — directly contradicting the product thesis (§0).
- **The async pipeline is not transactionally safe.** Side effects (email/webhook) fire *before* `db.commit()` under `autoretry_for=(Exception,)`, so retries duplicate them. The system has no notion of "exactly-once side effect."
- **Configuration and trust are split.** Secrets live half in `.env`/`Settings` and half hardcoded in `.py` files. The JWT key is a constant. There is no single trust root.
- **The repository does not represent the running app** (99.5% committed `.venv`, real source untracked). This is a process/architecture-hygiene failure that blocks everything else.

**Net:** the current system is a single-tenant, single-channel, happy-path demo of lead qualification. It validates the *idea* of an AI qualification pipeline. It does not contain the architecture for the product that was described.

---

## 2. Architectural Bottlenecks

Ranked by how hard they cap the product, not by code size.

### 🔴 Critical

1. **No tenancy plane.** Multi-tenancy is the most expensive thing to retrofit because it touches every table, every query, and every authorization check. Decided late, it forces a full schema rewrite + data backfill. **This must be settled before any feature work.**
2. **Leads modeled as mutable state, not as a transition timeline.** Leak detection has nothing to measure against — there is no `updated_at`, no stage-change history, no SLA concept. The headline feature is architecturally unsupported.
3. **Scheduling is non-durable and undefined.** The follow-up engine (Day 1/3/7/14) and leak scanners both require *durable, cancellable, rescheduleable* time-based work. `celery_beat` runs but schedules nothing, and naïve Celery `eta`/`countdown` tasks are lost on broker flush and can't be queried, cancelled, or audited. There is no scheduling substrate.
4. **The paid-AI endpoint is public and unthrottled.** `POST /leads` → `process_lead_ai.delay()` means anonymous traffic drives Groq spend with no ceiling. This is both a security hole (§8) and a hard scalability/cost bottleneck.

### 🟠 Important

5. **Single sync uvicorn process on a synchronous SQLAlchemy stack.** Concurrency is capped by one process; blocking DB calls hold the event loop. Fine for a demo, a wall under load.
6. **No connection-pool tuning** (`pool_pre_ping`, `pool_recycle`, sizing). Multi-worker deployments will exhaust/stale connections.
7. **Dashboard reads are unbounded full scans.** No aggregate caching, no indexes on the filtered columns. Every dashboard load full-scans `leads`.
8. **Event/timeline growth is unbounded.** Once `lead_events` becomes the source of truth (it should), it grows fast and needs an indexing/partitioning/retention strategy.
9. **AI adapter is hardwired to Groq at import time.** No anti-corruption layer; provider lock-in and untestability.

### 🟢 Nice-to-have

10. No CDN/static strategy for the frontend; no read-replica story (premature, but note the seams now).

---

## 3. Current Architecture vs. LeadPulse Vision

| Vision capability | Today | Gap class |
|---|---|---|
| Multi-channel capture (web, FB, Google Forms, CSV, webhooks) | One generic `POST /leads` | 🔴 Missing subsystem |
| Lead routing (team/location/workload/rules) | None | 🔴 Missing subsystem |
| Qualification (budget/timeline/intent/source) | AI fills intent/budget/urgency; no `timeline`; budget is a string | 🟠 Partial |
| Follow-up engine (sequences, reminders, escalation) | String stubs ("Follow-up scheduled") | 🔴 Missing subsystem |
| **Revenue leak detection (the headline)** | **Nonexistent** | 🔴 Missing subsystem |
| Dashboard (revenue at risk, response times, conversion, team perf) | 3 counts | 🔴 Mostly missing |
| Team management (orgs/teams/users/roles) | Free-text `role` on a flat `User` | 🔴 Missing subsystem |
| Security (JWT/refresh/RBAC/audit/rate-limit) | Forgeable JWT, SHA-256, no refresh, no RBAC depth, no limits | 🔴 Foundational rework |
| Observability (logs/errors/metrics/health) | `print()` + a fake `/health` | 🔴 Missing |
| Premium TS/Tailwind/Shadcn frontend | JSX + unwired Tailwind, no Shadcn | 🔴 Re-baseline |

**Conclusion:** roughly **70% of the product is unbuilt at the architecture level**, and the 30% that exists (qualification pipeline + async offload) sits on a foundation (tenancy, identity, timeline, scheduling) that must be laid first. This is a *foundation-then-features* program, not an incremental cleanup.

---

## 4. Proposed Target Architecture

**Style decision: Modular Monolith. Not microservices.**

> **Assumption challenged:** "A serious SaaS needs microservices."
> **Rejected for now.** A 1–3 person team with no product-market fit yet should not pay the operational tax of distributed transactions, network failure modes, and N deployables. We build a **modular monolith with hard internal domain boundaries** (separate Python packages with explicit interfaces, no cross-domain DB reads). This gives us microservice-*ready* seams — any module can later be extracted behind its existing interface — without the cost today. **Revisit when** a single domain needs independent scaling or an independent team owns it.

```
┌──────────────────────────────────────────────────────────────────────┐
│  Frontend — React + TypeScript + Vite + Tailwind + Shadcn              │
│  AuthContext · React Query · Command palette · Dark mode · a11y        │
└───────────────────────────────┬──────────────────────────────────────┘
                                 │ HTTPS, JWT access + refresh
                                 ▼
┌──────────────────────────────────────────────────────────────────────┐
│  API Gateway Layer  (FastAPI, Gunicorn + uvicorn workers)              │
│  /api/v1  · request-id + tenant-id middleware · rate limiter           │
│  Dependency chain: authenticate → resolve tenant → scope → authorize   │
└───────┬──────────────────────────────────────────────────────────────┘
        │  calls domain services (in-process, via interfaces)
        ▼
┌──────────────────────────────────────────────────────────────────────┐
│                      DOMAIN MODULES (bounded contexts)                 │
│                                                                        │
│  Identity&Access   Ingestion   Qualification   Routing                 │
│  Pipeline          FollowUp     LeakDetection   Notifications          │
│  Analytics         Audit                                               │
│                                                                        │
│  Shared kernel: Tenant context · Event timeline · Outbox · Enums       │
└───────┬───────────────────────────────┬───────────────┬───────────────┘
        │ writes                         │ enqueues       │ emits events
        ▼                                ▼               ▼
┌────────────────┐         ┌──────────────────────┐   ┌────────────────┐
│  PostgreSQL    │         │  Async Plane (Celery) │   │  Outbox table  │
│  system of     │◀────────│  workers + beat        │──▶│ → relay → email│
│  record        │  reads  │  scheduled_jobs scanner│   │   /webhook/SMS │
│  (tenant-scoped│         │  leak-SLA scanner      │   └────────────────┘
│   + timeline)  │         └──────────┬─────────────┘
└────────────────┘                    │ broker / cache / rate-limit / idempotency
        ▲                             ▼
        │                    ┌──────────────────┐
        └────────────────────│      Redis       │
                             └──────────────────┘

  Cross-cutting: structured logging · Prometheus metrics · Sentry · OTel · health probes
  External (behind adapters): LLM provider (Groq/OpenAI) · SMTP/email · channel webhooks
```

### Key target-architecture decisions

- **API layer is thin.** Routes validate input, resolve the tenant/principal, and delegate to a domain service. No business logic in route handlers.
- **Domain modules talk through interfaces,** never by reaching into each other's tables. A module owns its tables.
- **The async plane is a peer to the API,** not an afterthought: it hosts the scheduled-job scanner and the leak-SLA scanner that *are* the product.
- **The Outbox pattern** makes external side effects exactly-once-ish: domain logic writes an `outbox` row in the same transaction as its state change; a relay task delivers it and marks it sent. This directly fixes the duplicate-email retry bug from the audit.
- **An anti-corruption layer wraps the LLM.** Providers are swappable; AI output is validated into a Pydantic contract before it touches the domain.

---

## 5. Domain Boundaries (Bounded Contexts)

Ten contexts. Each is a package under `app/domains/<name>/` with `models`, `service`, `schemas`, and (where relevant) `tasks`. Ownership of tables is exclusive.

| # | Bounded context | Responsibility | Owns (tables) | Key collaborators |
|---|---|---|---|---|
| 1 | **Identity & Access** | Orgs, teams, memberships, users, roles, auth, sessions/refresh tokens | `organizations`, `teams`, `memberships`, `users`, `refresh_tokens` | everyone (provides tenant context) |
| 2 | **Lead Ingestion** | Multi-channel capture, normalization, dedup, source attribution | `leads` (write path), `ingestion_sources` | Qualification, Routing |
| 3 | **Lead Qualification** | AI scoring/enrichment via LLM ACL, validated output, guardrails | `lead_qualifications` | Ingestion, Pipeline |
| 4 | **Routing & Assignment** | Rule engine: assign by team/location/workload/round-robin | `routing_rules`, assignment fields on lead | Identity, Pipeline |
| 5 | **Pipeline / Opportunity** | Opportunities, stages, proposals, meetings — the objects that *stall* | `opportunities`, `proposals`, `meetings`, `pipeline_stages` | FollowUp, LeakDetection |
| 6 | **Follow-Up Engine** | Sequences (D1/3/7/14), reminders, escalation, scheduled execution | `sequences`, `sequence_steps`, `enrollments`, `scheduled_jobs` | Notifications, LeakDetection |
| 7 | **Revenue Leak Detection** | SLA policies, monitors, the scanner, leak alerts | `sla_policies`, `leak_alerts` | Pipeline, FollowUp, Notifications |
| 8 | **Notifications** | Channel delivery (email/webhook/in-app), templating, outbox relay | `outbox`, `notification_log` | all (consumer of events) |
| 9 | **Analytics / Reporting** | Dashboard aggregates, response-time/conversion/team metrics | materialized views / `metric_snapshots` (read models) | reads everywhere (CQRS read side) |
| 10 | **Audit & Timeline** | Immutable event log — the system of record for "what happened when" | `events` (renamed/expanded `lead_events`) | all (everyone appends) |

> **Why split Pipeline from Lead:** a *lead* is an inbound contact; an *opportunity* is a qualified deal with stages and money. Leak detection mostly operates on opportunities (stalled deals, missed meetings, unfollowed proposals). Collapsing them — the current model — makes the headline feature impossible to express cleanly.

> **Why Audit/Timeline is its own context:** it is the shared substrate that LeakDetection and Analytics both read. Per §0, the timeline is not a logging nicety — it is the source of truth for transition-absence detection.

---

## 6. Service Boundaries

Within each context, a single **service object** is the public interface. Routes and tasks call services; services call repositories. Rules:

- **Services are the only public surface of a domain.** No route or task touches another domain's models directly.
- **Cross-domain calls go through the target's service interface** (in-process today; the same interface becomes a network boundary if extracted later).
- **Every service method receives an explicit `TenantContext`** (org_id + principal + role). No service can run "unscoped" — that's enforced by the type signature, not by discipline.
- **External I/O is always behind an adapter interface:** `LLMProvider`, `EmailSender`, `WebhookDispatcher`. The domain depends on the interface, never the SDK. (Fixes the import-time `Groq(...)` coupling.)
- **The async plane calls the same services** the API does. A Celery task is a thin shell: load context → call service → done. Business logic never lives in the task body.

Illustrative interfaces (signatures only — no implementation):

```
QualificationService.qualify(ctx, lead_id) -> QualificationResult
RoutingService.assign(ctx, lead_id) -> Assignment
FollowUpService.enroll(ctx, lead_id, sequence_id) -> Enrollment
FollowUpService.schedule_step(ctx, enrollment_id, step, run_at)   # writes scheduled_jobs
LeakDetectionService.evaluate(ctx, entity_ref) -> list[LeakAlert]
NotificationService.dispatch(ctx, notification)                   # writes outbox, never sends inline
LLMProvider.complete(prompt) -> RawCompletion                     # adapter; validated by caller
```

---

## 7. Database Architecture

### 7.1 System of record — PostgreSQL

**Tenancy model — decision: shared schema with row-level `org_id` scoping.**

> **Assumption challenged:** "Enterprise SaaS needs schema-per-tenant or DB-per-tenant for isolation."
> **Rejected for now.** Schema-per-tenant multiplies migration and connection complexity by tenant count and is operationally heavy for a pre-PMF startup. We use **shared-schema, row-scoped** multi-tenancy: every tenant-owned table carries a non-null `org_id` FK, and a mandatory query-scoping layer applies the filter. **Revisit when** an enterprise/compliance deal demands physical isolation — the `org_id` discipline makes a later split mechanical.

Enforcement is **defense in depth**, not a single filter:
1. Middleware resolves `org_id` from the validated JWT.
2. A scoping dependency injects `TenantContext` into every service call.
3. Repositories refuse to build a query without a tenant filter (base query helper).
4. **(Recommended) PostgreSQL Row-Level Security** as a backstop, so even a forgotten filter can't leak across tenants.

**Core schema principles:**
- Every tenant table: `id`, `org_id` (FK, indexed), `created_at`, **`updated_at`** (the column leak detection lives or dies by), soft-delete `deleted_at`.
- **Replace magic strings with enums/constrained types**: `LeadStatus`, `OpportunityStage`, `Role`, `LeakType`, `Channel`. No more `"yes"/"no"` booleans-as-strings.
- **Immutable timeline table `events`** (`org_id`, `entity_type`, `entity_id`, `event_type`, `payload jsonb`, `occurred_at`, `actor`). Append-only; the source of truth for §0.
- **Indexes that match access patterns:** composite `(org_id, status)`, `(org_id, assigned_to)`, `(org_id, stage, updated_at)` for stall queries, and `(entity_type, entity_id, occurred_at)` on `events`.
- **Foreign keys with explicit `ondelete`** and indexed FK columns (the audit found `lead_event.lead_id` unindexed).
- **Migrations: Alembic is mandatory and the only path to schema change.** No `create_all`. Autogenerate + reviewed migrations, run on deploy.

### 7.2 Scale seams (designed now, built later)

- **`events` partitioning** by month (or by `org_id` hash) once volume warrants — 🟢 nice-to-have, but the table shape is chosen now to allow it.
- **Read models for analytics (CQRS-lite):** dashboard metrics come from materialized views / periodically-refreshed `metric_snapshots`, not live full scans. 🟠 important.
- **Read replica** for analytics/reporting traffic — 🟢 later.

### 7.3 Redis — explicit role list

Redis is over-fixated as "just the Celery broker." Its target responsibilities:
1. Celery broker + result backend (with `result_expires`).
2. Rate-limiting counters (sliding window) for login + public ingestion.
3. Cache for dashboard aggregates and hot read models (short TTL).
4. Idempotency-key store (dedupe repeated ingestion/webhook deliveries).
5. JWT refresh-token denylist / revocation set.

---

## 8. Workflow Architecture

This is where the product lives. Four workflow families.

### 8.1 Ingestion (synchronous accept + async process)

```
channel → POST /api/v1/ingest/{source}  (authenticated or signed webhook, rate-limited)
        → validate + normalize + dedup (idempotency key)
        → persist Lead (org-scoped) + append `lead.received` event
        → enqueue qualify(lead_id)        → 202 Accepted
```
Public, paid AI work is now **gated**: signed/authenticated ingestion + rate limit + idempotency. CSV upload is a batch variant (enqueue one job per row with a parent batch id).

### 8.2 Qualification (idempotent, validated, outbox-safe)

```
qualify(ctx, lead_id):
   guard: skip if already qualified (idempotency on processed state)
   raw = LLMProvider.complete(prompt)              # ACL, retry only transient errors
   result = QualificationContract.validate(raw)    # Pydantic; strip md fences; coerce types; defaults
   normalize_score(result)                          # null-safe guardrails
   in ONE transaction:
       persist qualification + update lead state + append events + WRITE outbox(notify)
   commit
# delivery happens later via outbox relay — never inline, so retries can't double-send
```
This directly resolves the audit's three pipeline criticals: **idempotency**, **validated AI output**, **side-effects-after-commit**.

### 8.3 Follow-Up Engine — durable scheduling

> **Assumption challenged:** "Use Celery `countdown`/`eta` for Day-1/3/7/14 follow-ups."
> **Rejected.** ETA tasks are invisible (can't list/query "what's scheduled for this lead"), can't be cleanly cancelled or rescheduled when a human responds, and are lost if the broker is flushed. For a follow-up product that *must* cancel sequences the moment a rep engages, that's disqualifying.

**Decision: a durable `scheduled_jobs` table is the scheduling substrate.** Celery Beat runs a frequent **dispatcher** that claims due rows (`SELECT ... FOR UPDATE SKIP LOCKED`) and executes them.

```
Enroll lead in sequence → write scheduled_jobs rows (run_at = D1, D3, D7, D14)
Beat dispatcher (every minute): claim due jobs → execute step → write next/escalation job
Rep replies / lead converts → cancel pending scheduled_jobs for that enrollment (a query, trivially)
```
Benefits: queryable ("show this lead's scheduled touches"), cancellable, reschedulable, auditable, survives restarts, and is the *same table* the leak scanner reasons about.

### 8.4 Revenue Leak Detection — the SLA scanner

The product thesis (§0) made concrete. SLA policies are data, not code:

```
sla_policy: (org_id, leak_type, entity_type, condition, threshold, severity, action)
   e.g. (LEAD_IGNORED, lead, "no contact event since created_at", 24h, high, alert+escalate)
        (OPP_STALLED,  opportunity, "no stage change since updated_at", 7d, medium, alert)
        (MEETING_MISSED, meeting, "scheduled_at passed, status != completed", 0, high, alert)
        (PROPOSAL_COLD, proposal, "no follow-up event since sent_at", 3d, medium, alert)

Beat scanner (periodic): for each active policy →
   query timeline/state for entities breaching the window →
   if no existing open leak_alert for (entity, policy): create leak_alert +
       append event + enqueue Notification via outbox (+ optional auto follow-up/escalation)
```
Because policies are rows, customers can tune thresholds without a deploy, and FollowUp + LeakDetection share the timeline and the scheduled-jobs machinery — they are two faces of the same engine, exactly as the thesis predicts.

### 8.5 Outbox relay (reliable delivery)

A Beat task polls `outbox` for unsent rows, delivers via the channel adapter, marks sent / increments attempts with backoff, and dead-letters after max attempts. This is the single chokepoint where all external sends happen — observable and exactly-once-ish.

---

## 9. Security Architecture

Layered, with a single trust root. Ranked.

### 🔴 Critical

- **Single secret root.** Every secret (JWT key, LLM key, SMTP creds, webhook signing keys) comes from `Settings`/environment/secret manager. **Zero secrets in source.** App fails fast at boot if a required secret is unset in non-dev. (Audit found four hardcoded.)
- **Password hashing: argon2id (or bcrypt).** Replace SHA-256. Per-user salt by construction.
- **AuthZ as a 4-stage pipeline on every protected request:**
  `authenticate (verify JWT sig+exp)` → `resolve tenant (org_id)` → `scope (inject TenantContext, filter all queries)` → `authorize (role/permission + object ownership)`.
  No endpoint may skip stages 2–4. This closes the IDOR + "every user sees all leads" findings.
- **Tenant isolation enforced in the data layer** (scoping repositories + optional Postgres RLS), not just in handlers.
- **Gate the public AI endpoint:** authenticated or HMAC-signed ingestion + per-source rate limit + idempotency. Removes the cost-amplification/DoS vector.

### 🟠 Important

- **JWT: short-lived access (≈15 min) + refresh token with rotation + server-side revocation** (refresh-token table or Redis denylist). `get_current_user` re-validates against the DB (user exists, `is_active`, current role) rather than trusting stale claims.
- **RBAC model:** `Role` enum (Owner > Admin > Manager > Agent) with a permission matrix, scoped per org via `memberships`. Not a free-text column.
- **Rate limiting** (Redis sliding window) on login, ingestion, and expensive endpoints.
- **Input validation everywhere:** `EmailStr`, length/format bounds, signed-webhook verification, output-escaping in templated emails.
- **Tighten CORS** to configured origins; security headers (HSTS, CSP, etc.) at the edge.
- **Immutable audit log** with actor + tenant on every privileged action; append-only, committed in-band (audit found it never commits).

### 🟢 Nice-to-have

- JWT `iss`/`aud`/`nbf` + leeway; field-level encryption for sensitive PII at rest; secret rotation runbook; per-tenant API keys for programmatic access.

**Immediate non-architectural action (carried from audit):** rotate the leaked Groq key, Gmail app password, and JWT constant *now* — they exist in committed `.py` files.

---

## 10. Observability Architecture

You cannot run an SLA/alerting product blind. Four pillars.

### 🔴 Critical

- **Structured JSON logging** with a correlation/request-id and `org_id` on every line, **propagated across the Celery boundary** (so an async pipeline is traceable end to end). Replace all `print()`.
- **Real health probes:** separate **liveness** (process up) from **readiness** (DB reachable + Redis reachable + broker reachable). The current `/health` is a constant; wire the dead `health.py` router into a genuine readiness check.

### 🟠 Important

- **Error tracking (Sentry or equiv.)** on API and workers, tagged with tenant + request id.
- **Metrics (Prometheus `/metrics`)** across three layers:
  - *RED* for the API (rate / errors / duration per route).
  - *Async plane:* queue depth, task latency, retry/failure counts, **outbox lag**, **scheduled-jobs backlog**, **scanner run duration**.
  - *Business:* leads/min by source, qualifications/min, **leaks detected**, follow-ups sent, alert volume — these double as product analytics.
- **SLOs + alerting on the alerting system:** e.g. "leak scanner must complete within its interval," "outbox lag < N min." If our own SLA engine falls behind, that is a P1.

### 🟢 Nice-to-have

- **Distributed tracing (OpenTelemetry)** spanning API → Celery → external adapters.
- Log retention/shipping (Loki/ELK) and dashboards (Grafana).

---

## 11. Consolidated Findings & Ranking

### 🔴 Critical (foundation — must precede feature work)
1. Establish the **tenancy plane** (org/team/membership + `org_id` everywhere + scoping layer + RLS backstop).
2. Re-model the domain around an **immutable event timeline + `updated_at`** (enables leak detection at all).
3. Introduce a **durable scheduling substrate** (`scheduled_jobs` + dispatcher) for follow-ups and the leak scanner.
4. Split **Lead vs Opportunity/Pipeline** so stalls/meetings/proposals are first-class.
5. **Secrets to a single root**, argon2/bcrypt hashing, and the **4-stage authn→tenant→scope→authz** pipeline.
6. **Gate the public AI endpoint**; make the qualification pipeline **idempotent + validated + outbox-delivered**.
7. **Alembic** as the only schema path; **adopt the modular-monolith package structure** with domain-owned tables.
8. Structured logging + real readiness probes (you can't operate the product otherwise).

### 🟠 Important
9. Gunicorn + uvicorn workers; tune the DB pool (`pool_pre_ping`/`recycle`/sizing).
10. JWT access+refresh with rotation/revocation; DB-backed user/role re-validation; RBAC enum + permission matrix.
11. Rate limiting + input validation (`EmailStr`, signed webhooks) across the edge.
12. Enums replacing magic strings; indexes matching access patterns; FK `ondelete` + indexed FKs.
13. CQRS-lite read models for the dashboard (no live full scans); Redis caching of aggregates.
14. LLM anti-corruption layer (swappable provider, injected, not import-time).
15. Sentry + Prometheus (RED + async + business metrics) + SLOs on the scanner/outbox.
16. Frontend re-baseline to TS + wired Tailwind + Shadcn, AuthContext + React Query, 401 interceptor (architectural enablers for everything in the UI spec).

### 🟢 Nice-to-have
17. `events` partitioning + retention; read replica for analytics.
18. OpenTelemetry tracing; log shipping/dashboards.
19. JWT `iss/aud/nbf`; field-level PII encryption; per-tenant API keys; secret-rotation runbook.

---

## 12. Risks, Tradeoffs & What I'm Deliberately *Not* Doing

- **Not adopting microservices.** Operational tax with no payoff pre-PMF. Modular monolith keeps the option open (§4).
- **Not adopting full event sourcing/CQRS.** We use *event-sourcing-lite* (an authoritative timeline + read models) — the benefit for leak detection without the rebuild-state-from-events complexity. **Risk:** the timeline and the mutable state can drift; mitigated by writing both in one transaction.
- **Not rewriting to fully-async SQLAlchemy yet.** Gunicorn+workers buys substantial headroom; an async rewrite is a large, separable effort. **Revisit** when per-request DB latency under concurrency becomes the bottleneck.
- **Staying on Celery + Redis** rather than Temporal/Kafka. Celery + a durable `scheduled_jobs` table covers the workflow needs at this stage; heavier orchestration is a later migration if sequence complexity explodes. **Risk:** the dispatcher polling model has a floor on scheduling precision (≈1 min) — acceptable for follow-up SLAs measured in hours/days.
- **Biggest program risk:** the foundation work (tenancy, timeline, scheduling) is invisible to a demo but gates everything. The temptation will be to skip it and build features on sand. **This document exists to make that tradeoff explicit and resist it.**

---

## 13. Recommended Sequencing (for the Phase 3+ plans, not executed here)

1. **Hygiene & trust** — repo cleanup, secrets to config, deps, Alembic bootstrap. *(unblocks everything)*
2. **Foundation** — tenancy plane, identity/RBAC, timeline, enums, modular package layout.
3. **Pipeline & scheduling substrate** — Lead/Opportunity split, `scheduled_jobs`, outbox.
4. **Core product** — follow-up engine, then leak detection (they reuse #3).
5. **Ingestion channels + routing.**
6. **Frontend re-baseline + dashboard read models.**
7. **Observability + security hardening + tests to coverage gates.**
8. **Production packaging** (Docker multi-stage, Gunicorn, healthchecks, CI).

> Detailed refactor/architecture/implementation plans are **Phase 3–5 deliverables** and are intentionally out of scope for this review.

---

*End of Architecture Review. No code written. No refactoring performed.*
