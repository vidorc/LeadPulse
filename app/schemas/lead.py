from pydantic import BaseModel
from typing import Optional


class LeadCreate(BaseModel):
    name: str
    phone: str
    email: Optional[str] = None
    source: Optional[str] = None


class LeadResponse(BaseModel):
    id: int
    name: str
    phone: str
    email: Optional[str]
    source: Optional[str]
    status: str

    class Config:
        from_attributes = True