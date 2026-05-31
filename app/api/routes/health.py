"""Health probes.

Separates liveness (is the process up?) from readiness (can it serve traffic —
DB + Redis reachable?). Load balancers and Kubernetes use these distinctly.
Phase 8 enriches readiness with broker checks and structured diagnostics.
"""

from __future__ import annotations

from fastapi import APIRouter, status
from fastapi.responses import JSONResponse
from sqlalchemy import text

from app.core.config import settings
from app.db.session import engine

router = APIRouter(tags=["Health"])


@router.get("/health")
@router.get("/health/live")
def liveness():
    """Liveness: the process is running. No external dependencies checked."""
    return {"status": "alive", "service": settings.APP_NAME}


@router.get("/health/ready")
@router.get("/health/readiness")
def readiness():
    """Readiness: dependencies reachable. Returns 503 if any check fails."""
    checks: dict[str, str] = {}
    healthy = True

    # Database
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        checks["database"] = "ok"
    except Exception as exc:  # noqa: BLE001
        checks["database"] = f"error: {type(exc).__name__}"
        healthy = False

    # Redis (broker / cache)
    try:
        import redis

        client = redis.from_url(settings.REDIS_URL, socket_connect_timeout=2)
        client.ping()
        checks["redis"] = "ok"
    except Exception as exc:  # noqa: BLE001
        checks["redis"] = f"error: {type(exc).__name__}"
        healthy = False

    body = {"status": "ready" if healthy else "not_ready", "checks": checks}
    if not healthy:
        return JSONResponse(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, content=body)
    return body
