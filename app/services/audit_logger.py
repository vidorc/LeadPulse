"""Append a LeadEvent to the timeline.

Tenant-aware (org_id is required) and flushes so the row gets an id, but does
NOT commit — the caller owns the transaction boundary so the event is written
atomically with the state change it records. Use ``commit=True`` only when
calling outside an existing transaction.
"""

from __future__ import annotations

from sqlalchemy.orm import Session

from app.models.lead_event import LeadEvent


def log_event(
    db: Session,
    *,
    org_id: int,
    lead_id: int,
    event_type: str,
    details: str | None = None,
    actor: str | None = None,
    commit: bool = False,
) -> LeadEvent:
    event = LeadEvent(
        org_id=org_id,
        lead_id=lead_id,
        event_type=event_type,
        details=details,
        actor=actor,
    )
    db.add(event)
    db.flush()
    if commit:
        db.commit()
    return event
