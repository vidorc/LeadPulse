"""Audit logging service.

A thin, side-effect-only helper: write an audit record in its own short
transaction so an audit write never participates in (or rolls back) the
caller's business transaction, and an audit failure is logged but never
propagates to break the request. Reads are tenant-scoped.
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.logging import get_logger
from app.models.audit_log import AuditLog

log = get_logger(__name__)


def record(
    db: Session,
    *,
    action: str,
    org_id: int | None = None,
    actor_user_id: int | None = None,
    actor_email: str | None = None,
    entity_type: str | None = None,
    entity_id: int | None = None,
    ip_address: str | None = None,
    detail: dict | None = None,
) -> None:
    """Append an audit record. Best-effort: never raises into the caller."""
    entry = AuditLog(
        org_id=org_id,
        actor_user_id=actor_user_id,
        actor_email=actor_email,
        action=action,
        entity_type=entity_type,
        entity_id=entity_id,
        ip_address=ip_address,
        detail=detail,
    )
    try:
        db.add(entry)
        db.commit()
    except Exception as exc:  # noqa: BLE001 — auditing must not break requests
        db.rollback()
        log.error("audit.write_failed", action=action, error=str(exc))


def list_for_org(db: Session, *, org_id: int, limit: int = 100) -> list[AuditLog]:
    return list(
        db.execute(
            select(AuditLog)
            .where(AuditLog.org_id == org_id)
            .order_by(AuditLog.created_at.desc())
            .limit(limit)
        ).scalars()
    )
