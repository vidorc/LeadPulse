"""Opportunity routes — thin layer over OpportunityService, tenant-scoped."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.api.deps import get_tenant_context
from app.core.tenant import TenantContext
from app.db.session import get_db
from app.schemas.opportunity import (
    MeetingCreate,
    MeetingResponse,
    OpportunityCreate,
    OpportunityResponse,
    OpportunityStageUpdate,
    ProposalCreate,
    ProposalResponse,
)
from app.services.opportunity_service import OpportunityRepository, OpportunityService

router = APIRouter(prefix="/opportunities", tags=["Opportunities"])


@router.post("/", response_model=OpportunityResponse, status_code=status.HTTP_201_CREATED)
def create_opportunity(
    payload: OpportunityCreate,
    db: Session = Depends(get_db),
    ctx: TenantContext = Depends(get_tenant_context),
):
    return OpportunityService(db, ctx).create(
        title=payload.title,
        lead_id=payload.lead_id,
        value_amount=payload.value_amount,
        owner_id=payload.owner_id,
        team_id=payload.team_id,
    )


@router.get("/", response_model=list[OpportunityResponse])
def list_opportunities(
    db: Session = Depends(get_db),
    ctx: TenantContext = Depends(get_tenant_context),
):
    return OpportunityRepository(db, ctx).list()


@router.get("/{opp_id}", response_model=OpportunityResponse)
def get_opportunity(
    opp_id: int,
    db: Session = Depends(get_db),
    ctx: TenantContext = Depends(get_tenant_context),
):
    opp = OpportunityRepository(db, ctx).get(opp_id)
    if opp is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Opportunity not found")
    return opp


@router.post("/{opp_id}/stage", response_model=OpportunityResponse)
def transition_stage(
    opp_id: int,
    payload: OpportunityStageUpdate,
    db: Session = Depends(get_db),
    ctx: TenantContext = Depends(get_tenant_context),
):
    try:
        return OpportunityService(db, ctx).transition_stage(opp_id, payload.stage)
    except LookupError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Opportunity not found")


@router.post(
    "/{opp_id}/proposals",
    response_model=ProposalResponse,
    status_code=status.HTTP_201_CREATED,
)
def add_proposal(
    opp_id: int,
    payload: ProposalCreate,
    db: Session = Depends(get_db),
    ctx: TenantContext = Depends(get_tenant_context),
):
    try:
        return OpportunityService(db, ctx).add_proposal(
            opp_id, title=payload.title, amount=payload.amount
        )
    except LookupError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Opportunity not found")


@router.post("/proposals/{proposal_id}/send", response_model=ProposalResponse)
def send_proposal(
    proposal_id: int,
    db: Session = Depends(get_db),
    ctx: TenantContext = Depends(get_tenant_context),
):
    try:
        return OpportunityService(db, ctx).send_proposal(proposal_id)
    except LookupError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Proposal not found")


@router.post(
    "/{opp_id}/meetings",
    response_model=MeetingResponse,
    status_code=status.HTTP_201_CREATED,
)
def schedule_meeting(
    opp_id: int,
    payload: MeetingCreate,
    db: Session = Depends(get_db),
    ctx: TenantContext = Depends(get_tenant_context),
):
    try:
        return OpportunityService(db, ctx).schedule_meeting(
            opp_id, title=payload.title, scheduled_at=payload.scheduled_at
        )
    except LookupError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Opportunity not found")


@router.post("/meetings/{meeting_id}/complete", response_model=MeetingResponse)
def complete_meeting(
    meeting_id: int,
    db: Session = Depends(get_db),
    ctx: TenantContext = Depends(get_tenant_context),
):
    try:
        return OpportunityService(db, ctx).complete_meeting(meeting_id)
    except LookupError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Meeting not found")
