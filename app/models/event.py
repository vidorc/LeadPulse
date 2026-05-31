"""Event — the immutable, append-only timeline.

The system of record for "what happened when" (architecture review §0, §5).
Generalizes the lead-only LeadEvent into a tenant-scoped log over any entity,
so Revenue Leak Detection and Analytics can both reason about transition
absence (e.g. "no contact event since created_at"). Rows are never updated
or deleted in normal operation.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import JSON, DateTime, Index, Integer, String
from sqlalchemy import Enum as SAEnum
from sqlalchemy.orm import Mapped, mapped_column

from app.core.enums import EntityType
from app.db.base_class import Base
from app.db.mixins import TenantMixin, utcnow


class Event(Base, TenantMixin):
    __tablename__ = "events"
    __table_args__ = (
        # Primary access pattern: a single entity's timeline in order, and
        # "latest event of type X for entity" staleness queries.
        Index("ix_events_entity", "entity_type", "entity_id", "occurred_at"),
        Index("ix_events_org_type_time", "org_id", "event_type", "occurred_at"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    entity_type: Mapped[EntityType] = mapped_column(
        SAEnum(EntityType, native_enum=False, length=20, validate_strings=True),
        nullable=False,
    )
    entity_id: Mapped[int] = mapped_column(Integer, nullable=False)
    event_type: Mapped[str] = mapped_column(String(64), nullable=False)
    payload: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    actor: Mapped[str | None] = mapped_column(String(255), nullable=True)
    occurred_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utcnow, index=True
    )
