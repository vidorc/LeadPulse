"""Lead capture + qualification surface tests."""

from __future__ import annotations

from tests.conftest import make_lead


def test_create_and_get_lead(client, auth_headers):
    lead_id = make_lead(client, auth_headers)
    r = client.get(f"/api/v1/leads/{lead_id}", headers=auth_headers)
    assert r.status_code == 200
    assert r.json()["name"] == "Jane"


def test_list_leads_scoped_to_org(client, auth_headers):
    make_lead(client, auth_headers, email="a@buyer.co")
    make_lead(client, auth_headers, email="b@buyer.co")
    r = client.get("/api/v1/leads/", headers=auth_headers)
    assert r.status_code == 200
    assert len(r.json()) == 2


def test_get_missing_lead_404(client, auth_headers):
    r = client.get("/api/v1/leads/999999", headers=auth_headers)
    assert r.status_code == 404


def test_dashboard_summary_shape(client, auth_headers):
    make_lead(client, auth_headers)
    r = client.get("/api/v1/leads/dashboard/summary", headers=auth_headers)
    assert r.status_code == 200
    assert isinstance(r.json(), dict)


def test_lead_events_timeline(client, auth_headers):
    lead_id = make_lead(client, auth_headers)
    r = client.get(f"/api/v1/leads/{lead_id}/events", headers=auth_headers)
    assert r.status_code == 200
    assert isinstance(r.json(), list)
