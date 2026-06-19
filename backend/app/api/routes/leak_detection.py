"""Revenue Leak Detection routes — SLA policy management + alert handling."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import get_tenant_context, require_manager
from app.core.enums import LeakAlertStatus
from app.core.tenant import TenantContext
from app.db.mixins import utcnow
from app.db.repository import TenantRepository
from app.db.session import get_db
from app.models.leak import LeakAlert, SLAPolicy
from app.schemas.leak import (
    LeakAlertResponse,
    SLAPolicyResponse,
    SLAPolicyUpsert,
)
from app.services import leak_detection

router = APIRouter(prefix="/leak-detection", tags=["Revenue Leak Detection"])


class _PolicyRepo(TenantRepository[SLAPolicy]):
    model = SLAPolicy


@router.put("/policies", response_model=SLAPolicyResponse)
def upsert_policy(
    payload: SLAPolicyUpsert,
    db: Session = Depends(get_db),
    ctx: TenantContext = Depends(require_manager),
):
    """Create or update the SLA policy for a leak type (one per type per org)."""
    existing = db.execute(
        select(SLAPolicy).where(
            SLAPolicy.org_id == ctx.org_id, SLAPolicy.leak_type == payload.leak_type
        )
    ).scalar_one_or_none()

    if existing is None:
        policy = SLAPolicy(
            org_id=ctx.org_id,
            leak_type=payload.leak_type,
            threshold_hours=payload.threshold_hours,
            severity=payload.severity,
            is_active=payload.is_active,
            notify=payload.notify,
        )
        db.add(policy)
    else:
        existing.threshold_hours = payload.threshold_hours
        existing.severity = payload.severity
        existing.is_active = payload.is_active
        existing.notify = payload.notify
        policy = existing
    db.commit()
    db.refresh(policy)
    return policy


@router.get("/policies", response_model=list[SLAPolicyResponse])
def list_policies(
    db: Session = Depends(get_db),
    ctx: TenantContext = Depends(get_tenant_context),
):
    return _PolicyRepo(db, ctx).list()


@router.get("/alerts", response_model=list[LeakAlertResponse])
def list_alerts(
    status_filter: LeakAlertStatus | None = Query(default=None, alias="status"),
    db: Session = Depends(get_db),
    ctx: TenantContext = Depends(get_tenant_context),
):
    stmt = select(LeakAlert).where(LeakAlert.org_id == ctx.org_id)
    if status_filter is not None:
        stmt = stmt.where(LeakAlert.status == status_filter)
    stmt = stmt.order_by(LeakAlert.detected_at.desc())
    return list(db.execute(stmt).scalars().all())


@router.post("/alerts/{alert_id}/resolve", response_model=LeakAlertResponse)
def resolve_alert(
    alert_id: int,
    db: Session = Depends(get_db),
    ctx: TenantContext = Depends(get_tenant_context),
):
    alert = db.get(LeakAlert, alert_id)
    if alert is None or alert.org_id != ctx.org_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Alert not found")
    alert.status = LeakAlertStatus.RESOLVED
    alert.resolved_at = utcnow()
    db.commit()
    db.refresh(alert)
    return alert


@router.post("/scan")
def trigger_scan(
    db: Session = Depends(get_db),
    ctx: TenantContext = Depends(require_manager),
):
    """Run the SLA scanner on demand (also runs every 5 min via Beat)."""
    return leak_detection.scan(db)
