"""Lead — an inbound contact, the write-path entity of Lead Ingestion.

Now tenant-scoped (org_id), assignable (owner_id / team_id for routing), and
typed (enum status/decision/urgency/intent instead of magic strings). Inherits
created_at/updated_at/deleted_at from the mixins — updated_at is what leak
detection measures staleness against.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime
from sqlalchemy import Enum as SAEnum
from sqlalchemy import ForeignKey, Integer, Numeric, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.enums import Intent, LeadDecision, LeadStatus, Urgency
from app.db.base_class import Base
from app.db.mixins import SoftDeleteMixin, TenantMixin, TimestampMixin


class Lead(Base, TenantMixin, TimestampMixin, SoftDeleteMixin):
    __tablename__ = "leads"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)

    # ---- Contact / capture ----
    name: Mapped[str | None] = mapped_column(String(255))
    phone: Mapped[str | None] = mapped_column(String(64))
    email: Mapped[str | None] = mapped_column(String(320), index=True)
    source: Mapped[str | None] = mapped_column(String(64), index=True)
    message: Mapped[str | None] = mapped_column(String)

    status: Mapped[LeadStatus] = mapped_column(
        SAEnum(LeadStatus, native_enum=False, length=20, validate_strings=True),
        nullable=False,
        default=LeadStatus.NEW,
        index=True,
    )

    # ---- Qualification (AI-enriched) ----
    intent: Mapped[Intent | None] = mapped_column(
        SAEnum(Intent, native_enum=False, length=20, validate_strings=True)
    )
    budget: Mapped[str | None] = mapped_column(String(255))  # raw AI-extracted text
    budget_amount: Mapped[float | None] = mapped_column(Numeric(14, 2))  # parsed, range-queryable
    timeline: Mapped[str | None] = mapped_column(String(255))
    location: Mapped[str | None] = mapped_column(String(255))
    urgency: Mapped[Urgency | None] = mapped_column(
        SAEnum(Urgency, native_enum=False, length=20, validate_strings=True)
    )
    score: Mapped[int | None] = mapped_column(Integer)
    ai_summary: Mapped[str | None] = mapped_column(String)

    # ---- Decision / routing ----
    decision: Mapped[LeadDecision | None] = mapped_column(
        SAEnum(LeadDecision, native_enum=False, length=20, validate_strings=True),
        index=True,
    )
    next_action: Mapped[str | None] = mapped_column(String(255))
    action_result: Mapped[str | None] = mapped_column(String)
    requires_human_review: Mapped[bool] = mapped_column(default=False, nullable=False)
    review_notes: Mapped[str | None] = mapped_column(String)

    owner_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), index=True
    )
    team_id: Mapped[int | None] = mapped_column(
        ForeignKey("teams.id", ondelete="SET NULL"), index=True
    )

    processed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    organization: Mapped["Organization"] = relationship()  # noqa: F821
