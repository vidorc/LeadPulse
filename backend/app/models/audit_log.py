"""Audit log — an append-only record of security-relevant actions.

Distinct from the domain timeline (``Event``): the timeline is product history
(what happened to a lead/opportunity), the audit log is *governance* history
(who did a privileged thing, from where). It is written for auth events, role
changes, manual overrides, and policy edits, and is never updated or deleted.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import JSON, DateTime, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base_class import Base
from app.db.mixins import utcnow


class AuditLog(Base):
    __tablename__ = "audit_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    # org_id is nullable: some events (e.g. a failed login before tenant
    # resolution) have no resolved tenant yet.
    org_id: Mapped[int | None] = mapped_column(Integer, index=True)
    actor_user_id: Mapped[int | None] = mapped_column(Integer, index=True)
    actor_email: Mapped[str | None] = mapped_column(String(320))
    action: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    entity_type: Mapped[str | None] = mapped_column(String(32))
    entity_id: Mapped[int | None] = mapped_column(Integer)
    ip_address: Mapped[str | None] = mapped_column(String(64))
    detail: Mapped[dict | None] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utcnow, index=True
    )
