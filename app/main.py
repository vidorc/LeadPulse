"""LeadPulse FastAPI application entrypoint.

Routes are mounted under a central /api/v1 prefix. CORS origins come from
settings (no longer wildcard-open for a token-bearing API). Health probes are
wired via the health router (liveness/readiness) — Phase 8 expands these.
"""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.routes.auth import router as auth_router
from app.api.routes.health import router as health_router
from app.api.routes.leads import router as lead_router
from app.core.config import settings

app = FastAPI(
    title=settings.APP_NAME,
    version="0.1.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins_list,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type"],
)

# Health probes live at the root (load balancers expect /health/*).
app.include_router(health_router)

# Versioned API surface.
API_PREFIX = "/api/v1"
app.include_router(auth_router, prefix=API_PREFIX)
app.include_router(lead_router, prefix=API_PREFIX)


@app.get("/")
def root():
    return {"service": settings.APP_NAME, "status": "running", "docs": "/docs"}
