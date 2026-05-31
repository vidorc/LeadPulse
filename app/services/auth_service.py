"""Authentication & identity service.

Encapsulates the login / signup / refresh / logout flows so routes stay thin.
Tokens carry `sub` (user id) and `org_id` (active membership); the access
token is short-lived, the refresh token is persisted by `jti` for rotation
and server-side revocation.
"""

from __future__ import annotations

import re
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.enums import Role
from app.models.membership import Membership
from app.models.organization import Organization
from app.models.refresh_token import RefreshToken
from app.models.user import User
from app.services.security import (
    create_access_token,
    create_refresh_token,
    decode_token,
    hash_password,
    verify_password,
)


class AuthError(Exception):
    """Raised for any authentication/identity failure (routes map to 401/400)."""


def _slugify(name: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")
    return slug or "org"


def _issue_token_pair(db: Session, user: User, org_id: int) -> dict:
    # Role is intentionally NOT in the token — the auth pipeline resolves the
    # current role from the DB membership so revocations take effect immediately.
    access = create_access_token({"sub": str(user.id), "org_id": org_id})
    refresh, jti = create_refresh_token({"sub": str(user.id), "org_id": org_id})
    decoded = decode_token(refresh)
    db.add(
        RefreshToken(
            user_id=user.id,
            org_id=org_id,
            jti=jti,
            expires_at=datetime.fromtimestamp(decoded["exp"], tz=timezone.utc),
        )
    )
    return {"access_token": access, "refresh_token": refresh, "token_type": "bearer"}


def signup(db: Session, *, email: str, password: str, org_name: str, full_name: str | None = None) -> dict:
    """Bootstrap a new organization with its first OWNER user.

    This is the only path that creates an org; subsequent users are invited by
    an admin (Phase 6). The first user is always OWNER of the org they create.
    """
    existing = db.execute(select(User).where(User.email == email)).scalar_one_or_none()
    if existing is not None:
        raise AuthError("A user with this email already exists")

    org = Organization(name=org_name, slug=_unique_slug(db, org_name))
    db.add(org)
    db.flush()  # assign org.id

    user = User(email=email, hashed_password=hash_password(password), full_name=full_name)
    db.add(user)
    db.flush()  # assign user.id

    db.add(Membership(org_id=org.id, user_id=user.id, role=Role.OWNER))
    db.flush()

    tokens = _issue_token_pair(db, user, org.id)
    db.commit()
    return tokens


def _unique_slug(db: Session, name: str) -> str:
    base = _slugify(name)
    slug = base
    n = 1
    while db.execute(
        select(Organization).where(Organization.slug == slug)
    ).scalar_one_or_none() is not None:
        n += 1
        slug = f"{base}-{n}"
    return slug


def login(db: Session, *, email: str, password: str, org_id: int | None = None) -> dict:
    """Authenticate and issue tokens for the user's active org.

    If the user belongs to multiple orgs, `org_id` selects which; otherwise the
    sole membership is used.
    """
    user = db.execute(select(User).where(User.email == email)).scalar_one_or_none()
    # Always run a verify to keep timing uniform (avoid user-enumeration).
    if user is None:
        verify_password(password, hash_password("dummy"))
        raise AuthError("Invalid credentials")
    if not user.is_active or user.deleted_at is not None:
        raise AuthError("Invalid credentials")
    if not verify_password(password, user.hashed_password):
        raise AuthError("Invalid credentials")

    memberships = db.execute(
        select(Membership).where(
            Membership.user_id == user.id, Membership.deleted_at.is_(None)
        )
    ).scalars().all()
    if not memberships:
        raise AuthError("User has no active organization membership")

    if org_id is not None:
        membership = next((m for m in memberships if m.org_id == org_id), None)
        if membership is None:
            raise AuthError("User is not a member of the requested organization")
    else:
        membership = memberships[0]

    return _issue_token_pair(db, user, membership.org_id)


def refresh(db: Session, *, refresh_token: str) -> dict:
    """Rotate a refresh token: validate, revoke the old jti, issue a new pair."""
    try:
        payload = decode_token(refresh_token)
    except Exception as exc:  # noqa: BLE001
        raise AuthError("Invalid refresh token") from exc
    if payload.get("type") != "refresh":
        raise AuthError("Wrong token type")

    jti = payload.get("jti")
    record = db.execute(
        select(RefreshToken).where(RefreshToken.jti == jti)
    ).scalar_one_or_none()
    if record is None or record.revoked:
        raise AuthError("Refresh token revoked or unknown")
    if record.expires_at < datetime.now(timezone.utc):
        raise AuthError("Refresh token expired")

    user = db.get(User, record.user_id)
    if user is None or not user.is_active or user.deleted_at is not None:
        raise AuthError("User inactive")

    record.revoked = True  # rotation: old token can't be reused
    tokens = _issue_token_pair(db, user, record.org_id)
    db.commit()
    return tokens


def logout(db: Session, *, refresh_token: str) -> None:
    """Revoke a refresh token (best-effort; idempotent)."""
    try:
        payload = decode_token(refresh_token)
    except Exception:  # noqa: BLE001
        return
    record = db.execute(
        select(RefreshToken).where(RefreshToken.jti == payload.get("jti"))
    ).scalar_one_or_none()
    if record is not None:
        record.revoked = True
        db.commit()
