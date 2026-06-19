"""LeadPulse FastAPI application entrypoint.

Routes are mounted under a central /api/v1 prefix. CORS origins come from
settings (no longer wildcard-open for a token-bearing API). Health probes are
wired via the health router (liveness/readiness).

Production concerns are assembled here: structured logging is configured at
import, every request flows through RequestContextMiddleware (request id +
access log + metrics), uncaught errors are normalized by the global exception
handlers, and Prometheus metrics are exposed at /metrics.
"""

from __future__ import annotations

from fastapi import FastAPI, Response
from fastapi.middleware.cors import CORSMiddleware

from app.api.routes.auth import router as auth_router
from app.api.routes.follow_ups import router as follow_up_router
from app.api.routes.health import router as health_router
from app.api.routes.leads import router as lead_router
from app.api.routes.leak_detection import router as leak_router
from app.api.routes.opportunities import router as opportunity_router
from app.core.config import settings
from app.core.exceptions import register_exception_handlers
from app.core.logging import configure_logging, get_logger
from app.core.metrics import render_latest
from app.core.middleware import RequestContextMiddleware

# Configure logging before anything else logs. JSON in prod, console in dev.
configure_logging(level=settings.LOG_LEVEL, json_logs=settings.is_production)
log = get_logger(__name__)

app = FastAPI(
    title=settings.APP_NAME,
    version="0.1.0",
)

# Order matters: context middleware wraps the whole stack so request id +
# metrics cover every response, including CORS preflight.
app.add_middleware(RequestContextMiddleware)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins_list,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type", "X-Request-ID"],
)

register_exception_handlers(app)

# Health probes live at the root (load balancers expect /health/*).
app.include_router(health_router)

# Versioned API surface.
API_PREFIX = "/api/v1"
app.include_router(auth_router, prefix=API_PREFIX)
app.include_router(lead_router, prefix=API_PREFIX)
app.include_router(opportunity_router, prefix=API_PREFIX)
app.include_router(follow_up_router, prefix=API_PREFIX)
app.include_router(leak_router, prefix=API_PREFIX)


@app.get("/metrics", include_in_schema=False)
def metrics():
    """Prometheus scrape endpoint."""
    payload, content_type = render_latest()
    return Response(content=payload, media_type=content_type)


@app.get("/")
def root():
    return {"service": settings.APP_NAME, "status": "running", "docs": "/docs"}


@app.on_event("startup")
def _startup():
    log.info(
        "app.startup",
        env=settings.APP_ENV,
        version="0.1.0",
        cors_origins=settings.cors_origins_list,
    )
