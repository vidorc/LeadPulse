"""Proposal — a document sent on an opportunity.

Leak detection watches for "no follow-up event since sent_at" (PROPOSAL_COLD).
sent_at is therefore a first-class column, not derived.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime
from sqlalchemy import Enum as SAEnum
from sqlalchemy import ForeignKey, Integer, Numeric, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.enums import ProposalStatus
from app.db.base_class import Base
from app.db.mixins import SoftDeleteMixin, TenantMixin, TimestampMixin


class Proposal(Base, TenantMixin, TimestampMixin, SoftDeleteMixin):
    __tablename__ = "proposals"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    opportunity_id: Mapped[int] = mapped_column(
        ForeignKey("opportunities.id", ondelete="CASCADE"), nullable=False, index=True
    )
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    amount: Mapped[float | None] = mapped_column(Numeric(14, 2))
    status: Mapped[ProposalStatus] = mapped_column(
        SAEnum(ProposalStatus, native_enum=False, length=20, validate_strings=True),
        nullable=False,
        default=ProposalStatus.DRAFT,
        index=True,
    )
    sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)

    opportunity: Mapped["Opportunity"] = relationship(  # noqa: F821
        back_populates="proposals"
    )
