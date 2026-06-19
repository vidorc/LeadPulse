"""Follow-up engine routes — sequences, enrollment, cancellation."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.api.deps import get_tenant_context, require_manager
from app.core.tenant import TenantContext
from app.db.repository import TenantRepository
from app.db.session import get_db
from app.models.sequence import Sequence
from app.schemas.sequence import (
    EnrollmentResponse,
    EnrollRequest,
    SequenceCreate,
    SequenceResponse,
)
from app.services.followup_service import FollowUpService

router = APIRouter(prefix="/follow-ups", tags=["Follow-Up Engine"])


class _SequenceRepo(TenantRepository[Sequence]):
    model = Sequence


@router.post("/sequences", response_model=SequenceResponse, status_code=status.HTTP_201_CREATED)
def create_sequence(
    payload: SequenceCreate,
    db: Session = Depends(get_db),
    ctx: TenantContext = Depends(require_manager),
):
    return FollowUpService(db, ctx).create_sequence(
        name=payload.name,
        steps=[s.model_dump() for s in payload.steps],
    )


@router.get("/sequences", response_model=list[SequenceResponse])
def list_sequences(
    db: Session = Depends(get_db),
    ctx: TenantContext = Depends(get_tenant_context),
):
    return _SequenceRepo(db, ctx).list()


@router.post("/enroll", response_model=EnrollmentResponse, status_code=status.HTTP_201_CREATED)
def enroll(
    payload: EnrollRequest,
    db: Session = Depends(get_db),
    ctx: TenantContext = Depends(get_tenant_context),
):
    try:
        return FollowUpService(db, ctx).enroll(
            lead_id=payload.lead_id, sequence_id=payload.sequence_id
        )
    except LookupError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))


@router.post("/leads/{lead_id}/cancel")
def cancel_for_lead(
    lead_id: int,
    db: Session = Depends(get_db),
    ctx: TenantContext = Depends(get_tenant_context),
):
    cancelled = FollowUpService(db, ctx).cancel_for_lead(lead_id=lead_id)
    return {"cancelled_enrollments": cancelled}
