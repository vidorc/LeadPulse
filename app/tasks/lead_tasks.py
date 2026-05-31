"""Async lead qualification pipeline.

Now tenant-aware (receives org_id) and aligned with the typed model (enum
status/decision, boolean review flag). Adds db.rollback() on failure so a
partial transaction never persists. The full hardening — idempotency guard,
Pydantic-validated AI contract, and outbox-delivered side effects — lands in
Phase 5; this version keeps the pipeline correct against the new schema.
"""

from __future__ import annotations

from app.core.celery_app import celery
from app.core.enums import Intent, LeadStatus, Urgency
from app.db.mixins import utcnow
from app.db.session import SessionLocal
from app.models.lead import Lead
from app.services.action_router import execute_action
from app.services.ai_qualifier import qualify_lead
from app.services.audit_logger import log_event
from app.services.decision_engine import decide_lead_action
from app.services.review_router import requires_review
from app.services.scoring_guardrails import normalize_score


def _coerce_enum(enum_cls, value, default):
    """Map an arbitrary AI string to an enum member, falling back safely."""
    if value is None:
        return default
    try:
        return enum_cls(str(value).lower())
    except ValueError:
        return default


@celery.task(
    bind=True,
    autoretry_for=(ConnectionError, TimeoutError),
    retry_backoff=True,
    retry_kwargs={"max_retries": 3},
)
def process_lead_ai(self, lead_id: int, org_id: int):
    db = SessionLocal()
    try:
        lead = (
            db.query(Lead)
            .filter(Lead.id == lead_id, Lead.org_id == org_id)
            .first()
        )
        if not lead:
            return

        lead.status = LeadStatus.QUALIFYING
        log_event(
            db,
            org_id=org_id,
            lead_id=lead.id,
            event_type="LEAD_RECEIVED",
            details="Lead entered async pipeline",
        )

        ai = qualify_lead(lead.source, lead.message)

        corrected_score = normalize_score(
            ai.get("score"), ai.get("urgency"), ai.get("budget")
        )
        review_needed = requires_review(corrected_score, ai.get("intent"))

        lead.intent = _coerce_enum(Intent, ai.get("intent"), Intent.UNKNOWN)
        lead.budget = str(ai.get("budget")) if ai.get("budget") is not None else None
        lead.timeline = ai.get("timeline")
        lead.location = ai.get("location")
        lead.urgency = _coerce_enum(Urgency, ai.get("urgency"), Urgency.LOW)
        lead.score = corrected_score
        lead.ai_summary = ai.get("ai_summary")

        log_event(
            db,
            org_id=org_id,
            lead_id=lead.id,
            event_type="AI_PROCESSED",
            details="Lead qualification completed",
        )

        if review_needed:
            lead.requires_human_review = True
            lead.status = LeadStatus.MANUAL_REVIEW
            lead.next_action = "await_human_review"
            lead.action_result = "Queued for manual review"
            log_event(
                db,
                org_id=org_id,
                lead_id=lead.id,
                event_type="MANUAL_REVIEW",
                details="Lead sent for human review",
            )
        else:
            decision = decide_lead_action(corrected_score, ai.get("urgency"))
            result = execute_action(decision["decision"], lead)
            lead.requires_human_review = False
            lead.status = LeadStatus.QUALIFIED
            lead.decision = decision["decision"]
            lead.next_action = decision["next_action"]
            lead.action_result = result
            log_event(
                db,
                org_id=org_id,
                lead_id=lead.id,
                event_type="DECISION_ASSIGNED",
                details=decision["decision"].value,
            )

        lead.processed_at = utcnow()
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()
