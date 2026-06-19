# LeadPulse — Local Development Setup

This guide takes you from a clean checkout to a running LeadPulse backend,
worker, scheduler, and frontend on your machine.

LeadPulse is a FastAPI + SQLAlchemy 2.0 backend with a Celery/Redis async plane,
PostgreSQL for storage, and a React + Vite frontend. The same configuration runs
locally and under Docker because connection URLs are derived from component
environment variables (see `backend/app/core/config.py`).

The repository is organized into `backend/` (the FastAPI app, tests, and
migrations), `frontend/` (the Vite app), `infra/` (docker-compose), and `docs/`.
Backend commands below are run from the `backend/` directory with the
repo-root virtualenv active.

---

## Prerequisites

| Tool | Version | Notes |
|------|---------|-------|
| Python | 3.12+ | The project pins a modern CPython; 3.12 or newer is required for the timezone-aware datetime usage and typing syntax. |
| Docker + Docker Compose | recent | Used to run PostgreSQL 15 and Redis 7 locally. You can also use a native install of each. |
| Node.js | 18+ | For the Vite frontend. |
| PostgreSQL client (optional) | 15 | `psql` is handy for inspecting the database. |

You do **not** need a local PostgreSQL or Redis install if you use the Docker
Compose services described below — only the data stores need to run; the API and
worker can run from your virtualenv against them.

---

## 1. Clone and create a virtualenv

```bash
git clone <your-fork-or-repo-url> LeadPulse
cd LeadPulse

python -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
```

## 2. Install dependencies

Install the development requirements — they include the runtime deps plus the
test and lint tooling. The Python project lives in `backend/`:

```bash
cd backend
pip install --upgrade pip
pip install -r requirements-dev.txt
```

`requirements-dev.txt` pulls in `requirements.txt` (FastAPI, SQLAlchemy, Alembic,
Celery, Redis, Groq/OpenAI clients, Argon2, structlog, prometheus-client) and
adds pytest, ruff, mypy, fakeredis, and friends.

## 3. Configure the environment

Copy the example file and edit it:

```bash
cp .env.example .env
```

For local development the defaults work as-is. The important variables:

- `APP_ENV=development` — keep this in development; production/staging triggers
  fail-fast secret validation (see DEPLOYMENT.md).
- `POSTGRES_*` — default to `postgres` / `postgres` / `leadpulse` on
  `localhost:5432`. `DATABASE_URL` is derived from these when left blank.
- `REDIS_*` — default to `localhost:6379/0`. `REDIS_URL` is derived likewise.
- `JWT_SECRET_KEY` — the dev default is fine locally; it is rejected in
  production.
- `GROQ_API_KEY` — needed for real LLM qualification. Without it, lead creation
  still works and the lead is persisted, but the AI enrichment step will fail
  inside the Celery task. Set a real key to exercise the full pipeline.

Generate a strong JWT secret when you want one:

```bash
python -c "import secrets; print(secrets.token_urlsafe(64))"
```

## 4. Start PostgreSQL and Redis

The compose file defines `postgres` (15) and `redis` (7) with health checks.
It lives in `infra/`. Start just those two services:

```bash
docker compose -f ../infra/docker-compose.yml up -d postgres redis
```

The database port is not published by default. If you want to reach Postgres
from your host (e.g. with `psql`), uncomment the `ports:` block under the
`postgres` service in `infra/docker-compose.yml`.

## 5. Apply database migrations

Alembic owns the schema. `alembic.ini` injects the database URL at runtime from
`app/core/config.py`, so no URL is hardcoded. Run from `backend/`:

```bash
alembic upgrade head
```

This applies three revisions in order:

1. `8aae99c81fe7` — initial schema: organizations, users, memberships, teams,
   leads, refresh_tokens, plus the workflow-engine tables (events, outbox,
   scheduled_jobs).
2. `b2f1c7d9e3a4` — revenue-recovery domain: opportunities, proposals, meetings,
   sequences, sequence_steps, enrollments, sla_policies, leak_alerts.
3. `c3a8e5f1d6b7` — ingestion columns: `organizations.ingest_secret` and
   `leads.idempotency_key`.

## 6. Run the API

```bash
uvicorn app.main:app --reload
```

The API serves on `http://localhost:8000`. Interactive docs are at
`http://localhost:8000/docs`. Health probes:

- `GET /health` / `GET /health/live` — liveness
- `GET /health/ready` / `GET /health/readiness` — readiness (checks DB + Redis)

## 7. Run the Celery worker and beat scheduler

The async plane drives the lead-qualification pipeline, the durable scheduler
(follow-up steps), the transactional outbox relay, and the leak scanner. Run the
worker and the beat scheduler in two more terminals (with the virtualenv active):

```bash
# Terminal A — worker
celery -A app.core.celery_app.celery worker --loglevel=info --concurrency=4

# Terminal B — beat (periodic scheduler)
celery -A app.core.celery_app.celery beat --loglevel=info
```

Beat fires three periodic tasks (defined in `app/core/celery_app.py`):

- `dispatch_scheduled_jobs` — every 60s (runs due follow-up steps)
- `relay_outbox` — every 30s (delivers queued email/webhook notifications)
- `scan_leaks` — every 300s (evaluates active SLA policies, raises leak alerts)

You need both the worker and beat running to see follow-up sequences advance and
leak alerts appear.

## 8. Run the frontend

```bash
cd frontend
npm install
npm run dev
```

Vite serves on `http://localhost:5173`, which is already in the default
`CORS_ORIGINS` list. The frontend talks to the API at `http://localhost:8000`.

---

## Running tests

Test tooling (pytest, pytest-cov, pytest-asyncio, factory-boy, freezegun,
fakeredis) is installed via `requirements-dev.txt`. Run the suite from the
`backend/` directory with the virtualenv active:

```bash
cd backend
pytest
```

The `backend/tests/` package is the home for the suite. `fakeredis` lets
rate-limit and broker-touching code run without a live Redis, and `freezegun` is
used to fast-forward time for SLA / scheduler tests.

Lint and type-check (also from `backend/`):

```bash
ruff check app tests
ruff format --check .
mypy app
```

---

## Common pitfalls

- **`GROQ_API_KEY` missing.** Lead creation returns 201 and the lead is stored,
  but the background `process_lead_ai` task cannot call the LLM. Set a real key,
  or expect the qualification step to fail in the worker log. The app only
  refuses to boot over a missing key when `APP_ENV` is production/staging.

- **Worker can't reach the database or Redis.** If you run the worker from your
  virtualenv, it uses `localhost` hosts from `.env`. Make sure the compose
  `postgres`/`redis` services are up (`docker compose -f infra/docker-compose.yml ps`).
  Inside containers the hosts are the service names `postgres`/`redis` — that
  override is handled in `infra/docker-compose.yml`, not `.env`.

- **Migrations not applied.** A fresh database has no tables; `/auth/signup` will
  fail on the first query. Always run `alembic upgrade head` after starting
  Postgres.

- **Follow-ups or leak alerts never appear.** These live entirely in the async
  plane. If beat or the worker is not running, scheduled jobs never dispatch and
  the SLA scanner never runs. Start both.

- **CORS errors from the frontend.** The frontend origin must be in
  `CORS_ORIGINS`. The defaults cover `http://localhost:5173` and
  `http://localhost:3000`; add others as a comma-separated list.

- **Port already in use.** `uvicorn` defaults to 8000 and Vite to 5173. Stop the
  conflicting process or pass `--port` to uvicorn / set `server.port` for Vite.
