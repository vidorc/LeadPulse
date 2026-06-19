"""Revenue Leak Detection models.

SLAPolicy makes thresholds *data, not code* (architecture review §8.4): a
customer can tune "lead ignored after N hours" without a deploy. LeakAlert is a
detected breach; the scanner avoids duplicates by checking for an existing OPEN
alert per (entity, leak_type) before creating one.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, DateTime
from sqlalchemy import Enum as SAEnum
from sqlalchemy import Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.core.enums import EntityType, LeakAlertStatus, LeakSeverity, LeakType
from app.db.base_class import Base
from app.db.mixins import TenantMixin, TimestampMixin


class SLAPolicy(Base, TenantMixin, TimestampMixin):
    __tablename__ = "sla_policies"
    __table_args__ = (
        UniqueConstraint("org_id", "leak_type", name="uq_sla_org_leak_type"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    leak_type: Mapped[LeakType] = mapped_column(
        SAEnum(LeakType, native_enum=False, length=30, validate_strings=True),
        nullable=False,
    )
    # Breach threshold in hours (e.g. 24 = "no contact within 24h of creation").
    threshold_hours: Mapped[int] = mapped_column(Integer, nullable=False)
    severity: Mapped[LeakSeverity] = mapped_column(
        SAEnum(LeakSeverity, native_enum=False, length=10, validate_strings=True),
        nullable=False,
        default=LeakSeverity.MEDIUM,
    )
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    # If true, the scanner enqueues a notification for each new alert.
    notify: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)


class LeakAlert(Base, TenantMixin, TimestampMixin):
    __tablename__ = "leak_alerts"
    __table_args__ = (
        # Fast "is there already an open alert for this entity+type?" lookup.
        UniqueConstraint(
            "org_id", "leak_type", "entity_type", "entity_id", "status",
            name="uq_open_alert_per_entity",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    leak_type: Mapped[LeakType] = mapped_column(
        SAEnum(LeakType, native_enum=False, length=30, validate_strings=True),
        nullable=False,
    )
    entity_type: Mapped[EntityType] = mapped_column(
        SAEnum(EntityType, native_enum=False, length=20, validate_strings=True),
        nullable=False,
    )
    entity_id: Mapped[int] = mapped_column(Integer, nullable=False)
    severity: Mapped[LeakSeverity] = mapped_column(
        SAEnum(LeakSeverity, native_enum=False, length=10, validate_strings=True),
        nullable=False,
    )
    status: Mapped[LeakAlertStatus] = mapped_column(
        SAEnum(LeakAlertStatus, native_enum=False, length=10, validate_strings=True),
        nullable=False,
        default=LeakAlertStatus.OPEN,
        index=True,
    )
    detail: Mapped[str | None] = mapped_column(String)
    detected_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
