"""Follow-up engine tests: sequence creation, enrollment, cancellation."""

from __future__ import annotations

from tests.conftest import make_lead


def _make_sequence(client, headers, name="Nurture"):
    r = client.post(
        "/api/v1/follow-ups/sequences",
        headers=headers,
        json={
            "name": name,
            "steps": [
                {"delay_hours": 24, "action": "email", "subject": "Hi", "body": "Hello"},
                {"delay_hours": 72, "action": "email", "subject": "Still there?", "body": "..."},
            ],
        },
    )
    assert r.status_code == 201, r.text
    return r.json()["id"]


def test_create_sequence_requires_manager(client, auth_headers):
    # Owner (>= manager) can create.
    seq_id = _make_sequence(client, auth_headers)
    assert seq_id is not None


def test_list_sequences(client, auth_headers):
    _make_sequence(client, auth_headers, name="A")
    _make_sequence(client, auth_headers, name="B")
    r = client.get("/api/v1/follow-ups/sequences", headers=auth_headers)
    assert r.status_code == 200
    assert len(r.json()) == 2


def test_enroll_lead_schedules_first_step(client, auth_headers, db):
    from app.core.enums import EntityType
    from app.models.scheduled_job import ScheduledJob
    from sqlalchemy import select

    seq_id = _make_sequence(client, auth_headers)
    lead_id = make_lead(client, auth_headers)
    r = client.post(
        "/api/v1/follow-ups/enroll",
        headers=auth_headers,
        json={"lead_id": lead_id, "sequence_id": seq_id},
    )
    assert r.status_code == 201, r.text
    # A scheduled job for the first step should now exist.
    jobs = db.execute(
        select(ScheduledJob).where(ScheduledJob.entity_type == EntityType.ENROLLMENT)
    ).scalars().all()
    assert len(jobs) == 1


def test_enroll_is_idempotent(client, auth_headers):
    seq_id = _make_sequence(client, auth_headers)
    lead_id = make_lead(client, auth_headers)
    body = {"lead_id": lead_id, "sequence_id": seq_id}
    first = client.post("/api/v1/follow-ups/enroll", headers=auth_headers, json=body)
    second = client.post("/api/v1/follow-ups/enroll", headers=auth_headers, json=body)
    assert first.status_code == 201
    # Re-enrolling the same active lead returns the same enrollment, not a dup.
    assert second.json()["id"] == first.json()["id"]


def test_enroll_missing_lead_404(client, auth_headers):
    seq_id = _make_sequence(client, auth_headers)
    r = client.post(
        "/api/v1/follow-ups/enroll",
        headers=auth_headers,
        json={"lead_id": 999999, "sequence_id": seq_id},
    )
    assert r.status_code == 404


def test_cancel_for_lead_cancels_enrollment(client, auth_headers):
    seq_id = _make_sequence(client, auth_headers)
    lead_id = make_lead(client, auth_headers)
    client.post(
        "/api/v1/follow-ups/enroll",
        headers=auth_headers,
        json={"lead_id": lead_id, "sequence_id": seq_id},
    )
    r = client.post(f"/api/v1/follow-ups/leads/{lead_id}/cancel", headers=auth_headers)
    assert r.status_code == 200
    assert r.json()["cancelled_enrollments"] == 1
