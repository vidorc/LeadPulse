"""Organization — the tenancy root. Every tenant-owned row hangs off an org."""

from __future__ import annotations

from sqlalchemy import Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base_class import Base
from app.db.mixins import SoftDeleteMixin, TimestampMixin


class Organization(Base, TimestampMixin, SoftDeleteMixin):
    __tablename__ = "organizations"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    slug: Mapped[str] = mapped_column(String(255), nullable=False, unique=True, index=True)
    # Shared secret for verifying HMAC-signed inbound ingestion webhooks.
    ingest_secret: Mapped[str] = mapped_column(String(64), nullable=False)

    teams: Mapped[list["Team"]] = relationship(  # noqa: F821
        back_populates="organization", cascade="all, delete-orphan"
    )
    memberships: Mapped[list["Membership"]] = relationship(  # noqa: F821
        back_populates="organization", cascade="all, delete-orphan"
    )
