# LeadPulse — Production Deployment

This guide covers deploying LeadPulse with Docker Compose (or any container
orchestrator built from the same image), the environment contract the app
enforces, secrets handling, migrations, health-check wiring, scaling, backups,
and rollback.

The deployable unit is one image (`backend/docker/Dockerfile`) run in three
roles: the **API** (Gunicorn + Uvicorn workers), the **Celery worker**, and
**Celery beat**. All three share the same code and configuration.

---

## The environment contract

Configuration is centralized in `app/core/config.py`. Every secret and tunable
enters there from the environment — nothing is hardcoded. `DATABASE_URL` and
`REDIS_URL` are **derived** from their component variables when left blank, so
the same image works locally and in-cluster by only changing the host vars.

### Fail-fast secret validation

When `APP_ENV` is one of `production`, `prod`, or `staging`, the app refuses to
boot if any of the following is insecure or missing:

| Variable | Rejected when | Why |
|----------|---------------|-----|
| `JWT_SECRET_KEY` | empty, or one of the known dev sentinels (`dev-only-insecure-key-change-me`, `super-secret-key-change-this`, `change-me-in-production`, `changeme`, `postgres`) | a shared/guessable signing key means forgeable tokens |
| `POSTGRES_PASSWORD` | empty or one of the same sentinels (including `postgres`) | default DB creds are a takeover risk |
| `GROQ_API_KEY` | empty | the LLM qualification path is non-functional without it |

If any fail, startup raises a `ValueError` listing the offending variables and
the process exits. This is intentional: a misconfigured production deploy should
never come up half-secured.

### Variables you MUST set in production

```bash
APP_ENV=production
JWT_SECRET_KEY=<64+ random chars>          # python -c "import secrets; print(secrets.token_urlsafe(64))"
POSTGRES_PASSWORD=<strong unique password>
GROQ_API_KEY=<your Groq key>
```

### Variables you should review

| Variable | Default | Production guidance |
|----------|---------|---------------------|
| `POSTGRES_USER` / `POSTGRES_DB` | `postgres` / `leadpulse` | set per your DB provisioning |
| `POSTGRES_HOST` / `POSTGRES_PORT` | `localhost` / `5432` | point at your managed DB or the `postgres` service |
| `REDIS_HOST` / `REDIS_PORT` / `REDIS_DB` | `localhost` / `6379` / `0` | point at your managed Redis or the `redis` service |
| `DATABASE_URL` / `REDIS_URL` | derived | set explicitly only if you need a non-standard DSN (e.g. TLS params) |
| `ACCESS_TOKEN_EXPIRE_MINUTES` | `15` | short-lived access tokens |
| `REFRESH_TOKEN_EXPIRE_DAYS` | `14` | refresh-token lifetime (server-side revocable) |
| `CORS_ORIGINS` | localhost dev origins | set to your real frontend origin(s), comma-separated. Do not use `*` for a token-bearing API |
| `LOG_LEVEL` | `INFO` | |
| `RATE_LIMIT_LOGIN_PER_MINUTE` | `10` | brute-force protection budget |
| `RATE_LIMIT_INGEST_PER_MINUTE` | `60` | ingestion abuse budget |
| `SMTP_*` | Gmail placeholders | set for outbound follow-up email delivery |
| `WEBHOOK_URL` | empty | outbound webhook channel target, if used |
| `SENTRY_DSN` | empty | optional error reporting |

---

## Secrets management

- Never bake secrets into the image or commit a real `.env`. `.env` is for local
  development only.
- Inject `JWT_SECRET_KEY`, `POSTGRES_PASSWORD`, and `GROQ_API_KEY` via your
  platform's secret store (Kubernetes Secrets, AWS Secrets Manager / SSM, Docker
  secrets, etc.) and expose them as environment variables to the containers.
- Rotate `JWT_SECRET_KEY` deliberately: rotating it invalidates all existing
  access and refresh tokens (every signature stops verifying), forcing re-login.
  Plan rotations during low-traffic windows.
- Passwords are hashed with Argon2id (`app/services/security.py`), so a database
  dump does not expose plaintext credentials — but the DB password and JWT key
  still must be protected as top-tier secrets.

---

## Running migrations on deploy

The container entrypoint (`docker/entrypoint.sh`) waits for the database to
accept connections, then runs `alembic upgrade head` before starting the
process — but only when `RUN_MIGRATIONS=true`.

To avoid races where multiple containers migrate simultaneously:

- The **API** container sets `RUN_MIGRATIONS=true` and owns migrations.
- The **worker** and **beat** containers set `RUN_MIGRATIONS=false`; they wait
  for the schema to exist but never drive it.

Alembic serializes via its `alembic_version` table, so even if two containers
attempted it, only one revision application would win — but the explicit split
keeps startup clean. If you orchestrate migrations as a separate one-shot job
(common in Kubernetes), run `alembic upgrade head` in an init job and set
`RUN_MIGRATIONS=false` everywhere.

---

## Docker Compose deployment

`infra/docker-compose.yml` defines five services: `postgres` (15), `redis` (7),
`backend` (API), `celery_worker`, and `celery_beat`. The worker/beat/backend all
build from `backend/docker/Dockerfile` (the compose build context is `backend/`).
Service-name hosts (`postgres`, `redis`) and blanked `DATABASE_URL`/`REDIS_URL`
force in-network URL derivation.

```bash
# Provide production env (secret-managed backend/.env or injected vars)
docker compose -f infra/docker-compose.yml build
docker compose -f infra/docker-compose.yml up -d
```

Startup ordering is enforced with health checks and `depends_on:
condition: service_healthy`, so the API and workers only start once Postgres and
Redis report healthy. The API container's own health check polls
`/health/live`.

The default API command (from the Dockerfile) is:

```
gunicorn app.main:app \
  --worker-class uvicorn.workers.UvicornWorker \
  --workers 4 --bind 0.0.0.0:8000 \
  --access-logfile - --error-logfile - --timeout 60
```

---

## Health checks for load balancers and Kubernetes

The app separates liveness from readiness (`app/api/routes/health.py`):

| Probe | Path(s) | Behavior | Use for |
|-------|---------|----------|---------|
| Liveness | `/health`, `/health/live` | always 200 if the process is up; no dependency checks | k8s `livenessProbe`, LB "is the process alive" |
| Readiness | `/health/ready`, `/health/readiness` | checks Postgres (`SELECT 1`) and Redis (`PING`); returns **200** when both are reachable, **503** otherwise with a per-check breakdown | k8s `readinessProbe`, LB "should I route traffic here" |

Key principle: do not gate liveness on dependencies. If readiness used the DB
and the DB blips, a liveness-gated pod would be killed and restarted in a loop.
Wire liveness to `/health/live` and readiness to `/health/ready`.

Example Kubernetes snippet:

```yaml
livenessProbe:
  httpGet: { path: /health/live, port: 8000 }
  initialDelaySeconds: 15
  periodSeconds: 15
readinessProbe:
  httpGet: { path: /health/ready, port: 8000 }
  initialDelaySeconds: 10
  periodSeconds: 10
```

---

## Observability

The observability stack under `app/core/` is wired into the application at
startup (`app/main.py` calls `configure_logging()`, adds
`RequestContextMiddleware`, registers the global exception handlers, and mounts
`/metrics`):

- **Structured logging** (`logging.py`): `configure_logging()` sets up structlog
  with JSON output (machine-parseable) in production and a console renderer in
  development, binding a per-request `request_id` into every log line.
- **Request middleware** (`middleware.py`): `RequestContextMiddleware` mints/
  propagates an `X-Request-ID`, emits a structured access-log line per request,
  and records Prometheus request count + latency keyed by the matched route
  template (low cardinality).
- **Prometheus metrics** (`metrics.py`): counters/histograms namespaced
  `leadpulse_*` (`leadpulse_http_requests_total`,
  `leadpulse_http_request_duration_seconds`, `leadpulse_rate_limited_total`,
  `leadpulse_leak_alerts_created_total`) plus a `render_latest()` helper for a
  `/metrics` scrape endpoint.
- **Rate limiting** (`rate_limit.py`): a fixed-window limiter keyed by client +
  scope, backed by Redis (atomic `INCR`+`EXPIRE`, shared across workers) with an
  in-process fallback. Fail-open on backend errors so a limiter outage never
  takes the API down. `login_rate_limiter` is attached to `POST /auth/login`
  today; `ingest_rate_limiter` is built and sized by the `RATE_LIMIT_*` env vars,
  ready for the ingestion route. Rejections return HTTP 429 with a `Retry-After`
  header.

The metrics endpoint and access logging are live on every request. When you
scrape metrics, point Prometheus at the `/metrics` path (it is excluded from the
access-log/metric self-instrumentation). Logs are emitted to stdout (JSON in
production), so ship them with your platform's log collector.

---

## Scaling

- **API workers.** The image runs Gunicorn with 4 Uvicorn workers by default.
  Size workers to roughly `2 * cores + 1` for the API container, and run
  multiple API replicas behind a load balancer for horizontal scale. The stack
  is synchronous SQLAlchemy, so concurrency is bounded by workers × pool size.
- **Database connection pool** (`app/db/session.py`): `pool_size=10`,
  `max_overflow=20`, `pool_pre_ping=True` (recovers stale connections after a DB
  restart), `pool_recycle=1800`. Total possible connections ≈
  `(pool_size + max_overflow) × worker_count × replica_count`. Keep this under
  your Postgres `max_connections`; use a pooler like PgBouncer if you scale wide.
- **Celery worker.** Scale `celery_worker` replicas / `--concurrency` for
  throughput on lead qualification, follow-up step execution, outbox delivery,
  and leak scans. The worker uses `task_acks_late=True` and
  `worker_prefetch_multiplier=1` (configured in `app/core/celery_app.py`) so a
  dying worker redelivers in-flight tasks and one worker can't hoard the queue.
- **Celery beat.** Run **exactly one** beat instance. Beat only emits the
  periodic triggers (dispatch scheduled jobs, relay outbox, scan leaks); running
  two would double-fire schedules. The actual work is claimed with
  `FOR UPDATE SKIP LOCKED`, so multiple *workers* are safe — but only one *beat*.

---

## Backups

- **PostgreSQL is the system of record** (leads, opportunities, the immutable
  event timeline, outbox, scheduled jobs, auth). Take regular `pg_dump` /
  managed snapshots and test restores. Under Compose, data persists in the
  `postgres_data` volume — back up the underlying volume or dump from inside.
- **Redis** is the Celery broker/result backend and the rate-limit store. It is
  largely reconstructable: with `appendonly yes` (set in compose) it survives
  restarts, but losing it only loses in-flight task messages and rate-limit
  windows — not durable business state, which lives in Postgres (the outbox and
  scheduled_jobs tables make delivery and scheduling durable independently of
  Redis).

---

## Rollback

Application rollback is a redeploy of the previous image tag. Schema rollback is
an Alembic downgrade:

```bash
# Roll back one revision
alembic downgrade -1

# Roll back to a specific revision
alembic downgrade b2f1c7d9e3a4
```

The three migrations are linear:
`8aae99c81fe7` → `b2f1c7d9e3a4` → `c3a8e5f1d6b7`. Each `downgrade()` drops the
tables/columns it added.

Cautions:
- Downgrades are destructive — `downgrade()` drops tables and columns, losing the
  data in them. Take a backup first.
- Roll the application image back **before** (or together with) a schema
  downgrade so the running code matches the schema it expects.
- The ingestion migration's `ingest_secret` backfill is forward-only; a
  downgrade simply drops the column.
