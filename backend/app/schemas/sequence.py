"""Follow-up sequence / enrollment request & response schemas."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.core.enums import EnrollmentStatus


class SequenceStepCreate(BaseModel):
    delay_hours: int = Field(ge=0, le=24 * 365)
    action: str = Field(default="email", max_length=64)
    subject: str | None = Field(default=None, max_length=255)
    body: str | None = None


class SequenceCreate(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    steps: list[SequenceStepCreate] = Field(min_length=1)


class SequenceStepResponse(BaseModel):
    id: int
    step_order: int
    delay_hours: int
    action: str
    subject: str | None = None
    body: str | None = None

    model_config = ConfigDict(from_attributes=True)


class SequenceResponse(BaseModel):
    id: int
    org_id: int
    name: str
    is_active: bool
    steps: list[SequenceStepResponse] = []

    model_config = ConfigDict(from_attributes=True)


class EnrollRequest(BaseModel):
    lead_id: int
    sequence_id: int


class EnrollmentResponse(BaseModel):
    id: int
    sequence_id: int
    lead_id: int
    status: EnrollmentStatus
    current_step: int
    enrolled_at: datetime
    completed_at: datetime | None = None

    model_config = ConfigDict(from_attributes=True)
