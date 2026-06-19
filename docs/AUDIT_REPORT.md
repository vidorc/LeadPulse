# LeadPulse — Repository Audit Report

**Date:** 2026-05-31
**Auditors:** Founding engineering team review (Backend, Frontend, Data/Architecture, QA, Security, DevOps)
**Scope:** Full repository — backend, frontend, models, schemas, services, tasks, database, docker, tests, configuration.
**Method:** Four parallel domain audits, each finding independently verified against the source tree with read-only commands.

---

## Executive Summary

LeadPulse today is an **early prototype of a single happy-path lead-qualification pipeline**, not a production SaaS. The core async flow (capture a lead → Groq LLM qualifies it → score/route/decide → notify) is coherent and is the strongest part of the codebase. Everything around it — version control hygiene, secrets, the data model, multi-tenancy, the headline product features, the frontend stack, and tests — is either missing, broken, or unsafe for production.

The single most urgent issue is **repository hygiene**: 99.5% of committed files are a checked-in virtualenv, while most of the actual application source is *not* committed at all. The repo does not currently reflect the running app.

The product gap is equally stark: LeadPulse is positioned as a **"Revenue Leak Detection + Follow-Up Intelligence"** platform, but the two features that define that positioning — the **Follow-Up Engine** and **Revenue Leak Detection** — do not exist in the data model or the code. They are string stubs.

**Verdict:** Not production-ready. Requires a foundational pass (hygiene + secrets + data model + tenancy) before feature work, then the core product features must be built largely from scratch.

### Severity tally

| Severity | Count | Theme |
|---|---|---|
| 🔴 Critical | 15 | Repo hygiene, leaked secrets, no tenancy, missing core features, broken deploy path, zero tests |
| 🟠 Important | 22 | AuthZ depth, rate limiting, data modeling, frontend UX/stack, task safety |
| 🟢 Nice-to-have | 9 | Deprecations, dead code, style modernization |

---

## What Exists

**Backend (FastAPI)**
- App entrypoint `app/main.py` with CORS + two routers (`auth`, `leads`) and inline `/` and `/health`.
- Pydantic v2 settings via `pydantic-settings` (`app/core/config.py`) — correctly using `SettingsConfigDict`.
- Celery app wired to Redis broker+backend (`app/core/celery_app.py`), including the task module.
- SQLAlchemy 2.0 sync engine + `get_db` dependency (`app/db/session.py`).
- JWT auth: login route, token creation, password hashing, an auth dependency, and an admin guard.
- Three models: `User`, `Lead`, `LeadEvent`.
- A qualification pipeline of services: `ai_qualifier` (Groq) → `scoring_guardrails` → `review_router` → `decision_engine` → `action_router` → `notification_service`/`email_service`, plus `audit_logger`.
- One Celery task `process_lead_ai`, dispatched on lead creation via `.delay()`.

**Frontend (React)**
- Vite + React 19 + react-router-dom 7 + axios.
- Four pages (`Login`, `Dashboard`, `ReviewQueue`, `LeadDetails`) + one `LeadTable` component.
- An axios instance with a request interceptor that attaches the bearer token.
- Routing wired with a `localStorage`-token `ProtectedRoute`.

**Infra**
- Single-stage `docker/Dockerfile`, `docker-compose.yml` (backend, postgres:15, redis:7, celery_worker, celery_beat), `.env`, pinned `requirements.txt`, `.gitignore`.

---

## What Works

- The **happy-path qualification pipeline is genuinely coherent** and fully wired end to end (`app/tasks/lead_tasks.py`). This is the asset to build on.
- The **async-offload architecture is correct**: `POST /leads` creates the row and offloads AI work to Celery (`leads.py:38`) — the right call for a paid external LLM dependency.
- `decision_engine.decide_lead_action` and `review_router.requires_review` are clean, pure, deterministic functions — trivially unit-testable.
- Pydantic v2 settings loading is correct, and `.env` is gitignored (and confirmed not tracked).
- Login query uses parameterized ORM filters — no SQL injection there.
- `get_db` closes sessions in a `finally`.
- Frontend routing works and the API endpoints the frontend calls **do line up** with real backend routes.
- The app **does import cleanly** under `.venv` (`.venv/bin/python -c "import app.main"` → exit 0). *Note: a fresh `pip install -r requirements.txt` would fail — see Critical #8.*

---

## What Is Broken

### 🔴 Critical

1. **The repository is a committed virtualenv.** `git ls-files` tracks **3,165 files; 3,149 are inside `.venv/`** (99.5%). Only **16 real source files** are tracked. The `.gitignore` ignores `venv/` but not `.venv/`. The committed env is platform-specific (`python3.14`, `*.cpython-314-x86_64-linux-gnu.so`) and already out of sync with disk.

2. **Most of the running app is NOT committed.** Untracked-but-on-disk: `app/api/routes/auth.py`, `app/models/user.py`, `app/models/lead_event.py`, `app/models/__init__.py`, `app/schemas/auth.py`, `app/schemas/lead_event.py`, and **all of `app/services/*`**. The repo does not represent the application.

3. **No schema creation path.** No `alembic.ini`, no migrations dir, no `Base.metadata.create_all()` anywhere (`alembic==1.18.4` is in requirements but unused). Against a fresh Postgres the `users`/`leads`/`lead_events` tables never exist, so `/auth/login` fails on first query.

4. **`requirements.txt` does not match the runtime.** Imports require `pydantic-settings`, `python-jose`, `groq`, `openai`, and a password lib — **none are in `requirements.txt`**. A clean `pip install` (i.e. the Docker build) yields `ModuleNotFoundError`. It only runs locally because the untracked `.venv` already has them.

5. **Containers can't reach their dependencies.** `DATABASE_URL`/`REDIS_URL` hardcode `localhost` (`.env`), but compose runs DB/Redis as services `postgres`/`redis`. The `.env` defines `POSTGRES_HOST=postgres`/`REDIS_HOST=redis` but `config.py` never uses them.

6. **Duplicate route registrations.** `/review-queue` is defined **3×** (`leads.py:116,143,170`) and `/dashboard/summary` **3×** (`leads.py:128,155,182`) with identical bodies — a botched copy/paste leaving dead, confusing registrations.

7. **`normalize_score` crashes on a null/non-string budget** (`scoring_guardrails.py:8`, `budget.lower()`). Since the LLM can return `budget` as a number or `null`, this raises `AttributeError` and kills the Celery task — then burns all 3 retries.

8. **Celery task is not idempotent or retry-safe** (`lead_tasks.py`). With `autoretry_for=(Exception,)`, external side effects (email/webhook in `execute_action`) fire **before** `db.commit()`; any later failure re-runs the whole task → **duplicate emails/notifications** and multiplied `LeadEvent` audit rows. No `db.rollback()` on error. A missing LLM key (`KeyError`) retries pointlessly instead of failing fast.

### 🟠 Important

9. **`override_lead` returns HTTP 200 on not-found** (`leads.py:62-63`) — returns `{"error": ...}` instead of raising `404`. Clients can't tell success from failure.
10. **AI output is trusted without validation** (`lead_tasks.py:50-66`): keys like `ai_result["score"]` accessed directly; a missing/typed-wrong key throws. `qualify_lead` also doesn't strip markdown ```json fences, so common llama3 responses fall into the generic fallback.
11. **`health.py` router is dead code** — never included in `main.py`; the inline `/health` does no DB/Redis readiness check.
12. **`LeadTable` renders booleans as blank cells** (`LeadTable.jsx:30`) — React renders booleans as nothing, so the Status column is always empty.
13. **No global 401 handling on the frontend** — `api.js` has only a request interceptor; an expired token never clears storage or redirects.
14. **Login UX broken** — no `<form>` (no Enter-to-submit), surfaces `err.message` not the backend detail, no loading/disabled state, and **prefills real-looking credentials** (`Login.jsx:8-9`).

### 🟢 Nice-to-have

15. `app/models/__init__.py` imports `LeadEvent` twice; `app/db/base.py` only registers `Base` + `Lead` (omits `User`, `LeadEvent`).
16. `LeadEventResponse.details: str` is non-optional but the column is nullable → Pydantic serialization error on null.
17. Deprecated `datetime.utcnow()` used throughout (naive timestamps; deprecated on Python 3.14).

---

## Missing Features (vs. product requirements)

> These are the gaps between the prototype and the stated product. Several are the *defining* features of LeadPulse.

### 🔴 Critical

- **Follow-Up Engine — absent.** No `FollowUp`/`Sequence`/`Reminder`/`ScheduledTask` model. The Day 1/3/7/14 sequences and escalation rules don't exist; `action_router` just returns strings like `"Follow-up scheduled"` with nothing behind them. No `celery beat` schedule exists (the `celery_beat` container runs but has no periodic tasks).
- **Revenue Leak Detection — absent.** Nothing detects ignored leads, stalled opportunities, missed meetings, or unfollowed proposals. There is no `updated_at`/state-history to even query against. **This is the headline product feature and it is unimplemented.**
- **No multi-tenancy.** No `Organization`/`Team` models, no `org_id`/`owner_id`/`team_id` anywhere. Team Management (orgs, teams, users) does not exist.
- **No role model.** Required Owner/Admin/Manager/Agent roles don't exist; `User.role` is free-text and `require_admin` only checks the literal `"admin"`.
- **Frontend stack does not meet spec** (see Architectural Problems): no TypeScript, Tailwind unwired, Shadcn absent, no command palette, no loading/error states.

### 🟠 Important

- **Lead Capture is single-channel** — only a generic `POST /leads`. No Facebook Leads, Google Forms, CSV upload, or signed webhook ingestion. `source` is an unconstrained string.
- **Lead Routing absent** — no assignment to user/team, no routing by location/workload/rules.
- **No Opportunity / Proposal / Meeting entities** — there is no pipeline object to stall or recover, which the product is built around.
- **Qualification gaps** — has intent/budget/urgency but **no `timeline`**, and `budget` is a String (can't be range-queried or scored numerically).
- **Dashboard is thin** — only total/hot/manual-review counts; spec requires opportunities, revenue at risk, response times, conversion metrics, team performance. This is a full-stack gap (backend `dashboard/summary` only supplies the three counts).
- **Frontend premium UX missing** — no real dark mode toggle, no keyboard shortcuts, weak accessibility (placeholder-as-label, clickable `<tr>` with no keyboard role), not responsive, `LeadDetails` shows a timeline but never the lead's actual data.

### 🟢 Nice-to-have

- No logout flow; no `VITE_*` env for API base URL; debug `console.log`s left in `Dashboard.jsx`.

---

## Security Problems

### 🔴 Critical

- **Hardcoded live secrets in source** (verified, values masked):
  - Groq API key — `app/services/ai_qualifier.py:5`
  - Gmail address + app password — `app/services/email_service.py:12-13`
  - JWT signing key `SECRET_KEY = "super-secret-key-change-this"` — `app/services/security.py:5` (identical across all deploys → forgeable tokens; not sourced from settings)
  - **All must be rotated immediately**, even though `.env` itself is gitignored — these are in `.py` files.
- **Unsalted SHA-256 password hashing** (`security.py:11`). Fast, no per-user salt, rainbow-table-vulnerable. Needs bcrypt/argon2 (not even installed).
- **No tenancy isolation — every authenticated user sees all data.** `get_leads` does `db.query(Lead).all()` with no scope (`leads.py:48`); `override_lead` and `get_lead_events` look up by raw id with no ownership check → **IDOR**: any logged-in user can read/modify any lead and read any lead's history.
- **`POST /leads` is unauthenticated, unvalidated, unrated** (`leads.py:21-40`). Because it triggers a **paid** `process_lead_ai.delay()`, anonymous traffic directly drives Groq spend — a cost-amplification / DoS vector.

### 🟠 Important

- **RBAC trusts only token claims.** `get_current_user` returns the decoded JWT verbatim without confirming the user still exists/is active; role changes and deactivations don't take effect until the 60-min token expires.
- **No refresh tokens, no logout/revocation/blacklist** — single 60-min access token; no rotation story. Frontend stores it in `localStorage` (XSS-exfiltration risk).
- **No rate limiting anywhere** — `/auth/login` is open to credential stuffing/brute force.
- **CORS fully open** — `allow_origins/methods/headers=["*"]` (`main.py`), overly permissive for a token-bearing SaaS.
- **Weak input typing** — `email` fields are bare `str` not `EmailStr`; no password policy; email content interpolated unescaped into outbound mail.
- **Placeholder webhook** `https://webhook.site/YOUR-ID` (`notification_service.py:4`) — if ever pointed at a real bin, leaks lead PII to a third party.

### 🟢 Nice-to-have

- JWT lacks `iss`/`aud`/`nbf` claims and leeway controls.

---

## Scalability Problems

### 🟠 Important

- **No DB pool tuning** (`session.py:6`): default pool, no `pool_pre_ping` (stale connections after DB restart raise), no `pool_recycle`, no explicit sizing.
- **Single sync uvicorn process** (`Dockerfile:10`) on a synchronous SQLAlchemy stack — hard concurrency cap. Needs Gunicorn + uvicorn workers.
- **Celery underconfigured** — no `task_serializer`, `result_expires`, `acks_late`, prefetch limits, or `beat_schedule`. `celery_beat` runs but does nothing.
- **No indexes / constraints / `updated_at` / soft-delete.** Only PKs + `users.email` unique. `LeadEvent.lead_id` FK has no index and no `ondelete`; dashboard status/decision filters full-scan. **No `updated_at` means leak detection has nothing to query.**

### 🟢 Nice-to-have

- Redis result backend with no `result_expires` accumulates keys over time.

---

## Architectural Problems

### 🔴 Critical

- **The data model cannot support the product.** With no org/team/owner FKs, multi-tenancy and routing can't be retrofitted without a schema rewrite + backfill. This is foundational, not incremental.
- **Frontend is the wrong baseline.** 100% `.jsx`/`.js` (no `tsconfig`, 0 TS files) against a required TS stack; **Tailwind installed but completely unwired** (no `tailwind.config`/`postcss.config`/`@tailwind` directives); **Shadcn not installed** (no `cmdk`, `cva`, `tailwind-merge`, Radix, `components.json`). Styling is bespoke global CSS that will fight any component library.

### 🟠 Important

- **Config split across two mechanisms** — env-driven `config.py` vs hardcoded module globals in `security.py`. Secrets belong in `Settings`.
- **Two virtualenvs on disk** (`.venv` and `venv`) with mismatched, futuristic pins; the runtime truth diverges from `requirements.txt`. No single reproducible dependency source.
- **Booleans/enums modeled as strings** — `requires_human_review` holds `"yes"/"no"`; `status`/`decision`/`urgency`/`intent` are unconstrained strings with magic values scattered across services (typos fail silently in dashboard filters).
- **Module-level external-client init** — `Groq(...)` constructed at import (`ai_qualifier.py:4`), so importing requires the key and makes the pipeline untestable without network mocking.
- **No state management / shared auth context on frontend** — token read from `localStorage` in three places; each page re-implements fetch-into-`useState`; no React Query/SWR, no `AuthContext`.
- **Errors swallowed with `print`** in `notification_service` — partial failures report success strings, no structured trace.

### 🟢 Nice-to-have

- Routers wired ad hoc with no `/api/v1` prefix or central API router; mix of inline + included endpoints.
- Schemas use deprecated `class Config: from_attributes` instead of `model_config = ConfigDict(...)`.
- `openai` installed but unused (only Groq is used).
- `audit_logger.log_event` only `db.add`s (no flush/commit) — unsafe to reuse outside its single caller.

---

## Testing

### 🔴 Critical

- **Zero automated tests** despite an 80%/70% requirement. `tests/` is empty. `test_email.py` is a side-effecting script that **sends a real email on run**, not a test.
- **No test tooling** — `pytest`/`pytest-cov`/`pytest-asyncio` absent from `requirements.txt`; no `vitest`/`@testing-library` in `frontend/package.json`. `pytest --collect-only` → `No module named pytest`.

### 🟠 Important

- **No CI** — no `.github/workflows`, no coverage gates, no `conftest.py`/fixtures, no Celery `task_always_eager` test config.

---

## Refactoring Recommendations (ranked)

### 🔴 Critical — do first, in order

1. **Fix version control hygiene.** `git rm -r --cached .venv venv`, add both to `.gitignore`, then **commit the untracked real source** (`app/services/*`, models, schemas, routes). Get the repo to reflect the app.
2. **Rotate every leaked secret** (Groq key, Gmail app password, JWT key) and move all secrets into `Settings`/env; inject clients rather than constructing at import.
3. **Replace SHA-256 with bcrypt/argon2** (`passlib[bcrypt]`), add to deps.
4. **Regenerate `requirements.txt` from the real runtime**; pick one virtualenv, delete the other; pin everything.
5. **Introduce Alembic** (init + initial migration); run migrations on deploy; stop relying on implicit table creation.
6. **Fix container connectivity** — derive URLs from `POSTGRES_HOST`/`REDIS_HOST` service names.
7. **Introduce core entities** — `Organization`, `Team`, `Membership` + role enum, `Opportunity`, `FollowUp`/`Sequence`, `Meeting`/`Proposal`; add `org_id`/`owner_id`/`team_id` to `Lead`. **Prerequisite for tenancy, routing, follow-ups, and leak detection.**
8. **Enforce tenancy at the query layer** — a dependency that scopes every query to the caller's `org_id`, plus per-object ownership checks. Add auth + rate limiting (or signed ingestion) to `POST /leads`.
9. **Make `process_lead_ai` idempotent/retry-safe** — validate AI output with a Pydantic model, narrow `autoretry_for` to transient errors, move side effects after commit (or guard with a processed-state check), add `db.rollback()`.
10. **Stand up the test harness** — add backend test tooling + `--cov-fail-under=80`; add Vitest + Testing Library + 70% gate; seed unit tests for the pure functions, an integration test for `process_lead_ai` with `task_always_eager`, and API tests.
11. **Re-baseline the frontend** — migrate to TypeScript, properly install/configure Tailwind + Shadcn, type API responses from the OpenAPI schema.

### 🟠 Important

12. Delete the duplicate route blocks; fix `override_lead` to raise `404`; remove/convert `test_email.py`.
13. Harden the DB engine (`pool_pre_ping`, `pool_recycle`, sizing); run Gunicorn + uvicorn workers; configure Celery properly + define the follow-up `beat_schedule`.
14. Lock down CORS; add `EmailStr` + input constraints; re-fetch user + check `is_active`/role from DB in `get_current_user`; add refresh-token + revocation flow.
15. Replace string flags with enums; add `updated_at`, soft-delete, and indexes on `lead.status`, `lead.decision`, `lead_event.lead_id`; switch to timezone-aware UTC timestamps.
16. Frontend: React Query + `AuthContext`, response interceptor for 401, env-driven base URL, loading/error/empty states, command palette + shortcuts, accessible forms/tables, responsive layout, build out the Dashboard metrics (coordinated with a backend expansion).
17. Dockerfile multi-stage + non-root `USER`; compose `healthcheck`s + `depends_on: service_healthy`; drop broad bind mount in prod; remove default `postgres/postgres` creds.

### 🟢 Nice-to-have

18. `/api/v1` prefix + central API router; migrate schemas to `ConfigDict`; remove unused `openai`; make `audit_logger` commit explicitly; fix deprecated `datetime.utcnow()`; make `LeadEventResponse.details` optional; dedupe model imports.

---

## Appendix — verification commands run

```
git ls-files | grep -c '\.venv/'        # 3149
git ls-files | wc -l                     # 3165
grep -n '@router' app/api/routes/leads.py    # review-queue ×3, dashboard/summary ×3
find . -maxdepth 2 -name 'alembic*'      # (none outside venv); no alembic.ini
.venv/bin/python -c "import app.main"    # exit 0 (imports under venv)
```

Secrets confirmed present in `ai_qualifier.py:5`, `email_service.py:12-13`, `security.py:5`, `notification_service.py:4` (values masked in this report).
