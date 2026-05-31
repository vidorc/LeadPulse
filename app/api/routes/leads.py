from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models.lead import Lead
from app.models.lead_event import LeadEvent
from app.schemas.lead import LeadCreate, LeadResponse, LeadOverride
from app.schemas.lead_event import LeadEventResponse
from app.tasks.lead_tasks import process_lead_ai
from app.services.auth_guard import (
    get_current_user,
    require_admin
)

router = APIRouter(
    prefix="/leads",
    tags=["Leads"]
)


@router.post("/", response_model=LeadResponse)
def create_lead(
    payload: LeadCreate,
    db: Session = Depends(get_db)
):
    lead = Lead(
        name=payload.name,
        phone=payload.phone,
        email=payload.email,
        source=payload.source,
        message=payload.message
    )

    db.add(lead)
    db.commit()
    db.refresh(lead)

    process_lead_ai.delay(lead.id)

    return lead


@router.get("/", response_model=list[LeadResponse])
def get_leads(
    db: Session = Depends(get_db),
    user=Depends(get_current_user)
):
    return db.query(Lead).all()


@router.post("/override/{lead_id}")
def override_lead(
    lead_id: int,
    payload: LeadOverride,
    db: Session = Depends(get_db),
    user=Depends(get_current_user)
):
    lead = db.query(Lead).filter(
        Lead.id == lead_id
    ).first()

    if not lead:
        return {"error": "Lead not found"}

    lead.decision = payload.decision
    lead.review_notes = payload.review_notes
    lead.requires_human_review = "no"

    db.commit()

    return {"message": "Lead overridden successfully"}


@router.get(
    "/events/{lead_id}",
    response_model=list[LeadEventResponse]
)
def get_lead_events(
    lead_id: int,
    db: Session = Depends(get_db),
    user=Depends(get_current_user)
):
    events = db.query(LeadEvent).filter(
        LeadEvent.lead_id == lead_id
    ).all()

    return events


@router.get("/metrics")
def get_metrics(
    db: Session = Depends(get_db),
    user=Depends(require_admin)
):
    total_leads = db.query(Lead).count()

    hot_leads = db.query(Lead).filter(
        Lead.decision == "hot_lead"
    ).count()

    manual_reviews = db.query(Lead).filter(
        Lead.requires_human_review == "yes"
    ).count()

    human_overrides = db.query(Lead).filter(
        Lead.review_notes.isnot(None)
    ).count()

    return {
        "total_leads": total_leads,
        "hot_leads": hot_leads,
        "manual_reviews": manual_reviews,
        "human_overrides": human_overrides
    }

@router.get("/review-queue")
def get_review_queue(
    db: Session = Depends(get_db),
    user=Depends(get_current_user)
):
    leads = db.query(Lead).filter(
        Lead.requires_human_review == "yes"
    ).all()

    return leads


@router.get("/dashboard/summary")
def dashboard_summary(
    db: Session = Depends(get_db),
    user=Depends(get_current_user)
):
    return {
        "total_leads": db.query(Lead).count(),
        "hot_leads": db.query(Lead).filter(
            Lead.decision == "hot_lead"
        ).count(),
        "manual_reviews": db.query(Lead).filter(
            Lead.requires_human_review == "yes"
        ).count()
    }

@router.get("/review-queue")
def get_review_queue(
    db: Session = Depends(get_db),
    user=Depends(get_current_user)
):
    leads = db.query(Lead).filter(
        Lead.requires_human_review == "yes"
    ).all()

    return leads


@router.get("/dashboard/summary")
def dashboard_summary(
    db: Session = Depends(get_db),
    user=Depends(get_current_user)
):
    return {
        "total_leads": db.query(Lead).count(),
        "hot_leads": db.query(Lead).filter(
            Lead.decision == "hot_lead"
        ).count(),
        "manual_reviews": db.query(Lead).filter(
            Lead.requires_human_review == "yes"
        ).count()
    }

@router.get("/review-queue")
def get_review_queue(
    db: Session = Depends(get_db),
    user=Depends(get_current_user)
):
    leads = db.query(Lead).filter(
        Lead.requires_human_review == "yes"
    ).all()

    return leads


@router.get("/dashboard/summary")
def dashboard_summary(
    db: Session = Depends(get_db),
    user=Depends(get_current_user)
):
    return {
        "total_leads": db.query(Lead).count(),
        "hot_leads": db.query(Lead).filter(
            Lead.decision == "hot_lead"
        ).count(),
        "manual_reviews": db.query(Lead).filter(
            Lead.requires_human_review == "yes"
        ).count()
    }