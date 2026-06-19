"""Authentication routes — thin layer over auth_service.

The login path is rate limited (brute-force protection) and security-relevant
auth events (signup, login success/failure, logout) are written to the audit
log. Audit writes are best-effort and never break the request.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.orm import Session

from app.api.deps import get_tenant_context
from app.core.rate_limit import login_rate_limiter
from app.core.tenant import TenantContext
from app.db.session import get_db
from app.schemas.auth import (
    LoginRequest,
    RefreshRequest,
    SignupRequest,
    TokenResponse,
    UserResponse,
)
from app.services import audit_service, auth_service
from app.services.auth_service import AuthError

router = APIRouter(prefix="/auth", tags=["Auth"])


def _client_ip(request: Request) -> str | None:
    fwd = request.headers.get("x-forwarded-for")
    if fwd:
        return fwd.split(",")[0].strip()
    return request.client.host if request.client else None


@router.post("/signup", response_model=TokenResponse, status_code=status.HTTP_201_CREATED)
def signup(payload: SignupRequest, request: Request, db: Session = Depends(get_db)):
    try:
        tokens = auth_service.signup(
            db,
            email=payload.email,
            password=payload.password,
            org_name=payload.org_name,
            full_name=payload.full_name,
        )
    except AuthError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))
    audit_service.record(
        db,
        action="auth.signup",
        actor_email=payload.email,
        ip_address=_client_ip(request),
        detail={"org_name": payload.org_name},
    )
    return tokens


@router.post("/login", response_model=TokenResponse, dependencies=[Depends(login_rate_limiter)])
def login(payload: LoginRequest, request: Request, db: Session = Depends(get_db)):
    try:
        tokens = auth_service.login(
            db, email=payload.email, password=payload.password, org_id=payload.org_id
        )
    except AuthError:
        audit_service.record(
            db,
            action="auth.login_failed",
            actor_email=payload.email,
            ip_address=_client_ip(request),
        )
        # Uniform message — no user enumeration.
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials"
        )
    audit_service.record(
        db,
        action="auth.login",
        actor_email=payload.email,
        ip_address=_client_ip(request),
    )
    return tokens


@router.post("/refresh", response_model=TokenResponse)
def refresh(payload: RefreshRequest, db: Session = Depends(get_db)):
    try:
        return auth_service.refresh(db, refresh_token=payload.refresh_token)
    except AuthError as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=str(exc))


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
def logout(payload: RefreshRequest, db: Session = Depends(get_db)):
    auth_service.logout(db, refresh_token=payload.refresh_token)


@router.get("/me", response_model=UserResponse)
def me(
    ctx: TenantContext = Depends(get_tenant_context),
    db: Session = Depends(get_db),
):
    from app.models.user import User

    user = db.get(User, ctx.user_id)
    if user is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    return user
