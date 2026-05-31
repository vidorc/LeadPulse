"""Scheduler service — durable scheduling substrate operations.

`schedule` writes a ScheduledJob row (queryable/cancellable, unlike Celery eta).
`cancel_for_entity` cancels pending jobs (e.g. when a rep replies, kill the
follow-up sequence). `dispatch_due` is run by Beat: it claims due pending jobs
with FOR UPDATE SKIP LOCKED so multiple workers never double-execute, runs the
registered handler, and records the outcome.
"""

from __future__ import annotations

from datetime import datetime
from typing import Callable

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.core.enums import EntityType, ScheduledJobStatus
from app.db.mixins import utcnow
from app.models.scheduled_job import ScheduledJob

# Registry of job_type -> handler(db, job). Domains register their handlers
# here (follow-up step execution, leak rescan, escalation) in Phase 6.
_HANDLERS: dict[str, Callable[[Session, ScheduledJob], None]] = {}


def register_handler(job_type: str, handler: Callable[[Session, ScheduledJob], None]) -> None:
    _HANDLERS[job_type] = handler


def schedule(
    db: Session,
    *,
    org_id: int,
    job_type: str,
    run_at: datetime,
    entity_type: EntityType | None = None,
    entity_id: int | None = None,
    payload: dict | None = None,
    commit: bool = False,
) -> ScheduledJob:
    job = ScheduledJob(
        org_id=org_id,
        job_type=job_type,
        run_at=run_at,
        entity_type=entity_type,
        entity_id=entity_id,
        payload=payload,
        status=ScheduledJobStatus.PENDING,
    )
    db.add(job)
    db.flush()
    if commit:
        db.commit()
    return job


def cancel_for_entity(
    db: Session,
    *,
    org_id: int,
    entity_type: EntityType,
    entity_id: int,
    job_type: str | None = None,
    commit: bool = True,
) -> int:
    """Cancel pending jobs for an entity (e.g. stop a follow-up sequence).
    Returns the number cancelled."""
    stmt = (
        update(ScheduledJob)
        .where(
            ScheduledJob.org_id == org_id,
            ScheduledJob.entity_type == entity_type,
            ScheduledJob.entity_id == entity_id,
            ScheduledJob.status == ScheduledJobStatus.PENDING,
        )
        .values(status=ScheduledJobStatus.CANCELLED)
    )
    if job_type is not None:
        stmt = stmt.where(ScheduledJob.job_type == job_type)
    result = db.execute(stmt)
    if commit:
        db.commit()
    return result.rowcount or 0


def dispatch_due(db: Session, *, batch_size: int = 100) -> dict[str, int]:
    """Claim and execute due jobs. Run frequently by Beat. Each job runs in its
    own committed unit so one failure doesn't roll back the batch."""
    now = utcnow()
    claim = (
        select(ScheduledJob)
        .where(
            ScheduledJob.status == ScheduledJobStatus.PENDING,
            ScheduledJob.run_at <= now,
        )
        .order_by(ScheduledJob.run_at.asc())
        .limit(batch_size)
        .with_for_update(skip_locked=True)
    )
    jobs = list(db.execute(claim).scalars().all())

    # Mark claimed rows RUNNING and commit so other dispatchers skip them.
    for job in jobs:
        job.status = ScheduledJobStatus.RUNNING
    db.commit()

    done = failed = 0
    for job in jobs:
        handler = _HANDLERS.get(job.job_type)
        job.attempts += 1
        try:
            if handler is None:
                raise LookupError(f"No handler registered for job_type={job.job_type!r}")
            handler(db, job)
            job.status = ScheduledJobStatus.DONE
            job.executed_at = utcnow()
            job.last_error = None
            done += 1
        except Exception as exc:  # noqa: BLE001
            db.rollback()
            job.status = ScheduledJobStatus.FAILED
            job.last_error = f"{type(exc).__name__}: {exc}"[:1000]
            failed += 1
        db.commit()

    return {"done": done, "failed": failed, "claimed": len(jobs)}
