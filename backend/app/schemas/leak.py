"""SLA policy / leak alert request & response schemas."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.core.enums import (
    EntityType,
    LeakAlertStatus,
    LeakSeverity,
    LeakType,
)


class SLAPolicyUpsert(BaseModel):
    leak_type: LeakType
    threshold_hours: int = Field(ge=0, le=24 * 365)
    severity: LeakSeverity = LeakSeverity.MEDIUM
    is_active: bool = True
    notify: bool = True


class SLAPolicyResponse(BaseModel):
    id: int
    org_id: int
    leak_type: LeakType
    threshold_hours: int
    severity: LeakSeverity
    is_active: bool
    notify: bool

    model_config = ConfigDict(from_attributes=True)


class LeakAlertResponse(BaseModel):
    id: int
    leak_type: LeakType
    entity_type: EntityType
    entity_id: int
    severity: LeakSeverity
    status: LeakAlertStatus
    detail: str | None = None
    detected_at: datetime
    resolved_at: datetime | None = None

    model_config = ConfigDict(from_attributes=True)
