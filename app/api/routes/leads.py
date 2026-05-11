from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models.lead import Lead
from app.schemas.lead import LeadCreate, LeadResponse
from app.db.base_class import Base

router = APIRouter(
    prefix="/leads",
    tags=["Leads"]
)


@router.post("/", response_model=LeadResponse)
def create_lead(
    payload: LeadCreate,
    db: Session = Depends(get_db)
):

    existing = db.query(Lead).filter(
        Lead.phone == payload.phone
    ).first()

    if existing:
        raise HTTPException(
            status_code=400,
            detail="Lead already exists"
        )

    lead = Lead(
        name=payload.name,
        phone=payload.phone,
        email=payload.email,
        source=payload.source
    )

    db.add(lead)

    db.commit()

    db.refresh(lead)

    return lead


@router.get("/", response_model=list[LeadResponse])
def get_leads(db: Session = Depends(get_db)):

    return db.query(Lead).all()