"""Opportunity pipeline tests: create, stage transitions, proposals, meetings."""

from __future__ import annotations

from tests.conftest import make_lead


def _create_opp(client, headers, title="Big Deal", value=50000):
    lead_id = make_lead(client, headers)
    r = client.post(
        "/api/v1/opportunities/",
        headers=headers,
        json={"title": title, "lead_id": lead_id, "value_amount": value},
    )
    assert r.status_code == 201, r.text
    return r.json()["id"]


def test_create_opportunity_starts_new(client, auth_headers):
    opp_id = _create_opp(client, auth_headers)
    r = client.get(f"/api/v1/opportunities/{opp_id}", headers=auth_headers)
    assert r.status_code == 200
    assert r.json()["stage"] == "new"


def test_stage_transition_updates_stage(client, auth_headers):
    opp_id = _create_opp(client, auth_headers)
    r = client.post(
        f"/api/v1/opportunities/{opp_id}/stage",
        headers=auth_headers,
        json={"stage": "contacted"},
    )
    assert r.status_code == 200
    assert r.json()["stage"] == "contacted"


def test_stage_transition_appends_timeline_event(client, auth_headers, db):
    from app.core.enums import EntityType
    from app.services import timeline

    opp_id = _create_opp(client, auth_headers)
    client.post(
        f"/api/v1/opportunities/{opp_id}/stage",
        headers=auth_headers,
        json={"stage": "qualified"},
    )
    # The org for org_a is id 1 (first signup, truncate resets identity).
    events = timeline.timeline_for(
        db, org_id=1, entity_type=EntityType.OPPORTUNITY, entity_id=opp_id
    )
    types = {e.event_type for e in events}
    assert "OPPORTUNITY_CREATED" in types
    assert "STAGE_CHANGED" in types


def test_proposal_lifecycle(client, auth_headers):
    opp_id = _create_opp(client, auth_headers)
    r = client.post(
        f"/api/v1/opportunities/{opp_id}/proposals",
        headers=auth_headers,
        json={"title": "Quote", "amount": 5000},
    )
    assert r.status_code == 201, r.text
    prop_id = r.json()["id"]
    assert r.json()["status"] == "draft"

    sent = client.post(
        f"/api/v1/opportunities/proposals/{prop_id}/send", headers=auth_headers
    )
    assert sent.status_code == 200
    assert sent.json()["status"] == "sent"
    assert sent.json()["sent_at"] is not None


def test_meeting_lifecycle(client, auth_headers):
    opp_id = _create_opp(client, auth_headers)
    r = client.post(
        f"/api/v1/opportunities/{opp_id}/meetings",
        headers=auth_headers,
        json={"title": "Demo", "scheduled_at": "2026-06-01T15:00:00Z"},
    )
    assert r.status_code == 201, r.text
    mtg_id = r.json()["id"]
    assert r.json()["status"] == "scheduled"

    done = client.post(
        f"/api/v1/opportunities/meetings/{mtg_id}/complete", headers=auth_headers
    )
    assert done.status_code == 200
    assert done.json()["status"] == "completed"


def test_proposal_on_missing_opp_404(client, auth_headers):
    r = client.post(
        "/api/v1/opportunities/999999/proposals",
        headers=auth_headers,
        json={"title": "x"},
    )
    assert r.status_code == 404
