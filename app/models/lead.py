from sqlalchemy import Column, Integer, String

from app.db.base_class import Base
from sqlalchemy import DateTime
from datetime import datetime

class Lead(Base):

    __tablename__ = "leads"

    id = Column(Integer, primary_key=True)

    name = Column(String)

    phone = Column(String)

    email = Column(String)

    source = Column(String)

    status = Column(String, default="new")

    message = Column(String)

    intent = Column(String)

    budget = Column(String)

    location = Column(String)

    urgency = Column(String)

    score = Column(Integer)

    ai_summary = Column(String)

    decision = Column(String)

    next_action = Column(String)
    action_result = Column(String)
    review_notes = Column(String)
    requires_human_review = Column(String)
    created_at = Column(DateTime, default=datetime.utcnow)
    processed_at = Column(DateTime, nullable=True)