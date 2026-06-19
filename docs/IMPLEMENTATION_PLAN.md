# LeadPulse — Implementation Plan (Phase 4)

**Date:** 2026-05-31
**Author:** Staff Engineering
**Inputs:** `AUDIT_REPORT.md` (Phase 1), `ARCHITECTURE_REVIEW.md` (Phase 2 architecture), `PRODUCT_REVIEW.md` (Phase 2 product).
**Status:** Plan only. Sequencing and scoping for the remaining work to reach the Phase 9 production deliverable.
**Horizon:** Four sprints (~2 weeks each), ordered so each one ships something runnable and de-risks the next.

---

## 0. Where we are starting from

This is not a greenfield plan. The foundation the architecture review prescribed has largely landed on the `production-hardening` branch, so Sprint 1 is mostly *documenting and finishing* what exists rather than building from scratch. The plan is calibrated to that reality:

- **Done and wired:** tenancy plane (`TenantMixin`, `org_id` everywhere), the 4-stage DB-backed authz pipeline (`app/api/deps.py`), Argon2id + JWT access/refresh with rotation/revocation (`security.py`, `auth_service.py`, `RefreshToken`), the immutable timeline (`Event`), the durable scheduler (`ScheduledJob` + `scheduler.py`), the transactional outbox (`OutboxMessage` + `outbox_service.py`), the SLA leak scanner (`leak_detection.py`), the follow-up engine (`followup_service.py`), the opportunity pipeline (`opportunity_service.py`), tuned DB pooling (`session.py`), a real Celery config with a beat schedule (`celery_app.py`), three Alembic migrations covering all 17 tables, and fail-fast secret validation (`config.py`).
- **Built but not wired:** structured logging (`app/core/logging.py`) and Prometheus metrics (`app/core/metrics.py`) — both well-formed modules that `app/main.py` does not yet install.
- **Service exists, route missing:** multi-channel ingestion (`ingestion_service.py` has HMAC verification, idempotent ingest, CSV parsing — but no router).
- **Not started:** request-id middleware, global exception handler, rate limiter, audit log, the `/metrics` mount, a pytest suite + coverage gate, GitHub Actions CI, the WhatsApp channel, billing, analytics depth, team-management routes, and the React/Vite TS dashboard re-baseline.

Each sprint below states **Objectives**, **Deliverables**, **Risks**, and **Dependencies**, with deliverables tied to specific files/modules so scope is unambiguous.

---

## Sprint 1 — Harden, Observe, Test, Ship CI

**Theme:** Close the production-readiness gap on what already exists. Wire the observability modules that are written but dark, enforce the security controls the settings already anticipate, and stand up the test + CI safety net so every subsequent sprint lands on green. This sprint is mostly *finishing*, not inventing — most of the substrate is in `app/core/`.

### Objectives
- Make the running app observable end-to-end (structured logs with request correlation, scrape-able metrics, real health distinctions).
- Enforce the rate limiting and edge controls the config and metrics already reference.
- Add the audit log the spec (Phase 6) and architecture review §9 require.
- Reach the Phase 7 coverage gate (backend 80%+) and gate it in CI.
- Mount the ingestion route so the already-built `ingestion_service` becomes reachable.

### Deliverables
- **Request-context middleware** (`app/core/middleware.py`, new): generate/propagate a request id, bind it to the `request_id_ctx` contextvar already defined in `app/core/logging.py`, time each request, and increment `REQUEST_COUNT`/`REQUEST_LATENCY` from `app/core/metrics.py`. Propagate the id across the Celery boundary (task header → contextvar) so an async pipeline is traceable.
- **Wire observability into `app/main.py`:** call `configure_logging(json_logs=settings.is_production)` at startup, add the middleware, and mount `GET /metrics` returning `render_latest()`. These modules exist; this is integration, not authoring.
- **Global exception handler** (`app/main.py`): catch unhandled exceptions, log them structured with the request id, return a sanitized JSON error envelope (no stack traces to clients). Replace any remaining ad-hoc error leakage.
- **Rate limiter** (`app/core/ratelimit.py`, new): Redis sliding-window using the existing `RATE_LIMIT_LOGIN_PER_MINUTE` / `RATE_LIMIT_INGEST_PER_MINUTE` settings, incrementing the already-defined `leadpulse_rate_limited_total` counter. Apply to `/auth/login` and the new ingestion route.
- **Audit log** (`app/models/audit_log.py` + append helper, or extend the `Event` timeline with a privileged-action convention): record actor + org + action on logins, role changes, overrides, policy upserts. Committed in-band (the audit flagged the old logger never committed).
- **Ingestion router** (`app/api/routes/ingestion.py`, new): `POST /api/v1/ingest/{slug}` (HMAC-verified via `ingestion_service.verify_signature`, rate-limited, idempotent) and `POST /api/v1/ingest/{slug}/csv` (batch via `parse_csv`). Mount in `main.py`. This unlocks the Lead Capture capability that `PRODUCT_REVIEW.md §1.1` flagged as service-complete-but-unreachable.
- **`EventType` enum** (`app/core/enums.py`): replace the load-bearing `event_type` string literals (`"PROPOSAL_FOLLOWUP"`, `"STAGE_CHANGED"`, …) so the leak scanner's `Event.event_type == "PROPOSAL_FOLLOWUP"` match can't be silently broken by a producer typo (`PRODUCT_REVIEW.md §4.2`).
- **Test suite** (`tests/`, currently empty) using the tooling already pinned in `requirements-dev.txt` (pytest, pytest-cov, factory-boy, freezegun, fakeredis): `conftest.py` with a transactional DB fixture + `task_always_eager` Celery config; unit tests for the pure functions (`decision_engine`, `scoring_guardrails`, `review_router`, `QualificationContract`); service tests for `leak_detection.scan`, `followup_service` enroll/cancel, `scheduler.dispatch_due`, `outbox_service.relay_pending` (with fakeredis), and the tenancy guarantee (`TenantRepository` cross-tenant isolation); API tests for the auth pipeline and IDOR closure. Target `--cov-fail-under=80`.
- **GitHub Actions CI** (`.github/workflows/ci.yml`, new): matrix of lint (ruff), type-check (mypy — both pinned in dev deps), and `pytest --cov` with Postgres + Redis service containers, failing under 80%.

### Risks
- **Coverage theatre.** Hitting 80% is easy to game with shallow tests. Mitigation: prioritize the temporal/transactional paths (idempotency in `process_lead_ai`, exactly-once in the outbox, `FOR UPDATE SKIP LOCKED` claim logic) — the bugs that hurt are concurrency and retry bugs, which line coverage alone won't catch. Use `freezegun` to test SLA-window boundaries.
- **Middleware ordering / async-boundary id loss.** The request id must survive the FastAPI→Celery hop; getting contextvar propagation wrong yields logs that look correlated but aren't. Mitigation: an explicit Celery `before_task_publish`/`task_prerun` signal pair, tested.
- **Rate limiter as a new failure mode.** A Redis blip shouldn't 500 every login. Mitigation: fail-open with a logged warning + `leadpulse_rate_limited_total{scope="error"}` increment, never fail-closed on limiter infrastructure errors.

### Dependencies
- None external; everything here builds on modules already in the tree (`logging.py`, `metrics.py`, `config.py` rate-limit settings, `requirements-dev.txt` tooling). Redis (already in compose) must be reachable for the limiter and fakeredis-backed tests.
- The `EventType` enum migration must precede any new event-producing code in later sprints.

---

## Sprint 2 — WhatsApp Channel, Notification Fan-out, Billing Foundation

**Theme:** Add the one missing delivery channel, generalize notifications from single-send to fan-out, and lay the billing/metering substrate the platform needs to be a business. All three extend existing substrate rather than replacing it.

### Objectives
- Make WhatsApp a first-class outbox channel, reusing the relay's reliability machinery (dedupe, backoff, dead-letter).
- Turn the per-message outbox into a notification fan-out so one domain event can reach multiple channels/recipients per org preference.
- Introduce a billing/plan/usage model so paid work (LLM qualification, message sends) can be metered and capped per org.

### Deliverables
- **`WHATSAPP` channel** (`app/core/enums.py` `OutboxChannel`): add the enum value — the documented extension point from `PRODUCT_REVIEW.md §1.3`. Add a `WhatsAppSender` adapter and a branch in `outbox_service._deliver` (currently EMAIL/WEBHOOK/IN_APP only). Add provider settings to `config.py` (`WHATSAPP_PROVIDER`, `WHATSAPP_API_KEY`, `WHATSAPP_FROM`) following the existing SMTP/webhook pattern.
- **`"whatsapp"` follow-up step action:** `SequenceStep.action` already gates behavior (`if step.action == "email"`); extend `_execute_followup_step` to enqueue a WhatsApp outbox message when `action == "whatsapp"` and the lead has a `phone`. Promote `SequenceStep.action` and the new channel to an enum (`PRODUCT_REVIEW.md §4.5`).
- **Inbound WhatsApp webhook** (`app/api/routes/ingestion.py` or a dedicated callback route): receive delivery receipts and inbound replies; on a reply, append a `LEAD_CONTACTED` timeline event and call `FollowUpService.cancel_for_lead` — closing the loop so a human reply stops the sequence (the cancellation machinery already exists).
- **Notification fan-out** (`app/services/notification_service.py`): generalize `enqueue_hot_lead_alert` into a `dispatch(ctx, notification_kind, entity_ref)` that consults per-org notification preferences and enqueues one outbox row per (channel, recipient). Today it hard-codes "email if SMTP configured, webhook if WEBHOOK_URL set"; this becomes data-driven. Add a `NotificationPreference` model (org/role/leak_type → channels).
- **Billing foundation** (`app/models/billing.py`, new): `Plan` (seat limit, leads/month quota, SLA-policy cap, enabled channels), `Subscription` (org → plan, status, period), `UsageRecord` (org, metric, count, period) — the model `PRODUCT_REVIEW.md §4.4` named as absent. Tenant-scoped like every other table.
- **Usage metering hooks:** increment `UsageRecord` for billable events — LLM qualification (in `process_lead_ai`) and outbound messages (in `outbox_service.relay_pending` on successful send). Enforce quota at ingestion (reject/queue over-quota leads) and surface remaining quota via a `GET /api/v1/billing/usage` route.
- **Plan-gated channels:** `outbox_service._deliver` (or enqueue) checks the org's plan enables the channel before sending — so WhatsApp can be a paid-tier feature.

### Risks
- **WhatsApp provider compliance.** WhatsApp Business messaging requires pre-approved templates and opt-in for business-initiated messages; a naive "send any body" sequence step will be rejected by the provider or flagged as spam. Mitigation: model template ids on `SequenceStep`, validate opt-in state on the lead before enqueueing, and treat provider rejections as dead-letter (not infinite retry) in the relay.
- **Billing correctness is unforgiving.** Double-counting usage (e.g. metering on outbox enqueue *and* send, or on a task retry) over- or under-charges. Mitigation: meter on the idempotent boundary only — successful relay send keyed by the outbox `dedupe_key`, never on enqueue; reuse the same exactly-once discipline the outbox already enforces.
- **Quota enforcement vs. paid-AI cost race.** A burst can drive LLM spend before the metering catches up if the check is post-hoc. Mitigation: check-and-reserve quota *before* `process_lead_ai.delay(...)`, atomically in Redis, so the ceiling is enforced at admission, not after spend.

### Dependencies
- **Sprint 1's rate limiter and ingestion route** — quota enforcement and WhatsApp inbound both hang off the mounted ingestion surface and the Redis limiter primitives.
- A WhatsApp Business provider account (Meta Cloud API or Twilio) with approved templates — external, lead-time-sensitive; start procurement at sprint open.
- The outbox relay (`relay_pending`) and dedupe machinery — already built; this sprint extends, doesn't replace.

---

## Sprint 3 — Analytics Depth, Dashboard, Team Collaboration

**Theme:** Turn the data the platform already captures into the dashboard the product promises, and mount the team-management surfaces the multi-user data model already supports. This is where the timeline (`events`) finally pays off as an analytics source.

### Objectives
- Replace the four-count dashboard with the revenue-recovery metrics the Phase 3 spec describes, computed without full-scanning the primary on every load.
- Mount the team/membership/invite/role-management routes that `PRODUCT_REVIEW.md §1.7` flagged as model-complete-but-unreachable.
- Make routing strategy configurable (beyond least-loaded round-robin).
- Re-baseline the frontend to the `/api/v1` surface with the dark-mode dashboard.

### Deliverables
- **Analytics service + read models** (`app/services/analytics_service.py`, new): compute **revenue at risk** (open `LeakAlert`s joined to `Opportunity.value_amount`), **response time** (time from `LEAD_INGESTED` to first `LEAD_ASSIGNED`/contact event in the timeline), **leads ignored / opportunities stalled** (open alert counts by type), **conversion** (`LeadStatus.CONVERTED` rate), and **team performance** (per-`owner_id`/`team_id` aggregates). These replace `LeadRepository.summary_counts`, which `PRODUCT_REVIEW.md §1.6` flagged as the entire current dashboard.
- **CQRS-lite refresh** (architecture review §7.2): a `metric_snapshots` table + a Beat task (`celery_app.py` beat_schedule) that refreshes per-org aggregates on an interval, plus short-TTL Redis caching of hot reads, so the dashboard does not full-scan `leads`/`opportunities`/`events` on every request. Add the supporting composite indexes the review specified (`(org_id, stage, updated_at)` etc.) where missing.
- **Dashboard route** (`app/api/routes/analytics.py`, new): `GET /api/v1/dashboard` returning the metric set, tenant-scoped.
- **Team management routes** (`app/api/routes/teams.py`, new): team CRUD, member invite (the flow `auth_service.signup` defers with "invited by an admin (Phase 6)"), role change (admin-gated via `require_admin`), member listing — all reusing the `Membership`/`Team`/`Role` models that already exist.
- **Configurable routing** (`app/services/routing_service.py`): extend behind the existing `assign_lead` interface with strategy selection (round-robin / by-territory / by-source), keyed off a `RoutingRule` model. The docstring already calls the current round-robin "a deliberately simple but real seam" — this realizes it without touching callers. Requires the typed `Lead.source` from below.
- **Typed `Lead.source`** (`app/core/enums.py` + migration): convert free-text `source` to a `LeadSource` enum so source-attribution analytics and source-based routing don't fragment on `"facebook"` vs `"fb"` (`PRODUCT_REVIEW.md §4.3`).
- **Frontend re-baseline** (`frontend/`): migrate the JSX prototype (`Login`/`Dashboard`/`ReviewQueue`/`LeadDetails`/`LeadTable`/`api.js`) to TypeScript + wired Tailwind + Shadcn, point `api.js` at `/api/v1`, add `AuthContext` + React Query + a 401 interceptor, dark mode, command palette, and loading/error states (Phase 8 UI spec). Wire the new dashboard and team screens. Stand up Vitest + Testing Library toward the 70% frontend gate.

### Risks
- **Timeline-based metrics are only as correct as event coverage.** Response-time accuracy depends on every contact actually appending a timeline event; any code path that mutates state without `timeline.append_event` produces wrong analytics. Mitigation: an invariant test that asserts each state-changing service method emits its event, and reconcile metric snapshots against live queries in a nightly check.
- **Snapshot staleness vs. freshness expectations.** A periodically-refreshed dashboard can show numbers that lag reality, confusing users watching a leak resolve. Mitigation: stamp `metric_snapshots.refreshed_at` and surface it in the UI; keep revenue-at-risk near-real-time (cheap) while heavier team aggregates refresh on a longer interval.
- **Frontend re-baseline is the largest single chunk and easy to under-scope.** Mitigation: treat the API-shape migration (old routes → `/api/v1`, token refresh flow) as the must-ship core; dark-mode/command-palette polish is the stretch, droppable without blocking the dashboard.

### Dependencies
- **Sprint 1's `EventType` enum and test harness** — analytics matches on event types, so they must be typed and tested first.
- **Sprint 2's billing model** — team-invite must respect the plan's seat limit, and the dashboard surfaces usage/quota from `UsageRecord`.
- Redis caching builds on the limiter's Redis usage from Sprint 1.

---

## Sprint 4 — Scale and Observability Maturity

**Theme:** Remove the structural ceilings `PRODUCT_REVIEW.md §3 and §5` identified — single queue, single primary, single region — and mature observability from "metrics exist" to "we get paged before the customer notices." This sprint is about operating the SLA engine at volume.

### Objectives
- Partition the async plane so paid lead work can't starve the SLA-critical dispatcher/relay/scanner.
- Add read-replica routing so analytics and the leak scanner stop contending with transactional writes on the primary.
- Make the leak scanner scale with tenant/entity count instead of full-sweeping.
- Lay multi-region seams without committing to a full multi-region deploy.
- Add error tracking, SLOs, and alerting-on-the-alerting-system.

### Deliverables
- **Queue partitioning** (`app/core/celery_app.py` `task_routes`): separate queues by workload class — `qualify` (paid LLM, bursty), `dispatch`/`relay`/`scan` (SLA-critical, must stay timely) — with dedicated workers, so a lead-ingestion spike no longer delays follow-ups (`PRODUCT_REVIEW.md §3.2`). Add per-queue Prometheus gauges (queue depth, task latency, outbox lag, scheduled-jobs backlog, scanner duration) per architecture review §10.
- **Read-replica routing** (`app/db/session.py`): a replica engine + a session/router that sends read-only work (analytics service, the leak scanner's `_breaching_entities` queries, dashboard reads) to a replica while writes stay on the primary. The `TenantRepository` read path is the natural injection point. Settings gain `DATABASE_REPLICA_URL` (optional; falls back to primary).
- **Scanner scalability** (`app/services/leak_detection.py`): replace the per-policy full table sweep with (a) tenant-batched scanning scheduled as `ScheduledJob` rows so the scan itself partitions across workers, and (b) eliminate the `PROPOSAL_COLD` N+1 by joining the timeline in one query (`NOT EXISTS` against `events`) instead of a per-proposal `SELECT`. Add a scanner-duration SLO and alert if a scan can't complete within its interval (architecture review §10).
- **Postgres Row-Level Security** (new migration): the defense-in-depth backstop the architecture review §7.1 recommended and `PRODUCT_REVIEW.md §5.3` flagged as still missing — RLS policies on tenant tables keyed off a session `org_id`, so even a hand-written query that forgets `.where(org_id == ...)` (as several scanner/raw queries do today) cannot leak across tenants.
- **Redis role expansion** (architecture review §7.3): move refresh-token revocation checks to a Redis denylist (relieving primary-DB load on every refresh), add the aggregate cache (Sprint 3) and idempotency-key store as first-class Redis uses rather than DB lookups.
- **Multi-region seams (designed, not fully deployed):** document and stub region affinity on `Organization` (a `region` column), confirm `org_id` row-scoping makes a future data-residency split mechanical, and ensure no cross-region assumptions are baked into the outbox/scheduler. Full multi-region deploy is explicitly deferred; the seam is the deliverable.
- **Error tracking + SLOs** (`app/core/observability.py`): Sentry (DSN already in `config.py` as `SENTRY_DSN`) on API and workers tagged with request id + org; define SLOs (outbox lag < N min, scanner within interval, p99 API latency) and alert rules. Distributed tracing (OpenTelemetry) across API→Celery→adapters as the stretch goal.

### Risks
- **Replica lag breaks read-after-write expectations.** A user creates a lead and the dashboard (reading the replica) doesn't show it yet. Mitigation: route only tolerant reads (analytics, scanner) to the replica; keep user-facing read-after-write paths (just-created entity fetch) on the primary, and document the routing rule explicitly.
- **RLS retrofit can silently break existing queries.** Enabling RLS without a correctly-set session `org_id` makes every query return zero rows — including the cross-tenant Beat tasks (scanner, dispatcher, relay) that legitimately operate across orgs. Mitigation: a `BYPASSRLS` service role for the async plane (which scopes by `org_id` in code), RLS enforced only on the request-path role, rolled out behind a flag with the Sprint 1 tenancy-isolation tests as the gate.
- **Queue partitioning changes deployment topology.** More worker pools means more to operate and monitor; a misconfigured route can silently drop a task class. Mitigation: a startup assertion that every registered task has a route, and per-queue depth alerts so a stalled pool pages immediately.

### Dependencies
- **Sprint 1's metrics/middleware** — SLOs and per-queue gauges build directly on the wired Prometheus layer; Sentry needs the request-id correlation.
- **Sprint 3's analytics read paths** — replica routing targets exactly those queries, so they must exist first.
- A provisioned read replica and (for the multi-region seam) a region-tagging decision from product — infrastructure lead time; flag at sprint open.

---

## Cross-sprint sequencing rationale

The order is deliberate and dependency-driven, not feature-priority-driven:

1. **Sprint 1 first** because nothing should be built on an untested, unobservable base — and because most of it is *finishing* wired-but-dark modules, it is the cheapest high-leverage sprint. The test harness and CI gate everything after it.
2. **Sprint 2 before Sprint 3** because billing/quota is foundational (like tenancy was in the audit): team seats and dashboard usage both read from the billing model, so it must exist before those surfaces.
3. **Sprint 3 before Sprint 4** because Sprint 4's replica routing and scanner optimization target the exact analytics/scanner read paths Sprint 3 creates — optimizing queries that don't exist yet is premature.
4. **Sprint 4 last** because scale work is invisible to a demo and only pays off under load; doing it earlier would be the "build on sand differently" trap the architecture review warned against.

Every sprint ships something runnable: Sprint 1 a hardened, tested, observable, CI-gated app with reachable ingestion; Sprint 2 WhatsApp + metered billing; Sprint 3 the real dashboard and team features; Sprint 4 the scale and observability maturity to operate it. That cadence keeps the Phase 9 deliverable (runnable, dockerized, production-ready, documented, tested) reachable incrementally rather than as a big-bang at the end.

---

*End of Implementation Plan. No code written.*
