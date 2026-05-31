"""ScheduledJob — durable, queryable, cancellable scheduling substrate.

The architecture review (§8.3) rejects Celery eta/countdown because those jobs
are invisible, uncancellable, and lost on broker flush. Instead, time-based
work (follow-up steps, leak re-scans, escalations) is a row here. A Beat
dispatcher claims due rows with SELECT ... FOR UPDATE SKIP LOCKED and executes
them. Cancelling a sequence when a rep replies is then a trivial UPDATE.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import JSON, DateTime, Index, Integer, String
from sqlalchemy import Enum as SAEnum
from sqlalchemy.orm import Mapped, mapped_column

from app.core.enums import EntityType, ScheduledJobStatus
from app.db.base_class import Base
from app.db.mixins import TenantMixin, TimestampMixin


class ScheduledJob(Base, TenantMixin, TimestampMixin):
    __tablename__ = "scheduled_jobs"
    __table_args__ = (
        # Dispatcher hot path: due, pending jobs ordered by run_at.
        Index("ix_scheduled_jobs_due", "status", "run_at"),
        Index("ix_scheduled_jobs_entity", "entity_type", "entity_id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    job_type: Mapped[str] = mapped_column(String(64), nullable=False)
    entity_type: Mapped[EntityType | None] = mapped_column(
        SAEnum(EntityType, native_enum=False, length=20, validate_strings=True)
    )
    entity_id: Mapped[int | None] = mapped_column(Integer)
    payload: Mapped[dict | None] = mapped_column(JSON)
    run_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    status: Mapped[ScheduledJobStatus] = mapped_column(
        SAEnum(ScheduledJobStatus, native_enum=False, length=20, validate_strings=True),
        nullable=False,
        default=ScheduledJobStatus.PENDING,
    )
    attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    last_error: Mapped[str | None] = mapped_column(String)
    executed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
