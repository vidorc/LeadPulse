"""Lead routes — thin, tenant-scoped layer over the lead repositories.

Every read/write is scoped to the caller's org via TenantContext +
LeadRepository, closing the IDOR / "every user sees all leads" findings.
Lead creation now requires authentication (it triggers paid AI work and must
be tenant-attributed); multi-channel signed ingestion arrives in Phase 6.
The duplicate review-queue / dashboard registrations and the 200-on-not-found
bug from the audit are removed here.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.api.deps import get_tenant_context, require_manager
from app.core.enums import LeadStatus
from app.core.tenant import TenantContext
from app.db.session import get_db
from app.models.lead import Lead
from app.repositories.lead_repository import LeadEventRepository, LeadRepository
from app.schemas.lead import (
    LeadCreate,
    LeadOverride,
    LeadResponse,
)
from app.schemas.lead_event import LeadEventResponse
from app.tasks.lead_tasks import process_lead_ai

router = APIRouter(prefix="/leads", tags=["Leads"])


@router.post("/", response_model=LeadResponse, status_code=status.HTTP_201_CREATED)
def create_lead(
    payload: LeadCreate,
    db: Session = Depends(get_db),
    ctx: TenantContext = Depends(get_tenant_context),
):
    repo = LeadRepository(db, ctx)
    lead = Lead(
        name=payload.name,
        phone=payload.phone,
        email=payload.email,
        source=payload.source,
        message=payload.message,
        status=LeadStatus.NEW,
    )
    repo.add(lead)  # forces org_id = ctx.org_id
    db.commit()
    db.refresh(lead)

    # Offload paid AI work; pass org_id so the worker stays tenant-scoped.
    process_lead_ai.delay(lead.id, ctx.org_id)
    return lead


@router.get("/", response_model=list[LeadResponse])
def list_leads(
    db: Session = Depends(get_db),
    ctx: TenantContext = Depends(get_tenant_context),
):
    return LeadRepository(db, ctx).list()


@router.get("/review-queue", response_model=list[LeadResponse])
def review_queue(
    db: Session = Depends(get_db),
    ctx: TenantContext = Depends(get_tenant_context),
):
    return LeadRepository(db, ctx).review_queue()


@router.get("/dashboard/summary")
def dashboard_summary(
    db: Session = Depends(get_db),
    ctx: TenantContext = Depends(get_tenant_context),
):
    return LeadRepository(db, ctx).summary_counts()


@router.get("/{lead_id}", response_model=LeadResponse)
def get_lead(
    lead_id: int,
    db: Session = Depends(get_db),
    ctx: TenantContext = Depends(get_tenant_context),
):
    lead = LeadRepository(db, ctx).get(lead_id)
    if lead is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Lead not found")
    return lead


@router.post("/{lead_id}/override", response_model=LeadResponse)
def override_lead(
    lead_id: int,
    payload: LeadOverride,
    db: Session = Depends(get_db),
    ctx: TenantContext = Depends(require_manager),
):
    repo = LeadRepository(db, ctx)
    lead = repo.get(lead_id)
    if lead is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Lead not found")

    lead.decision = payload.decision
    lead.review_notes = payload.review_notes
    lead.requires_human_review = False
    db.commit()
    db.refresh(lead)
    return lead


@router.get("/{lead_id}/events", response_model=list[LeadEventResponse])
def get_lead_events(
    lead_id: int,
    db: Session = Depends(get_db),
    ctx: TenantContext = Depends(get_tenant_context),
):
    # Ensure the lead belongs to the tenant before exposing its events.
    if LeadRepository(db, ctx).get(lead_id) is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Lead not found")
    return LeadEventRepository(db, ctx).for_lead(lead_id)
