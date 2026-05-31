"""Outbox — transactional outbox for reliable, exactly-once-ish delivery.

Domain logic writes an outbox row in the SAME transaction as its state change
(architecture review §8.5). A Beat relay polls pending rows, delivers via the
channel adapter, and marks sent / increments attempts with backoff, dead-
lettering after max attempts. This fixes the audit's duplicate-email retry bug:
side effects no longer fire inline before commit, so a task retry can't double-send.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import JSON, DateTime, Index, Integer, String
from sqlalchemy import Enum as SAEnum
from sqlalchemy.orm import Mapped, mapped_column

from app.core.enums import OutboxChannel, OutboxStatus
from app.db.base_class import Base
from app.db.mixins import TenantMixin, TimestampMixin


class OutboxMessage(Base, TenantMixin, TimestampMixin):
    __tablename__ = "outbox"
    __table_args__ = (
        # Relay hot path: pending messages whose next_attempt_at is due.
        Index("ix_outbox_pending", "status", "next_attempt_at"),
        # Idempotency: at most one row per dedupe key per tenant.
        Index("ix_outbox_dedupe", "org_id", "dedupe_key", unique=True),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    channel: Mapped[OutboxChannel] = mapped_column(
        SAEnum(OutboxChannel, native_enum=False, length=20, validate_strings=True),
        nullable=False,
    )
    # Stable key so the same logical notification is never enqueued twice
    # (e.g. "hot_lead_alert:lead:42"). Unique per tenant.
    dedupe_key: Mapped[str] = mapped_column(String(255), nullable=False)
    payload: Mapped[dict] = mapped_column(JSON, nullable=False)
    status: Mapped[OutboxStatus] = mapped_column(
        SAEnum(OutboxStatus, native_enum=False, length=20, validate_strings=True),
        nullable=False,
        default=OutboxStatus.PENDING,
    )
    attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    max_attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=5)
    next_attempt_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_error: Mapped[str | None] = mapped_column(String)
    sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
