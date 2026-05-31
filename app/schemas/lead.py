"""Lead request/response schemas."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, EmailStr, Field

from app.core.enums import Intent, LeadDecision, LeadStatus, Urgency


class LeadCreate(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    phone: str | None = Field(default=None, max_length=64)
    email: EmailStr | None = None
    source: str = Field(min_length=1, max_length=64)
    message: str | None = Field(default=None, max_length=10_000)


class LeadResponse(BaseModel):
    id: int
    org_id: int
    name: str | None = None
    phone: str | None = None
    email: str | None = None
    source: str | None = None
    status: LeadStatus

    message: str | None = None
    intent: Intent | None = None
    budget: str | None = None
    budget_amount: float | None = None
    timeline: str | None = None
    location: str | None = None
    urgency: Urgency | None = None
    score: int | None = None
    ai_summary: str | None = None

    decision: LeadDecision | None = None
    next_action: str | None = None
    action_result: str | None = None

    requires_human_review: bool = False
    review_notes: str | None = None
    owner_id: int | None = None
    team_id: int | None = None

    created_at: datetime | None = None
    updated_at: datetime | None = None
    processed_at: datetime | None = None

    model_config = ConfigDict(from_attributes=True)


class LeadOverride(BaseModel):
    decision: LeadDecision
    review_notes: str | None = Field(default=None, max_length=10_000)
