"""Timeline service — append and query the immutable Event log.

This is the single sanctioned way to write to / read from the timeline. Events
are appended within the caller's transaction (flush, not commit) so they land
atomically with the state change they record. Staleness queries
(`latest_event_at`) are what Revenue Leak Detection builds on.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.enums import EntityType
from app.models.event import Event


def append_event(
    db: Session,
    *,
    org_id: int,
    entity_type: EntityType,
    entity_id: int,
    event_type: str,
    payload: dict | None = None,
    actor: str | None = None,
    commit: bool = False,
) -> Event:
    """Append one immutable event. Does not commit by default (caller owns the
    transaction boundary)."""
    event = Event(
        org_id=org_id,
        entity_type=entity_type,
        entity_id=entity_id,
        event_type=event_type,
        payload=payload,
        actor=actor,
    )
    db.add(event)
    db.flush()
    if commit:
        db.commit()
    return event


def timeline_for(
    db: Session, *, org_id: int, entity_type: EntityType, entity_id: int
) -> list[Event]:
    stmt = (
        select(Event)
        .where(
            Event.org_id == org_id,
            Event.entity_type == entity_type,
            Event.entity_id == entity_id,
        )
        .order_by(Event.occurred_at.asc(), Event.id.asc())
    )
    return list(db.execute(stmt).scalars().all())


def latest_event_at(
    db: Session,
    *,
    org_id: int,
    entity_type: EntityType,
    entity_id: int,
    event_type: str | None = None,
) -> datetime | None:
    """Most recent occurred_at for an entity (optionally of a given type).
    Returns None if no matching event — the primitive leak detection uses to
    measure 'no transition within window'."""
    stmt = select(Event.occurred_at).where(
        Event.org_id == org_id,
        Event.entity_type == entity_type,
        Event.entity_id == entity_id,
    )
    if event_type is not None:
        stmt = stmt.where(Event.event_type == event_type)
    stmt = stmt.order_by(Event.occurred_at.desc()).limit(1)
    return db.execute(stmt).scalar_one_or_none()
