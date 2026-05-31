from pydantic import BaseModel
from datetime import datetime


class LeadCreate(BaseModel):
    name: str
    phone: str
    email: str
    source: str
    message: str


class LeadResponse(BaseModel):
    id: int
    name: str
    phone: str
    email: str
    source: str
    status: str

    message: str | None = None
    intent: str | None = None
    budget: str | None = None
    location: str | None = None
    urgency: str | None = None
    score: int | None = None
    ai_summary: str | None = None

    decision: str | None = None
    next_action: str | None = None
    action_result: str | None = None

    review_notes: str | None = None
    requires_human_review: str | None = None

    created_at: datetime | None = None
    processed_at: datetime | None = None

    class Config:
        from_attributes = True


class LeadOverride(BaseModel):
    decision: str
    review_notes: str