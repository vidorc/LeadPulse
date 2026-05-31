"""Reusable SQLAlchemy mixins for the LeadPulse data model.

Every tenant-owned table composes these so the tenancy + temporal guarantees
the product depends on are uniform and impossible to forget:

  * ``TimestampMixin``  — timezone-aware created_at / updated_at (updated_at is
    what Revenue Leak Detection measures staleness against).
  * ``SoftDeleteMixin`` — deleted_at for reversible deletes (no hard deletes of
    tenant data by default).
  * ``TenantMixin``     — non-null, indexed org_id FK; the row-level tenancy key.

Timestamps are UTC and timezone-aware (the audit flagged naive
``datetime.utcnow()``, deprecated on 3.12+).
"""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import DateTime, ForeignKey, Integer, func
from sqlalchemy.orm import Mapped, mapped_column


def utcnow() -> datetime:
    """Timezone-aware current UTC time (replaces naive datetime.utcnow)."""
    return datetime.now(timezone.utc)


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=utcnow,
        server_default=func.now(),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=utcnow,
        onupdate=utcnow,
        server_default=func.now(),
    )


class SoftDeleteMixin:
    deleted_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        default=None,
    )

    @property
    def is_deleted(self) -> bool:
        return self.deleted_at is not None


class TenantMixin:
    """Adds the mandatory org scope. Indexed because every tenant query
    filters on it."""

    org_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("organizations.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
