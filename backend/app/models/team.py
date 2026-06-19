"""Team — an org-scoped grouping of members, used for routing and ownership."""

from __future__ import annotations

from sqlalchemy import Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base_class import Base
from app.db.mixins import SoftDeleteMixin, TenantMixin, TimestampMixin


class Team(Base, TenantMixin, TimestampMixin, SoftDeleteMixin):
    __tablename__ = "teams"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)

    organization: Mapped["Organization"] = relationship(  # noqa: F821
        back_populates="teams"
    )
    memberships: Mapped[list["Membership"]] = relationship(  # noqa: F821
        back_populates="team"
    )
