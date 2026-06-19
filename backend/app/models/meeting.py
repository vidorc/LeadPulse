"""Meeting — a scheduled interaction on an opportunity.

Leak detection watches for "scheduled_at passed and status != completed"
(MEETING_MISSED). scheduled_at + status drive that check.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime
from sqlalchemy import Enum as SAEnum
from sqlalchemy import ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.enums import MeetingStatus
from app.db.base_class import Base
from app.db.mixins import SoftDeleteMixin, TenantMixin, TimestampMixin


class Meeting(Base, TenantMixin, TimestampMixin, SoftDeleteMixin):
    __tablename__ = "meetings"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    opportunity_id: Mapped[int] = mapped_column(
        ForeignKey("opportunities.id", ondelete="CASCADE"), nullable=False, index=True
    )
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    scheduled_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, index=True
    )
    status: Mapped[MeetingStatus] = mapped_column(
        SAEnum(MeetingStatus, native_enum=False, length=20, validate_strings=True),
        nullable=False,
        default=MeetingStatus.SCHEDULED,
        index=True,
    )

    opportunity: Mapped["Opportunity"] = relationship(  # noqa: F821
        back_populates="meetings"
    )
