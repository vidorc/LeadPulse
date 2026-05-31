"""LeadEvent — per-lead audit trail.

Tenant-scoped and with an indexed FK (the audit found lead_id unindexed and
without ondelete). In Phase 5 this is generalized into the immutable `events`
timeline that leak detection reads; for now it remains the lead-scoped log.
"""

from __future__ import annotations

from sqlalchemy import ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base_class import Base
from app.db.mixins import TenantMixin, TimestampMixin


class LeadEvent(Base, TenantMixin, TimestampMixin):
    __tablename__ = "lead_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    lead_id: Mapped[int] = mapped_column(
        ForeignKey("leads.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    event_type: Mapped[str] = mapped_column(String(64), nullable=False)
    details: Mapped[str | None] = mapped_column(String, nullable=True)
    actor: Mapped[str | None] = mapped_column(String(255), nullable=True)
