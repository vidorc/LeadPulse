"""Opportunity / Proposal / Meeting request & response schemas."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.core.enums import MeetingStatus, OpportunityStage, ProposalStatus


# ---- Opportunity ----
class OpportunityCreate(BaseModel):
    title: str = Field(min_length=1, max_length=255)
    lead_id: int | None = None
    value_amount: float | None = Field(default=None, ge=0)
    owner_id: int | None = None
    team_id: int | None = None


class OpportunityStageUpdate(BaseModel):
    stage: OpportunityStage


class OpportunityResponse(BaseModel):
    id: int
    org_id: int
    lead_id: int | None = None
    title: str
    stage: OpportunityStage
    value_amount: float | None = None
    currency: str
    owner_id: int | None = None
    team_id: int | None = None
    stage_changed_at: datetime
    closed_at: datetime | None = None
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


# ---- Proposal ----
class ProposalCreate(BaseModel):
    title: str = Field(min_length=1, max_length=255)
    amount: float | None = Field(default=None, ge=0)


class ProposalResponse(BaseModel):
    id: int
    opportunity_id: int
    title: str
    amount: float | None = None
    status: ProposalStatus
    sent_at: datetime | None = None

    model_config = ConfigDict(from_attributes=True)


# ---- Meeting ----
class MeetingCreate(BaseModel):
    title: str = Field(min_length=1, max_length=255)
    scheduled_at: datetime


class MeetingResponse(BaseModel):
    id: int
    opportunity_id: int
    title: str
    scheduled_at: datetime
    status: MeetingStatus

    model_config = ConfigDict(from_attributes=True)
