#!/usr/bin/env bash
# Container entrypoint: wait for the database, apply migrations, then exec the
# given command. Used by the API and worker containers so schema is always
# current before the app serves traffic. Migrations are idempotent and safe to
# run from every container (Alembic serializes via the alembic_version table).
set -euo pipefail

echo "[entrypoint] waiting for database to accept connections..."
python - <<'PY'
import time
import sys
from sqlalchemy import create_engine, text
from app.core.config import settings

url = settings.DATABASE_URL
for attempt in range(60):
    try:
        engine = create_engine(url, pool_pre_ping=True)
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        print(f"[entrypoint] database reachable after {attempt}s")
        break
    except Exception as exc:  # noqa: BLE001
        if attempt == 59:
            print(f"[entrypoint] database unreachable: {exc}", file=sys.stderr)
            sys.exit(1)
        time.sleep(1)
PY

# Only the API container should drive migrations to avoid races; workers wait
# for the schema to exist. RUN_MIGRATIONS defaults to "true".
if [ "${RUN_MIGRATIONS:-true}" = "true" ]; then
    echo "[entrypoint] applying database migrations..."
    alembic upgrade head
fi

echo "[entrypoint] starting: $*"
exec "$@"
