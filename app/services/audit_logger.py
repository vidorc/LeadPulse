from app.models.lead_event import LeadEvent


def log_event(
    db,
    lead_id: int,
    event_type: str,
    details: str
):
    event = LeadEvent(
        lead_id=lead_id,
        event_type=event_type,
        details=details
    )

    db.add(event)
