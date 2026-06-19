"""Password hashing and JWT token handling.

Secrets come exclusively from `settings` (the single trust root) — no
hardcoded keys. Passwords use Argon2id (memory-hard, per-password salt by
construction), replacing the previous unsalted SHA-256 which was vulnerable
to rainbow-table and GPU brute-force attacks.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError, VerificationError, InvalidHashError
from jose import jwt

from app.core.config import settings

# Argon2id with library defaults (sensible memory/time cost for an API).
_password_hasher = PasswordHasher()


def hash_password(password: str) -> str:
    """Return an Argon2id hash (salt embedded in the encoded string)."""
    return _password_hasher.hash(password)


def verify_password(password: str, hashed: str) -> bool:
    """Constant-time-ish verification; never raises on a bad password."""
    if not hashed:
        return False
    try:
        return _password_hasher.verify(hashed, password)
    except (VerifyMismatchError, VerificationError, InvalidHashError):
        return False


def needs_rehash(hashed: str) -> bool:
    """True if a stored hash should be upgraded (cost params changed)."""
    try:
        return _password_hasher.check_needs_rehash(hashed)
    except (InvalidHashError, Exception):  # noqa: BLE001 - defensive
        return True


def _now() -> datetime:
    return datetime.now(timezone.utc)


def create_access_token(
    data: dict,
    expires_minutes: int | None = None,
) -> str:
    """Mint a short-lived access token."""
    to_encode = data.copy()
    expire = _now() + timedelta(
        minutes=expires_minutes or settings.ACCESS_TOKEN_EXPIRE_MINUTES
    )
    to_encode.update(
        {
            "exp": expire,
            "iat": _now(),
            "type": "access",
            "jti": uuid.uuid4().hex,
        }
    )
    return jwt.encode(
        to_encode,
        settings.JWT_SECRET_KEY,
        algorithm=settings.JWT_ALGORITHM,
    )


def create_refresh_token(data: dict) -> tuple[str, str]:
    """Mint a refresh token. Returns (token, jti) so the jti can be persisted
    for server-side revocation."""
    jti = uuid.uuid4().hex
    to_encode = data.copy()
    expire = _now() + timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS)
    to_encode.update(
        {
            "exp": expire,
            "iat": _now(),
            "type": "refresh",
            "jti": jti,
        }
    )
    token = jwt.encode(
        to_encode,
        settings.JWT_SECRET_KEY,
        algorithm=settings.JWT_ALGORITHM,
    )
    return token, jti


def decode_token(token: str) -> dict:
    """Decode and verify a token's signature and expiry. Raises jose.JWTError
    on any failure (caller maps to 401)."""
    return jwt.decode(
        token,
        settings.JWT_SECRET_KEY,
        algorithms=[settings.JWT_ALGORITHM],
    )
