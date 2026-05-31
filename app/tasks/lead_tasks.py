from datetime import datetime

from app.core.celery_app import celery
from app.db.session import SessionLocal
from app.models.lead import Lead
from app.services.ai_qualifier import qualify_lead
from app.services.decision_engine import decide_lead_action
from app.services.action_router import execute_action
from app.services.scoring_guardrails import normalize_score
from app.services.review_router import requires_review
from app.services.audit_logger import log_event


@celery.task(
    bind=True,
    autoretry_for=(Exception,),
    retry_backoff=True,
    retry_kwargs={"max_retries": 3}
)
def process_lead_ai(self, lead_id: int):
    db = SessionLocal()

    try:
        lead = db.query(Lead).filter(
            Lead.id == lead_id
        ).first()

        if not lead:
            return

        log_event(
            db,
            lead.id,
            "LEAD_RECEIVED",
            "Lead entered async pipeline"
        )

        ai_result = qualify_lead(
            lead.source,
            lead.message
        )

        log_event(
            db,
            lead.id,
            "AI_PROCESSED",
            "Lead qualification completed"
        )

        corrected_score = normalize_score(
            ai_result["score"],
            ai_result["urgency"],
            ai_result["budget"]
        )

        review_needed = requires_review(
            corrected_score,
            ai_result["intent"]
        )

        lead.intent = ai_result["intent"]
        lead.budget = ai_result["budget"]
        lead.location = ai_result["location"]
        lead.urgency = ai_result["urgency"]
        lead.score = corrected_score
        lead.ai_summary = ai_result["ai_summary"]

        if review_needed:
            lead.requires_human_review = "yes"
            lead.decision = "manual_review"
            lead.next_action = "await_human_review"
            lead.action_result = "Queued for manual review"

            log_event(
                db,
                lead.id,
                "MANUAL_REVIEW",
                "Lead sent for human review"
            )

        else:
            decision_result = decide_lead_action(
                corrected_score,
                ai_result["urgency"]
            )

            action_result = execute_action(
                decision_result["decision"],
                lead
            )

            lead.requires_human_review = "no"
            lead.decision = decision_result["decision"]
            lead.next_action = decision_result["next_action"]
            lead.action_result = action_result

            log_event(
                db,
                lead.id,
                "DECISION_ASSIGNED",
                decision_result["decision"]
            )

        lead.processed_at = datetime.utcnow()

        db.commit()

    finally:
        db.close()