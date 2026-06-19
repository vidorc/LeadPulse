"""Follow-up sequence models.

A Sequence is a named, org-scoped follow-up plan (e.g. "New Lead Nurture").
Its SequenceSteps fire at delays after enrollment (Day 1/3/7/14 — the product
spec). An Enrollment binds a lead to a sequence and tracks progress; cancelling
it (when a rep engages) stops further touches. Steps are executed by the
durable scheduler from Phase 5, not Celery eta.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, DateTime
from sqlalchemy import Enum as SAEnum
from sqlalchemy import ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.enums import EnrollmentStatus
from app.db.base_class import Base
from app.db.mixins import SoftDeleteMixin, TenantMixin, TimestampMixin


class Sequence(Base, TenantMixin, TimestampMixin, SoftDeleteMixin):
    __tablename__ = "sequences"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    steps: Mapped[list["SequenceStep"]] = relationship(
        back_populates="sequence",
        cascade="all, delete-orphan",
        order_by="SequenceStep.step_order",
    )


class SequenceStep(Base, TenantMixin, TimestampMixin):
    __tablename__ = "sequence_steps"
    __table_args__ = (
        UniqueConstraint("sequence_id", "step_order", name="uq_step_order"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    sequence_id: Mapped[int] = mapped_column(
        ForeignKey("sequences.id", ondelete="CASCADE"), nullable=False, index=True
    )
    step_order: Mapped[int] = mapped_column(Integer, nullable=False)
    # Delay from enrollment start at which this step fires.
    delay_hours: Mapped[int] = mapped_column(Integer, nullable=False)
    action: Mapped[str] = mapped_column(String(64), nullable=False, default="email")
    subject: Mapped[str | None] = mapped_column(String(255))
    body: Mapped[str | None] = mapped_column(String)

    sequence: Mapped["Sequence"] = relationship(back_populates="steps")


class Enrollment(Base, TenantMixin, TimestampMixin):
    __tablename__ = "enrollments"
    __table_args__ = (
        # A lead is enrolled in a given sequence at most once at a time.
        UniqueConstraint("sequence_id", "lead_id", name="uq_enrollment_seq_lead"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    sequence_id: Mapped[int] = mapped_column(
        ForeignKey("sequences.id", ondelete="CASCADE"), nullable=False, index=True
    )
    lead_id: Mapped[int] = mapped_column(
        ForeignKey("leads.id", ondelete="CASCADE"), nullable=False, index=True
    )
    status: Mapped[EnrollmentStatus] = mapped_column(
        SAEnum(EnrollmentStatus, native_enum=False, length=20, validate_strings=True),
        nullable=False,
        default=EnrollmentStatus.ACTIVE,
        index=True,
    )
    current_step: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    enrolled_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
