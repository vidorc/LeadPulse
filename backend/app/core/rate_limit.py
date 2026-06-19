"""Rate limiting.

A fixed-window limiter keyed by client identity + scope. Backed by Redis in
production (atomic INCR + EXPIRE, shared across workers); falls back to an
in-process counter when Redis is unavailable so local dev and tests work
without a broker. Fail-open on backend errors — a limiter outage must not take
the API down, it just stops limiting.

Used for the auth login path (brute-force protection) and the ingestion path
(abuse protection). The dependency raises HTTP 429 with a Retry-After header.
"""

from __future__ import annotations

import time
from collections import defaultdict

from fastapi import HTTPException, Request, status

from app.core.config import settings
from app.core.logging import get_logger
from app.core.metrics import RATE_LIMITED

log = get_logger(__name__)

# Lazily-created Redis client (None until first use / if unavailable).
_redis_client = None
_redis_unavailable = False

# In-process fallback: {key: (window_start_epoch, count)}.
_local_buckets: dict[str, tuple[int, int]] = defaultdict(lambda: (0, 0))


def _get_redis():
    global _redis_client, _redis_unavailable
    if _redis_unavailable:
        return None
    if _redis_client is None:
        try:
            import redis

            _redis_client = redis.from_url(
                settings.REDIS_URL, socket_connect_timeout=1, socket_timeout=1
            )
            _redis_client.ping()
        except Exception as exc:  # noqa: BLE001
            log.warning("rate_limiter.redis_unavailable", error=str(exc))
            _redis_unavailable = True
            _redis_client = None
    return _redis_client


def _client_id(request: Request) -> str:
    """Best-effort client identity. Honors X-Forwarded-For first hop when
    present (behind a trusted proxy), else the socket peer."""
    fwd = request.headers.get("x-forwarded-for")
    if fwd:
        return fwd.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


def _hit(key: str, limit: int, window_seconds: int) -> tuple[bool, int]:
    """Register a hit. Returns (allowed, retry_after_seconds)."""
    client = _get_redis()
    if client is not None:
        try:
            count = client.incr(key)
            if count == 1:
                client.expire(key, window_seconds)
            if count > limit:
                ttl = client.ttl(key)
                return False, max(int(ttl), 1)
            return True, 0
        except Exception as exc:  # noqa: BLE001 — fail open
            log.warning("rate_limiter.redis_error", error=str(exc))
            return True, 0

    # In-process fallback (single worker; best-effort).
    now = int(time.time())
    window_start, count = _local_buckets[key]
    if now - window_start >= window_seconds:
        _local_buckets[key] = (now, 1)
        return True, 0
    count += 1
    _local_buckets[key] = (window_start, count)
    if count > limit:
        return False, window_seconds - (now - window_start)
    return True, 0


class RateLimiter:
    """FastAPI dependency enforcing ``limit`` requests per ``window_seconds``
    per client, namespaced by ``scope``."""

    def __init__(self, *, scope: str, limit: int, window_seconds: int = 60):
        self.scope = scope
        self.limit = limit
        self.window_seconds = window_seconds

    def __call__(self, request: Request) -> None:
        key = f"rl:{self.scope}:{_client_id(request)}"
        allowed, retry_after = _hit(key, self.limit, self.window_seconds)
        if not allowed:
            RATE_LIMITED.labels(scope=self.scope).inc()
            log.warning("rate_limited", scope=self.scope, client=_client_id(request))
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail="Rate limit exceeded. Try again later.",
                headers={"Retry-After": str(retry_after)},
            )


login_rate_limiter = RateLimiter(
    scope="login", limit=settings.RATE_LIMIT_LOGIN_PER_MINUTE, window_seconds=60
)
ingest_rate_limiter = RateLimiter(
    scope="ingest", limit=settings.RATE_LIMIT_INGEST_PER_MINUTE, window_seconds=60
)
