"""Async lead qualification pipeline — idempotent, validated, outbox-safe.

Resolves the audit's three pipeline criticals (architecture review §8.2):
  * idempotency      — a processed lead is skipped, so a retry can't re-run
                       side effects;
  * validated AI     — raw LLM output goes through QualificationContract
                       (bounded score, coerced enums) before touching state;
  * exactly-once     — state change, timeline events, and the hot-lead
                       notification (outbox enqueue) all commit in ONE
                       transaction; delivery happens later via the relay, so a
                       retry can never double-send.

autoretry is narrowed to transient errors only (the old `(Exception,)` retried
on programming errors and a missing key, burning all retries pointlessly).
"""

from __future__ import annotations

from app.core.celery_app import celery
from app.core.enums import EntityType, LeadDecision, LeadStatus
from app.db.mixins import utcnow
from app.db.session import SessionLocal
from app.models.lead import Lead
from app.schemas.qualification import QualificationContract
from app.services import timeline
from app.services.action_router import describe_action
from app.services.ai_qualifier import qualify_lead
from app.services.decision_engine import decide_lead_action
from app.services.notification_service import enqueue_hot_lead_alert
from app.services.review_router import requires_review
from app.services.scoring_guardrails import normalize_score

# Statuses that mean the lead has already been through the pipeline.
_TERMINAL_STATUSES = {
    LeadStatus.QUALIFIED,
    LeadStatus.MANUAL_REVIEW,
    LeadStatus.ASSIGNED,
    LeadStatus.CONVERTED,
    LeadStatus.LOST,
}


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
        if lead is None:
            return

        # ---- Idempotency guard ----
        if lead.processed_at is not None or lead.status in _TERMINAL_STATUSES:
            return

        lead.status = LeadStatus.QUALIFYING
        timeline.append_event(
            db,
            org_id=org_id,
            entity_type=EntityType.LEAD,
            entity_id=lead.id,
            event_type="LEAD_RECEIVED",
            payload={"source": lead.source},
        )

        # ---- Validated AI output (anti-corruption layer) ----
        raw = qualify_lead(lead.source, lead.message)
        q = QualificationContract.from_raw(raw)

        corrected_score = normalize_score(q.score, q.urgency, q.budget)
        review_needed = requires_review(corrected_score, q.intent)

        lead.intent = q.intent
        lead.budget = q.budget
        lead.budget_amount = q.budget_amount
        lead.timeline = q.timeline
        lead.location = q.location
        lead.urgency = q.urgency
        lead.score = corrected_score
        lead.ai_summary = q.ai_summary

        timeline.append_event(
            db,
            org_id=org_id,
            entity_type=EntityType.LEAD,
            entity_id=lead.id,
            event_type="AI_PROCESSED",
            payload={"score": corrected_score, "intent": q.intent.value},
        )

        if review_needed:
            lead.requires_human_review = True
            lead.status = LeadStatus.MANUAL_REVIEW
            lead.decision = LeadDecision.MANUAL_REVIEW
            lead.next_action = "await_human_review"
            lead.action_result = "Queued for manual review"
            timeline.append_event(
                db,
                org_id=org_id,
                entity_type=EntityType.LEAD,
                entity_id=lead.id,
                event_type="MANUAL_REVIEW",
            )
        else:
            decision = decide_lead_action(corrected_score, q.urgency)
            lead.requires_human_review = False
            lead.status = LeadStatus.QUALIFIED
            lead.decision = decision["decision"]
            lead.next_action = decision["next_action"]
            lead.action_result = describe_action(decision["decision"])

            # Enqueue side effect in THIS transaction (exactly-once via outbox).
            if decision["decision"] == LeadDecision.HOT_LEAD:
                enqueue_hot_lead_alert(db, org_id=org_id, lead=lead)

            timeline.append_event(
                db,
                org_id=org_id,
                entity_type=EntityType.LEAD,
                entity_id=lead.id,
                event_type="DECISION_ASSIGNED",
                payload={"decision": decision["decision"].value},
            )

        lead.processed_at = utcnow()
        db.commit()  # state + events + outbox commit atomically
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()
