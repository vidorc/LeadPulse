"""Opportunity — a qualified deal with stages and money.

Distinct from Lead (an inbound contact): an Opportunity is what *stalls* and
what Revenue Leak Detection measures (no stage change within N days). Stage
transitions append timeline events so staleness is queryable.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime
from sqlalchemy import Enum as SAEnum
from sqlalchemy import ForeignKey, Integer, Numeric, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.enums import OpportunityStage
from app.db.base_class import Base
from app.db.mixins import SoftDeleteMixin, TenantMixin, TimestampMixin


class Opportunity(Base, TenantMixin, TimestampMixin, SoftDeleteMixin):
    __tablename__ = "opportunities"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    lead_id: Mapped[int | None] = mapped_column(
        ForeignKey("leads.id", ondelete="SET NULL"), index=True
    )
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    stage: Mapped[OpportunityStage] = mapped_column(
        SAEnum(OpportunityStage, native_enum=False, length=20, validate_strings=True),
        nullable=False,
        default=OpportunityStage.NEW,
        index=True,
    )
    value_amount: Mapped[float | None] = mapped_column(Numeric(14, 2))
    currency: Mapped[str] = mapped_column(String(3), nullable=False, default="USD")

    owner_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), index=True
    )
    team_id: Mapped[int | None] = mapped_column(
        ForeignKey("teams.id", ondelete="SET NULL"), index=True
    )

    # When the stage last changed — the column "opportunity stalled" measures.
    stage_changed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    proposals: Mapped[list["Proposal"]] = relationship(  # noqa: F821
        back_populates="opportunity", cascade="all, delete-orphan"
    )
    meetings: Mapped[list["Meeting"]] = relationship(  # noqa: F821
        back_populates="opportunity", cascade="all, delete-orphan"
    )
