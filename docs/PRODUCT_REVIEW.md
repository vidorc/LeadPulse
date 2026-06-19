# LeadPulse — Product Review (Phase 2)

**Date:** 2026-05-31
**Author:** Staff Engineering / Product review
**Inputs:** `AUDIT_REPORT.md` (Phase 1), `ARCHITECTURE_REVIEW.md` (Phase 2 architecture)
**Scope:** Does the *current* codebase support each headline product capability? Evidence is cited from the source tree; this is a review, not a plan.
**Status:** Read-only assessment. No code written.

---

## 0. How to read this document

The audit (Phase 1) described a single-tenant, happy-path qualification demo. Since then the foundation work the architecture review demanded has largely landed: a tenancy plane (`org_id` on every row via `TenantMixin`), a DB-backed 4-stage authz pipeline (`app/api/deps.py`), an immutable event timeline (`app/models/event.py`), a durable scheduler (`app/models/scheduled_job.py`), a transactional outbox (`app/models/outbox.py`), and an SLA-driven leak scanner (`app/services/leak_detection.py`). Seventeen tables now exist across three Alembic migrations.

So this review measures the product against a **much stronger baseline** than the audit did. The question is no longer "does the data model exist" — it does — but "is each capability actually wired end-to-end, and where are the honest gaps." The verdict per capability is one of:

| Verdict | Meaning |
|---|---|
| ✅ **Supported** | Models + service + route exist and are wired end-to-end |
| 🟡 **Partial** | Substrate exists, but a layer (route, channel, depth) is missing |
| 🔴 **Gap** | Capability is absent or only a documented extension point |

The architecture review's thesis still governs everything: **LeadPulse is a temporal SLA engine, not a CRM.** Leak detection and the follow-up engine are the same primitive (a timestamped expectation + a scanner/dispatcher) viewed from two angles. The code now reflects that thesis directly — `Event`, `ScheduledJob`, and `SLAPolicy` are first-class — which is why most capabilities below score better than the audit would predict.

---

## 1. Capability assessment

### 1.1 Lead Capture — 🟡 Partial

**What exists.** `Lead` (`app/models/lead.py`) is tenant-scoped, soft-deletable, and carries a `source`, an `idempotency_key` (indexed, per-org), and the timestamp mixins leak detection depends on. Two capture paths are real:

- **Authenticated manual entry** — `POST /api/v1/leads` (`app/api/routes/leads.py:34`) creates a tenant-scoped lead via `LeadRepository.add` (which forces `org_id = ctx.org_id`) and offloads qualification to Celery with the org id (`process_lead_ai.delay(lead.id, ctx.org_id)`). This closes the audit's "public, unauthenticated, paid-AI endpoint" finding — creation now requires a principal and is tenant-attributed.
- **Signed webhook / CSV ingestion** — `app/services/ingestion_service.py` implements the gated path the architecture review §8.1 specified: constant-time HMAC-SHA256 verification of the raw body against the org's `ingest_secret` (`verify_signature`), org resolution by slug, idempotent `ingest_lead` (returns `(lead, created)` and won't re-enqueue on a duplicate key), and `parse_csv` for the batch variant. `organizations.ingest_secret` and `leads.idempotency_key` are real columns (migration `c3a8e5f1d6b7`).

**The gap.** `ingestion_service` has **no route**. There is no `app/api/routes/ingestion.py`, and `app/main.py` mounts only auth/leads/opportunities/follow-ups/leak-detection/health. So the spec's named sources — Facebook Leads, Google Forms, generic webhooks, CSV upload — have a fully-built service layer but **no HTTP surface to reach it**. The capability is one thin router away, but today it is not reachable. `source` is also still a free-text `String(64)`, not a constrained enum, so per-source attribution and routing rules can't yet key off a typed value.

**Verdict:** the hard part (idempotent, signed, tenant-scoped ingestion + auto-routing) is built and unit-testable; the easy part (mounting it) is outstanding.

### 1.2 Lead Qualification — ✅ Supported

The qualification pipeline is the strongest, most complete capability, and it now resolves all three pipeline criticals from the audit:

- **Validated AI output.** `QualificationContract` (`app/schemas/qualification.py`) is an anti-corruption layer: it coerces intent/urgency to enums, bounds `score` to 0–100, stringifies free-text fields, and *never raises* on bad LLM input (`from_raw` defaults a non-dict to `{}`). The pipeline no longer does `ai_result["score"]` blindly.
- **Idempotency.** `process_lead_ai` (`app/tasks/lead_tasks.py:61`) skips a lead whose `processed_at` is set or whose status is terminal, so a retry can't re-run side effects.
- **Exactly-once side effects.** State change, timeline events, and the hot-lead notification (`enqueue_hot_lead_alert`) all commit in **one** transaction (`lead_tasks.py:134`); delivery happens later via the outbox relay. `autoretry_for` is narrowed to `(ConnectionError, TimeoutError)` — no more burning retries on programming errors.

The pure decision/guardrail functions (`decision_engine.decide_lead_action`, `scoring_guardrails.normalize_score`, `review_router.requires_review`) are deterministic and null-safe (the audit's `budget.lower()` crash is fixed — `normalize_score` now coerces `str(budget)`). Qualification also gained the previously-missing `timeline` field and a parsed `budget_amount Numeric(14,2)` for range queries.

**Minor gap:** the LLM is still a direct `qualify_lead(...)` call rather than an injected `LLMProvider` adapter, so provider-swap and offline testing require mocking the module. This is the one architecture-review recommendation (the LLM ACL interface) not yet realized in code.

### 1.3 WhatsApp Automation — 🔴 Gap

This is the clearest product gap, and it is worth being blunt about. The delivery substrate (`OutboxMessage` + `outbox_service.relay_pending` + channel adapters) is well-built, but it speaks exactly three channels:

```python
# app/core/enums.py
class OutboxChannel(str, enum.Enum):
    EMAIL = "email"
    WEBHOOK = "webhook"
    IN_APP = "in_app"
```

`outbox_service._deliver` (`app/services/outbox_service.py:55`) dispatches on those three and `raise ValueError` on anything else. There is **no WhatsApp channel, no WhatsApp adapter, no provider credentials** (`config.py` has SMTP and a generic `WEBHOOK_URL`, nothing for Twilio/Meta WhatsApp Business API), and no inbound-message handling (a WhatsApp reply would need to flow back as a `lead.contacted` event to cancel follow-up sequences).

**The good news is that the architecture anticipated this.** `OutboxChannel` is the documented extension point: adding `WHATSAPP = "whatsapp"`, a branch in `_deliver`, a `WhatsAppSender` adapter, and provider settings is an additive change that reuses the entire outbox reliability machinery (dedupe key, backoff, dead-lettering, the relay loop). Follow-up steps already carry an `action` field (`SequenceStep.action`, default `"email"`), so a `"whatsapp"` step action is a natural fit. Nothing structural blocks it — but as of today the capability does not exist.

### 1.4 Follow-Up Automation — ✅ Supported

This is fully wired end-to-end on the durable scheduling substrate the architecture review insisted on (rejecting Celery `eta`):

- **Sequences** (`Sequence`/`SequenceStep`/`Enrollment`, `app/models/sequence.py`) with per-step `delay_hours` (the Day 1/3/7/14 plan), `step_order` uniqueness, and a one-active-enrollment-per-(sequence, lead) constraint.
- **Enrollment** (`FollowUpService.enroll`) schedules the first step as a `ScheduledJob` row, not a Celery countdown — so it is queryable and cancellable.
- **Execution** — `_execute_followup_step` (registered via `scheduler.register_handler`) runs the due step, enqueues the message through the outbox, appends a `FOLLOWUP_SENT` event, and schedules the next step or completes the enrollment.
- **Cancellation** — `cancel_for_lead` flips active enrollments to `CANCELLED` and `scheduler.cancel_for_entity` cancels their pending jobs. This is the exact "stop touching the lead the moment a rep engages" capability the review said `eta` couldn't provide, and it's a trivial UPDATE here.
- **Heartbeat** — `dispatch_scheduled_jobs` runs every 60s via Beat (`celery_app.py`), claiming due rows with `SELECT ... FOR UPDATE SKIP LOCKED` so multiple workers never double-execute.

Routes exist (`app/api/routes/follow_ups.py`): create/list sequences (manager-gated), enroll, cancel-for-lead. **Escalation rules** (spec item) are not yet modeled as data — a step can send a message but there is no "if no response by step N, escalate to manager" branch. That is the one follow-up sub-feature still missing.

### 1.5 Revenue Leak Detection — ✅ Supported (the headline feature is real)

The audit called this "nonexistent… the headline product feature and it is unimplemented." It now exists and matches the architecture thesis precisely. `app/services/leak_detection.py` implements **transition-absence detection** over four leak types, with **policies as data** (`SLAPolicy`, tunable per-org without a deploy):

| Leak type | Query (`_breaching_entities`) |
|---|---|
| `LEAD_IGNORED` | `Lead.created_at < cutoff` AND status in uncontacted set |
| `OPP_STALLED` | `Opportunity.stage_changed_at < cutoff` AND stage not terminal |
| `MEETING_MISSED` | `Meeting.scheduled_at < cutoff` AND status == SCHEDULED |
| `PROPOSAL_COLD` | `Proposal.sent_at < cutoff` AND no `PROPOSAL_FOLLOWUP` event since `sent_at` |

The scanner is **idempotent** — `_has_open_alert` plus a DB uniqueness constraint (`uq_open_alert_per_entity` on org/leak_type/entity/status) guarantees one OPEN alert per breach. Each new alert appends a `LEAK_DETECTED` timeline event and, if `policy.notify`, enqueues an outbox notification. It runs every 5 minutes via Beat (`scan_leaks`) and on demand via `POST /leak-detection/scan` (manager-gated). Routes for policy upsert, alert listing/filtering, and resolution all exist (`app/api/routes/leak_detection.py`).

The model is honest about its own boundary: `PROPOSAL_COLD` reasons over the timeline (no follow-up event), while the other three reason over mutable state columns (`created_at`/`stage_changed_at`/`scheduled_at`). Both work because every state mutation in `OpportunityService` stamps its timestamp **and** appends an event in one transaction, so state and timeline don't drift.

### 1.6 Analytics — 🟡 Partial

This is genuinely thin and should not be oversold. The entire dashboard backend is `LeadRepository.summary_counts` (`app/repositories/lead_repository.py:19`): four scalar counts (total / hot / manual-review / converted), each a `SELECT COUNT(*)` against `leads`. That is an improvement over the audit's three counts (it's now tenant-scoped and avoids the duplicate-route mess), but measured against the Phase 3 dashboard spec it is mostly absent:

- **Revenue at risk** — not computed. The data exists (`LeakAlert` joined to `Opportunity.value_amount`), but nothing aggregates it.
- **Response times** — not computed. The `events` timeline holds everything needed (time from `LEAD_INGESTED` to first `LEAD_ASSIGNED`/contact), but there is no query.
- **Opportunities stalled / leads ignored** — surfaced as raw alert lists, not as dashboard metrics.
- **Team performance** — not computed; no per-owner/per-team aggregation exists.

There are **no read models, no materialized views, no `metric_snapshots`**, no Redis caching of aggregates. Every count is a live query. For the current data volume that's fine, but the CQRS-lite read-model seam the architecture review §7.2 designed is not yet built. Analytics is the capability with the widest gap between "data is available" and "product surfaces it."

### 1.7 Team Collaboration — 🟡 Partial

The identity and tenancy substrate is complete and well-modeled:

- `Organization` (tenancy root, `app/models/organization.py`), `Team`, `Membership` (binds user↔org with a per-org `Role`, so one user can be OWNER of one org and AGENT of another), `User` (global identity; role lives on membership, not the user).
- **RBAC** is a real `Role` enum (OWNER > ADMIN > MANAGER > AGENT) with `.rank`/`.at_least` ordering, enforced via `require_role`/`require_manager`/`require_admin` dependencies and `TenantContext.require_role`.
- **Lead routing/assignment** is built: `routing_service.assign_lead` does least-loaded round-robin across an org's (optionally team-scoped) members, balancing by open-lead count, and appends a `LEAD_ASSIGNED` event. `Lead.owner_id`/`team_id` are real FKs.

**The gaps are the collaboration *surfaces*, not the model.** There is no invite flow (`signup` bootstraps an org + OWNER, but the comment notes "subsequent users are invited by an admin (Phase 6)" — that route doesn't exist yet). There is no team CRUD route, no membership-management route, no role-change endpoint, no per-team or per-territory routing rule engine (the round-robin is the only strategy; the docstring calls it a deliberate seam). So an org is currently a single-user island in practice: the multi-user data model is sound, but the APIs to grow and manage a team aren't mounted.

---

## 2. Capability scorecard

| Capability | Verdict | Evidence | Principal gap |
|---|---|---|---|
| Lead Capture | 🟡 Partial | `ingestion_service.py`, `leads.py:34` | Ingestion service has no mounted route; `source` is free-text |
| Lead Qualification | ✅ Supported | `lead_tasks.py`, `qualification.py` | LLM not behind an injected adapter |
| WhatsApp Automation | 🔴 Gap | `OutboxChannel` (EMAIL/WEBHOOK/IN_APP only) | No channel, adapter, creds, or inbound handling |
| Follow-Up Automation | ✅ Supported | `followup_service.py`, `scheduler.py` | No escalation-rule modeling |
| Revenue Leak Detection | ✅ Supported | `leak_detection.py`, `leak.py` | None material; scanner is per-policy full-ish scan |
| Analytics | 🟡 Partial | `lead_repository.summary_counts` | 4 counts only; no read models, revenue-at-risk, response-time, team metrics |
| Team Collaboration | 🟡 Partial | `membership.py`, `routing_service.py` | No invite/team/role-management routes; single routing strategy |

**Net:** the foundation the architecture review prescribed is built and the two defining features (follow-up engine, leak detection) are genuinely live end-to-end. The remaining product gaps are concentrated in **reachability** (ingestion route, team-management routes), **a missing channel** (WhatsApp), and **analytics depth**. There is also no billing/subscription model anywhere in the tree — not a gap against the current spec features, but a prerequisite for commercializing the platform and worth naming now.

---

## 3. Architectural bottlenecks

Ranked by how hard they cap the product, in the audit's convention.

### 🔴 Critical

1. **The leak scanner does not scale with tenant or entity count.** `leak_detection.scan` loops every active `SLAPolicy` across all orgs and, per policy, runs an unindexed-on-the-filter query over the full entity table (e.g. all non-terminal opportunities with `stage_changed_at < cutoff`). There is no per-tenant sharding, no incremental cursor, and `PROPOSAL_COLD` issues an N+1 follow-up-event lookup per sent proposal (`outbox_service`-style per-row `SELECT`). At 5-minute cadence this is fine for tens of orgs; it becomes the product's hardest scaling wall well before the API does, because it is *the* product and runs unconditionally. The architecture review flagged scanner SLOs ("the scanner must complete within its interval") — there is no such guard yet.

2. **The async plane is a single logical queue.** All Celery work — the paid per-lead qualification, the 60s job dispatcher, the 30s outbox relay, the 5-min leak scan — shares one Redis broker and one default queue (`celery_app.py` defines no `task_routes`). A burst of lead ingestion (paid LLM work) can starve the dispatcher and relay, which delays follow-ups and notifications — i.e. a traffic spike degrades the exact SLAs the product sells. There is no queue partitioning by workload class.

### 🟠 Important

3. **Observability is built but not wired.** `app/core/logging.py` (structlog JSON + request-id contextvar) and `app/core/metrics.py` (Prometheus counters/histograms, including `leadpulse_leak_alerts_created_total`) exist as well-formed modules, but `app/main.py` does **not** install a request-context middleware, does **not** mount `/metrics`, and does **not** call `configure_logging()`. Until that wiring lands, an operator running this SLA/alerting product is effectively blind — there is no request correlation and no scrape endpoint. (This is in-flight in the current hardening effort; see the plan.)

4. **Single sync uvicorn process on a sync SQLAlchemy stack.** `gunicorn` is now in `requirements.txt` and the pool is tuned (`pool_pre_ping`, `pool_recycle=1800`, `pool_size=10`, `max_overflow=20` in `session.py`), so the headroom exists — but the process model still needs Gunicorn + uvicorn workers to use it. Blocking DB calls hold a worker for the duration.

5. **No rate limiting is enforced.** Settings carry `RATE_LIMIT_LOGIN_PER_MINUTE` / `RATE_LIMIT_INGEST_PER_MINUTE` and `metrics.py` defines a `leadpulse_rate_limited_total` counter, but there is no limiter middleware. `/auth/login` is open to credential stuffing, and once the ingestion route is mounted it will drive paid LLM spend unthrottled.

### 🟢 Nice-to-have

6. **The timeline (`events`) has no retention/partitioning.** Every state change appends a row; it will be the fastest-growing table. The indexes are right (`ix_events_entity`, `ix_events_org_type_time`) and the shape is partition-ready, but no partitioning or archival exists yet.

---

## 4. Domain model problems

The model is dramatically healthier than the audit's (enums everywhere, `updated_at` universal, FKs with explicit `ondelete`, tenant scoping uniform). The remaining issues are specific:

### 🟠 Important

1. **The timeline is polymorphic-by-convention, with no referential integrity.** `Event.entity_id` and `ScheduledJob.entity_id` / `LeakAlert.entity_id` are plain `Integer` columns paired with an `EntityType` enum — there is no FK enforcing that `(entity_type=OPPORTUNITY, entity_id=42)` actually points at a live opportunity. This is the standard tradeoff for a generic timeline, but it means a hard-deleted entity orphans its events/alerts/jobs silently, and a bug could append events against a non-existent id with no DB-level rejection. Acceptable for an append-only log; worth a periodic integrity sweep.

2. **`event_type` is a free-text `String(64)`.** `"LEAD_INGESTED"`, `"STAGE_CHANGED"`, `"PROPOSAL_FOLLOWUP"`, etc. are string literals scattered across services. The audit's whole thesis was "replace magic strings with enums," and this is the one place magic strings remain — and they are load-bearing: `leak_detection` matches `Event.event_type == "PROPOSAL_FOLLOWUP"` by string. A typo at the producer (which writes events) silently breaks the consumer (the leak scanner), with no test or type to catch it. These should be an `EventType`/`EventName` enum.

3. **`source` on `Lead` is unconstrained.** Multi-channel capture and source-attribution analytics need a typed channel; today `source` is `String(64)`, so "facebook" vs "Facebook" vs "fb" are distinct values that will fragment any group-by.

4. **No billing/subscription/plan model exists.** There is no `Plan`, `Subscription`, `UsageRecord`, or per-org quota anywhere. Quotas (leads/month, seats, SLA-policy count) and metering can't be expressed against the current schema. This is foundational for monetization and, like tenancy was in the audit, cheaper to add deliberately than to retrofit.

### 🟢 Nice-to-have

5. **`SequenceStep.action` is a `String(64)`, not an enum.** It gates behavior (`if step.action == "email"`), so it's the same magic-string class as `event_type`, just lower-stakes. It is also the seam a `"whatsapp"` action would extend.

6. **`Numeric(14,2)` money columns carry no currency on `Lead`.** `Opportunity` has a `currency` column; `Lead.budget_amount` and `Proposal.amount` do not, so cross-currency aggregation (revenue at risk) is ambiguous if an org operates in multiple currencies.

---

## 5. Future scaling risks

Naming these now so the seams are chosen deliberately, per the review's 3-year horizon.

### 🔴 Critical

1. **Single-region, single-primary database is assumed throughout.** Every read and write goes to one `engine` (`session.py`) bound to one `DATABASE_URL`. There is no read-replica routing, so analytics/dashboard load and the leak scanner's table sweeps contend with transactional writes on the same primary. The architecture review listed read replicas as "🟢 later," but because the scanner and dashboard are both read-heavy and run continuously, replica pressure will arrive sooner than for a typical CRUD app. There is also no multi-region story — `org_id` row-scoping makes data-residency splits *mechanical*, but nothing is partitioned by region today.

2. **Scheduler and outbox throughput are bounded by fixed batch sizes and poll intervals.** `dispatch_due(batch_size=100)` every 60s and `relay_pending(batch_size=50)` every 30s impose hard ceilings: ~6,000 follow-up executions/min and ~6,000 deliveries/min at saturation, single-worker. `FOR UPDATE SKIP LOCKED` makes these safely horizontally scalable across workers, but nothing auto-scales workers or partitions the claim by tenant, so a large customer's burst can monopolize a batch and delay everyone else's SLAs (a noisy-neighbor risk in a shared-schema model).

### 🟠 Important

3. **Shared-schema tenancy has no per-tenant resource isolation.** The decision (architecture review §7.1) is sound for pre-PMF, and the enforcement is genuinely defense-in-depth — middleware/JWT (`deps.py`), `TenantContext`, and the `TenantRepository.scoped_query` base that makes an unscoped query *unexpressible*. But note: the review recommended **Postgres Row-Level Security as a backstop, and it is not implemented** (no RLS policies in any migration). So a future raw-SQL path or a service that bypasses `TenantRepository` (e.g. `leak_detection` writes raw `select(...)` directly, correctly filtering `org_id` by hand) has no database-level safety net. One forgotten `.where(org_id == ...)` in a hand-written query leaks across tenants. RLS would make that class impossible; it remains a recommendation, not a control.

4. **Redis is mono-purpose.** It is the broker and result backend only. The review's target role list (rate-limit counters, aggregate cache, idempotency store, refresh-token denylist) is unrealized — refresh-token revocation is currently DB-backed (`RefreshToken.revoked`), which is correct but adds primary-DB load on every refresh. As traffic grows, several of these belong in Redis.

5. **The LLM dependency is an unbudgeted, unbounded cost vector at scale.** Qualification is correctly offloaded and now idempotent, but there is no per-org quota, no spend ceiling, and (until the ingestion route is gated by the planned rate limiter) the cost scales linearly with inbound volume with no cap. This ties directly to the missing billing model: without usage metering, paid AI work can't be attributed or capped per plan.

### 🟢 Nice-to-have

6. **Frontend is still the prototype baseline.** `frontend/src` is JSX (`Login`/`Dashboard`/`ReviewQueue`/`LeadDetails` + `LeadTable` + `api.js`), no TypeScript, Tailwind unwired, no command palette or dark mode. It calls the old API shape and will need re-baselining against the `/api/v1` surface. Not a backend scaling risk, but it gates the entire UI spec (Phase 8) and the dashboard depth (§1.6).

---

## 6. Summary

LeadPulse has crossed the line the audit drew: it is no longer a single-tenant demo. The temporal-SLA foundation is real, and the two features that *define* the product — the follow-up engine and revenue leak detection — are wired end-to-end on a shared, durable substrate (timeline + scheduler + outbox), exactly as the architecture thesis predicted they could be.

The honest gaps are now narrow and specific rather than foundational:

- **One missing channel** (WhatsApp) on an otherwise-complete delivery system — an additive extension at `OutboxChannel`.
- **Two unmounted capabilities** (multi-channel ingestion, team management) whose service/model layers already exist.
- **Shallow analytics** — the data is all present in `events` and the domain tables; nothing aggregates it into the dashboard the spec describes.
- **Observability wired-but-dark** and **no enforced rate limiting** — both in-flight in the current hardening effort.
- **No billing model** — fine for the feature spec, foundational for the business.

None of these require the schema rewrite the audit feared. They are reachability, one channel, query depth, and commercial plumbing — which is the right shape of problem to have at this stage. The work items are sequenced in `IMPLEMENTATION_PLAN.md`.

---

*End of Product Review. No code written.*
