"""Revenue leak detection tests: policies, scan, alert idempotency, resolve."""

from __future__ import annotations

from tests.conftest import make_lead


def _set_policy(client, headers, leak_type="lead_ignored", threshold=0):
    return client.put(
        "/api/v1/leak-detection/policies",
        headers=headers,
        json={
            "leak_type": leak_type,
            "threshold_hours": threshold,
            "severity": "high",
            "is_active": True,
            "notify": True,
        },
    )


def test_upsert_policy_creates_then_updates(client, auth_headers):
    r1 = _set_policy(client, auth_headers, threshold=24)
    assert r1.status_code == 200
    assert r1.json()["threshold_hours"] == 24
    # Upsert again with a new threshold — same row, updated.
    r2 = _set_policy(client, auth_headers, threshold=48)
    assert r2.status_code == 200
    assert r2.json()["threshold_hours"] == 48

    listing = client.get("/api/v1/leak-detection/policies", headers=auth_headers)
    assert len([p for p in listing.json() if p["leak_type"] == "lead_ignored"]) == 1


def test_scan_raises_alert_for_ignored_lead(client, auth_headers):
    make_lead(client, auth_headers)  # status NEW, created just now
    _set_policy(client, auth_headers, threshold=0)  # anything older than now breaches
    r = client.post("/api/v1/leak-detection/scan", headers=auth_headers)
    assert r.status_code == 200, r.text
    assert r.json()["alerts_created"] >= 1

    alerts = client.get("/api/v1/leak-detection/alerts", headers=auth_headers)
    assert alerts.status_code == 200
    assert len(alerts.json()) >= 1
    assert alerts.json()[0]["leak_type"] == "lead_ignored"


def test_scan_is_idempotent(client, auth_headers):
    make_lead(client, auth_headers)
    _set_policy(client, auth_headers, threshold=0)
    first = client.post("/api/v1/leak-detection/scan", headers=auth_headers).json()
    second = client.post("/api/v1/leak-detection/scan", headers=auth_headers).json()
    assert first["alerts_created"] >= 1
    # Second scan must not duplicate the open alert.
    assert second["alerts_created"] == 0


def test_resolve_alert(client, auth_headers):
    make_lead(client, auth_headers)
    _set_policy(client, auth_headers, threshold=0)
    client.post("/api/v1/leak-detection/scan", headers=auth_headers)
    alert_id = client.get("/api/v1/leak-detection/alerts", headers=auth_headers).json()[0]["id"]

    r = client.post(f"/api/v1/leak-detection/alerts/{alert_id}/resolve", headers=auth_headers)
    assert r.status_code == 200
    assert r.json()["status"] == "resolved"
    assert r.json()["resolved_at"] is not None


def test_resolve_missing_alert_404(client, auth_headers):
    r = client.post("/api/v1/leak-detection/alerts/999999/resolve", headers=auth_headers)
    assert r.status_code == 404
