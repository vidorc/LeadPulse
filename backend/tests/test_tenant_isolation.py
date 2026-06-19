"""Multi-tenancy isolation — the audit's headline finding (every user saw all
leads / IDOR). These tests assert org A can never see or touch org B's data."""

from __future__ import annotations

from tests.conftest import make_lead


def test_leads_isolated_between_orgs(client, org_a, org_b):
    headers_a, _ = org_a
    headers_b, _ = org_b
    make_lead(client, headers_a, email="a@buyer.co")
    # Org B sees none of org A's leads.
    assert client.get("/api/v1/leads/", headers=headers_b).json() == []


def test_cannot_read_other_orgs_lead_by_id(client, org_a, org_b):
    headers_a, _ = org_a
    headers_b, _ = org_b
    lead_id = make_lead(client, headers_a)
    # Direct-id access from the other org is a 404, not the record (no IDOR).
    assert client.get(f"/api/v1/leads/{lead_id}", headers=headers_b).status_code == 404


def test_cannot_read_other_orgs_opportunity(client, org_a, org_b):
    headers_a, _ = org_a
    headers_b, _ = org_b
    lead_id = make_lead(client, headers_a)
    opp_id = client.post(
        "/api/v1/opportunities/",
        headers=headers_a,
        json={"title": "Secret deal", "lead_id": lead_id},
    ).json()["id"]
    assert client.get(f"/api/v1/opportunities/{opp_id}", headers=headers_b).status_code == 404
    assert client.get("/api/v1/opportunities/", headers=headers_b).json() == []


def test_leak_alerts_isolated(client, org_a, org_b):
    headers_a, _ = org_a
    headers_b, _ = org_b
    make_lead(client, headers_a)
    client.put(
        "/api/v1/leak-detection/policies",
        headers=headers_a,
        json={"leak_type": "lead_ignored", "threshold_hours": 0, "severity": "high",
              "is_active": True, "notify": True},
    )
    client.post("/api/v1/leak-detection/scan", headers=headers_a)
    # Org B's scan sees no policies and no alerts from A.
    assert client.get("/api/v1/leak-detection/alerts", headers=headers_b).json() == []
