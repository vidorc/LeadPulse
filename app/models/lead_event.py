from sqlalchemy import Column, Integer, String, ForeignKey, DateTime
from datetime import datetime

from app.db.base_class import Base


class LeadEvent(Base):
    __tablename__ = "lead_events"

    id = Column(Integer, primary_key=True)

    lead_id = Column(
        Integer,
        ForeignKey("leads.id")
    )

    event_type = Column(String)

    details = Column(String)

    created_at = Column(
        DateTime,
        default=datetime.utcnow
    )