"""Timeline event response schema."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict

from app.core.enums import EntityType


class EventResponse(BaseModel):
    id: int
    entity_type: EntityType
    entity_id: int
    event_type: str
    payload: dict | None = None
    actor: str | None = None
    occurred_at: datetime

    model_config = ConfigDict(from_attributes=True)
