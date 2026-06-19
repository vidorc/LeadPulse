"""Follow-up engine service.

Sits on the Phase 5 scheduling substrate: enrolling a lead schedules the first
step as a ScheduledJob; the step handler executes the step (enqueues the
message via the outbox) and schedules the next step. When a rep engages the
lead, ``cancel_for_lead`` cancels the enrollment and its pending jobs — the
exact capability the review said Celery eta couldn't provide.

The step handler is registered with the scheduler at import time, so the Beat
dispatcher can run follow-up jobs.
"""

from __future__ import annotations

from datetime import timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.enums import (
    EnrollmentStatus,
    EntityType,
    OutboxChannel,
)
from app.core.tenant import TenantContext
from app.db.mixins import utcnow
from app.models.lead import Lead
from app.models.sequence import Enrollment, Sequence, SequenceStep
from app.services import outbox_service, scheduler, timeline

FOLLOWUP_JOB_TYPE = "followup_step"


def _schedule_step(db: Session, *, org_id: int, enrollment: Enrollment, step: SequenceStep) -> None:
    run_at = enrollment.enrolled_at + timedelta(hours=step.delay_hours)
    scheduler.schedule(
        db,
        org_id=org_id,
        job_type=FOLLOWUP_JOB_TYPE,
        run_at=run_at,
        entity_type=EntityType.ENROLLMENT,
        entity_id=enrollment.id,
        payload={"step_id": step.id},
    )


class FollowUpService:
    def __init__(self, db: Session, ctx: TenantContext):
        self.db = db
        self.ctx = ctx

    def create_sequence(self, *, name: str, steps: list[dict]) -> Sequence:
        seq = Sequence(org_id=self.ctx.org_id, name=name)
        self.db.add(seq)
        self.db.flush()
        for i, step in enumerate(steps):
            self.db.add(
                SequenceStep(
                    org_id=self.ctx.org_id,
                    sequence_id=seq.id,
                    step_order=i,
                    delay_hours=step["delay_hours"],
                    action=step.get("action", "email"),
                    subject=step.get("subject"),
                    body=step.get("body"),
                )
            )
        self.db.commit()
        self.db.refresh(seq)
        return seq

    def enroll(self, *, lead_id: int, sequence_id: int) -> Enrollment:
        seq = self.db.get(Sequence, sequence_id)
        if seq is None or seq.org_id != self.ctx.org_id:
            raise LookupError("Sequence not found")
        lead = self.db.get(Lead, lead_id)
        if lead is None or lead.org_id != self.ctx.org_id:
            raise LookupError("Lead not found")

        existing = self.db.execute(
            select(Enrollment).where(
                Enrollment.sequence_id == sequence_id,
                Enrollment.lead_id == lead_id,
                Enrollment.status == EnrollmentStatus.ACTIVE,
            )
        ).scalar_one_or_none()
        if existing is not None:
            return existing

        enrollment = Enrollment(
            org_id=self.ctx.org_id,
            sequence_id=sequence_id,
            lead_id=lead_id,
            status=EnrollmentStatus.ACTIVE,
            current_step=0,
            enrolled_at=utcnow(),
        )
        self.db.add(enrollment)
        self.db.flush()

        first_step = self.db.execute(
            select(SequenceStep)
            .where(SequenceStep.sequence_id == sequence_id)
            .order_by(SequenceStep.step_order.asc())
            .limit(1)
        ).scalar_one_or_none()
        if first_step is not None:
            _schedule_step(self.db, org_id=self.ctx.org_id, enrollment=enrollment, step=first_step)

        timeline.append_event(
            self.db,
            org_id=self.ctx.org_id,
            entity_type=EntityType.LEAD,
            entity_id=lead_id,
            event_type="SEQUENCE_ENROLLED",
            payload={"sequence_id": sequence_id, "enrollment_id": enrollment.id},
        )
        self.db.commit()
        self.db.refresh(enrollment)
        return enrollment

    def cancel_for_lead(self, *, lead_id: int) -> int:
        """Cancel all active enrollments for a lead and their pending jobs.
        Called when a rep engages (so we stop auto-following-up)."""
        enrollments = self.db.execute(
            select(Enrollment).where(
                Enrollment.org_id == self.ctx.org_id,
                Enrollment.lead_id == lead_id,
                Enrollment.status == EnrollmentStatus.ACTIVE,
            )
        ).scalars().all()
        for enr in enrollments:
            enr.status = EnrollmentStatus.CANCELLED
            scheduler.cancel_for_entity(
                self.db,
                org_id=self.ctx.org_id,
                entity_type=EntityType.ENROLLMENT,
                entity_id=enr.id,
                job_type=FOLLOWUP_JOB_TYPE,
                commit=False,
            )
        self.db.commit()
        return len(enrollments)


def _execute_followup_step(db: Session, job) -> None:
    """Scheduler handler: run the due step, enqueue its message, schedule next.

    Runs inside the scheduler's per-job transaction. Tenant scope comes from
    the job's org_id (the async plane has no HTTP principal).
    """
    org_id = job.org_id
    enrollment = db.get(Enrollment, job.entity_id)
    if enrollment is None or enrollment.status != EnrollmentStatus.ACTIVE:
        return  # cancelled/completed since scheduling — no-op

    step_id = (job.payload or {}).get("step_id")
    step = db.get(SequenceStep, step_id) if step_id else None
    if step is None:
        return

    lead = db.get(Lead, enrollment.lead_id)
    if lead is not None and step.action == "email" and lead.email:
        outbox_service.enqueue(
            db,
            org_id=org_id,
            channel=OutboxChannel.EMAIL,
            dedupe_key=f"followup:{enrollment.id}:{step.id}",
            payload={
                "to": lead.email,
                "subject": step.subject or "Following up",
                "body": step.body or "",
            },
        )

    enrollment.current_step = step.step_order + 1
    timeline.append_event(
        db,
        org_id=org_id,
        entity_type=EntityType.LEAD,
        entity_id=enrollment.lead_id,
        event_type="FOLLOWUP_SENT",
        payload={"enrollment_id": enrollment.id, "step_order": step.step_order},
    )

    # Schedule the next step, or complete the enrollment.
    next_step = db.execute(
        select(SequenceStep)
        .where(
            SequenceStep.sequence_id == enrollment.sequence_id,
            SequenceStep.step_order > step.step_order,
        )
        .order_by(SequenceStep.step_order.asc())
        .limit(1)
    ).scalar_one_or_none()
    if next_step is not None:
        _schedule_step(db, org_id=org_id, enrollment=enrollment, step=next_step)
    else:
        enrollment.status = EnrollmentStatus.COMPLETED
        enrollment.completed_at = utcnow()


# Register the handler so the Beat dispatcher can run follow-up jobs.
scheduler.register_handler(FOLLOWUP_JOB_TYPE, _execute_followup_step)
