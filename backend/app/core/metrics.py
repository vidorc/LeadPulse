"""Prometheus metrics.

Exposes counters/histograms for HTTP traffic plus a few domain gauges. The
``/metrics`` endpoint (mounted in app.main) is scraped by Prometheus. Metric
names follow the ``leadpulse_*`` convention so they namespace cleanly.
"""

from __future__ import annotations

from prometheus_client import CONTENT_TYPE_LATEST, Counter, Histogram, generate_latest

REQUEST_COUNT = Counter(
    "leadpulse_http_requests_total",
    "Total HTTP requests.",
    ["method", "path", "status"],
)

REQUEST_LATENCY = Histogram(
    "leadpulse_http_request_duration_seconds",
    "HTTP request latency in seconds.",
    ["method", "path"],
    buckets=(0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0),
)

RATE_LIMITED = Counter(
    "leadpulse_rate_limited_total",
    "Requests rejected by the rate limiter.",
    ["scope"],
)

LEAK_ALERTS_CREATED = Counter(
    "leadpulse_leak_alerts_created_total",
    "Leak alerts raised by the SLA scanner.",
    ["leak_type"],
)


def render_latest() -> tuple[bytes, str]:
    """Return (payload, content_type) for the /metrics endpoint."""
    return generate_latest(), CONTENT_TYPE_LATEST
