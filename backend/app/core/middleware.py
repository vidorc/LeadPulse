"""HTTP middleware: request context, access logging, and metrics.

One middleware does three correlated jobs per request so they share the same
timing and request id:
  * mint/propagate an ``X-Request-ID`` and bind it to the logging context,
  * time the request and emit a structured access log line,
  * record Prometheus request count + latency.

The route path is taken from the matched route template (e.g.
``/api/v1/leads/{lead_id}``) rather than the raw URL, so high-cardinality IDs
don't explode the metrics label space.
"""

from __future__ import annotations

import time
import uuid

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

from app.core.logging import get_logger, request_id_ctx
from app.core.metrics import REQUEST_COUNT, REQUEST_LATENCY

log = get_logger("http")

_REQUEST_ID_HEADER = "X-Request-ID"


def _route_template(request: Request) -> str:
    """Low-cardinality path for metrics: the matched route template if any."""
    route = request.scope.get("route")
    if route is not None and getattr(route, "path", None):
        return route.path
    return request.url.path


class RequestContextMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next) -> Response:
        # Reuse an inbound request id (from a proxy/gateway) or mint one.
        request_id = request.headers.get(_REQUEST_ID_HEADER) or uuid.uuid4().hex
        token = request_id_ctx.set(request_id)
        start = time.perf_counter()
        status_code = 500
        try:
            response = await call_next(request)
            status_code = response.status_code
            return response
        finally:
            elapsed = time.perf_counter() - start
            path = _route_template(request)
            # Skip self-instrumentation noise for the scrape endpoint.
            if path != "/metrics":
                REQUEST_COUNT.labels(
                    method=request.method, path=path, status=str(status_code)
                ).inc()
                REQUEST_LATENCY.labels(method=request.method, path=path).observe(elapsed)
                log.info(
                    "http_request",
                    method=request.method,
                    path=path,
                    status=status_code,
                    duration_ms=round(elapsed * 1000, 2),
                    client=request.client.host if request.client else None,
                )
            # response may not exist if call_next raised; set header when it does
            if "response" in locals():
                response.headers[_REQUEST_ID_HEADER] = request_id
            request_id_ctx.reset(token)
