"""Lead event response schema."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict


class LeadEventResponse(BaseModel):
    id: int
    lead_id: int
    event_type: str
    details: str | None = None  # column is nullable (audit: was non-optional → serialization error)
    actor: str | None = None
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)
