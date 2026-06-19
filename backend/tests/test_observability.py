"""Production hardening tests: request id, error envelope, metrics, rate limit."""

from __future__ import annotations


def test_health_live(client):
    r = client.get("/health/live")
    assert r.status_code == 200
    assert r.json()["status"] == "alive"


def test_request_id_header_present(client):
    r = client.get("/health/live")
    assert r.headers.get("X-Request-ID")


def test_request_id_is_propagated(client):
    rid = "test-correlation-123"
    r = client.get("/health/live", headers={"X-Request-ID": rid})
    assert r.headers.get("X-Request-ID") == rid


def test_error_envelope_shape_on_404(client, auth_headers):
    r = client.get("/api/v1/leads/999999", headers=auth_headers)
    assert r.status_code == 404
    body = r.json()
    assert "error" in body
    assert body["error"]["type"] == "http_error"
    assert "request_id" in body["error"]


def test_validation_error_envelope(client):
    r = client.post("/api/v1/auth/signup", json={"email": "not-an-email"})
    assert r.status_code == 422
    assert r.json()["error"]["type"] == "validation_error"


def test_metrics_endpoint_exposes_prometheus(client):
    # Generate at least one request so a counter exists.
    client.get("/health/live")
    r = client.get("/metrics")
    assert r.status_code == 200
    assert "leadpulse_http_requests_total" in r.text


def test_rate_limiter_blocks_after_limit():
    """Drive the limiter directly with a tiny window (functional tests run with
    the limit effectively disabled, so exercise it in isolation here)."""
    from app.core import rate_limit

    limiter = rate_limit.RateLimiter(scope="unit", limit=3, window_seconds=60)

    class _Req:
        headers = {}

        class client:  # noqa: N801
            host = "10.0.0.1"

    req = _Req()
    # First 3 allowed, 4th rejected.
    for _ in range(3):
        limiter(req)
    try:
        limiter(req)
        raised = False
    except Exception as exc:  # HTTPException
        raised = getattr(exc, "status_code", None) == 429
    assert raised
