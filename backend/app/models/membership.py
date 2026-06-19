"""Membership — binds a User to an Organization with a Role (and optional Team).

This is where tenancy and authorization meet: a user's role is per-org, so the
same person can be OWNER of one org and AGENT of another. The JWT carries the
active membership's org_id + role.
"""

from __future__ import annotations

from sqlalchemy import Enum as SAEnum
from sqlalchemy import ForeignKey, Integer, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.enums import Role
from app.db.base_class import Base
from app.db.mixins import SoftDeleteMixin, TenantMixin, TimestampMixin


class Membership(Base, TenantMixin, TimestampMixin, SoftDeleteMixin):
    __tablename__ = "memberships"
    __table_args__ = (
        # A user has exactly one membership row per org.
        UniqueConstraint("org_id", "user_id", name="uq_membership_org_user"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    team_id: Mapped[int | None] = mapped_column(
        ForeignKey("teams.id", ondelete="SET NULL"), nullable=True, index=True
    )
    role: Mapped[Role] = mapped_column(
        SAEnum(Role, native_enum=False, length=20, validate_strings=True),
        nullable=False,
        default=Role.AGENT,
    )

    organization: Mapped["Organization"] = relationship(  # noqa: F821
        back_populates="memberships"
    )
    user: Mapped["User"] = relationship(back_populates="memberships")  # noqa: F821
    team: Mapped["Team"] = relationship(back_populates="memberships")  # noqa: F821
