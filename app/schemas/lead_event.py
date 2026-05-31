from pydantic import BaseModel
from datetime import datetime


class LeadEventResponse(BaseModel):
    id: int
    lead_id: int
    event_type: str
    details: str
    created_at: datetime

    class Config:
        from_attributes = True
