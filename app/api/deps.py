"""API dependency chain — the 4-stage authorization pipeline.

Every protected request flows through:
  1. authenticate   — verify JWT signature + expiry (decode_token)
  2. resolve tenant — load the user + active membership from the DB
                      (NOT trusting stale token claims for role/active state)
  3. scope          — build the TenantContext injected into services/repos
  4. authorize      — role / permission checks (require_role helpers)

No protected endpoint may skip stages 2-4. This closes the audit's "trusts
only token claims" and "every user sees all leads / IDOR" findings.
"""

from __future__ import annotations

from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from jose import JWTError
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.enums import Role
from app.core.tenant import TenantContext
from app.db.session import get_db
from app.models.membership import Membership
from app.models.user import User
from app.services.security import decode_token

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/v1/auth/login")

_CREDENTIALS_EXC = HTTPException(
    status_code=status.HTTP_401_UNAUTHORIZED,
    detail="Could not validate credentials",
    headers={"WWW-Authenticate": "Bearer"},
)


def get_tenant_context(
    token: str = Depends(oauth2_scheme),
    db: Session = Depends(get_db),
) -> TenantContext:
    """Stages 1-3: authenticate, resolve tenant from the DB, build the scope."""
    # ---- Stage 1: authenticate ----
    try:
        payload = decode_token(token)
    except JWTError:
        raise _CREDENTIALS_EXC
    if payload.get("type") != "access":
        raise _CREDENTIALS_EXC

    user_id = payload.get("sub")
    org_id = payload.get("org_id")
    if user_id is None or org_id is None:
        raise _CREDENTIALS_EXC

    # ---- Stage 2: resolve tenant (DB-backed, not trusting token claims) ----
    try:
        user_id_int = int(user_id)
        org_id_int = int(org_id)
    except (TypeError, ValueError):
        raise _CREDENTIALS_EXC

    user = db.get(User, user_id_int)
    if user is None or not user.is_active or user.deleted_at is not None:
        # Deactivated/deleted users are rejected immediately, not at token expiry.
        raise _CREDENTIALS_EXC

    membership = db.execute(
        select(Membership).where(
            Membership.user_id == user_id_int,
            Membership.org_id == org_id_int,
            Membership.deleted_at.is_(None),
        )
    ).scalar_one_or_none()
    if membership is None:
        # User is no longer a member of this org → no access.
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="No active membership for this organization",
        )

    # ---- Stage 3: scope ----
    return TenantContext(
        org_id=org_id_int,
        user_id=user_id_int,
        email=user.email,
        role=membership.role,  # current role from DB, not the token
    )


# ---- Stage 4: authorize (role gates) ----
def require_role(minimum: Role):
    """Dependency factory enforcing a minimum role."""

    def _guard(ctx: TenantContext = Depends(get_tenant_context)) -> TenantContext:
        try:
            ctx.require_role(minimum)
        except PermissionError as exc:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc))
        return ctx

    return _guard


require_admin = require_role(Role.ADMIN)
require_manager = require_role(Role.MANAGER)
