"""Beat-driven workflow tasks: the durable scheduling + delivery substrate.

These are the periodic tasks wired in celery_app.beat_schedule. They are thin
shells: open a session, call the service, close — business logic lives in the
services (architecture review §6). This is where the follow-up engine and leak
scanner (Phase 6) get their heartbeat.
"""

from __future__ import annotations

import logging

from app.core.celery_app import celery
from app.db.session import SessionLocal
from app.services import outbox_service, scheduler

logger = logging.getLogger(__name__)


@celery.task(name="app.tasks.workflow_tasks.dispatch_scheduled_jobs")
def dispatch_scheduled_jobs() -> dict:
    """Claim and execute due scheduled jobs (follow-up steps, rescans, etc.)."""
    db = SessionLocal()
    try:
        result = scheduler.dispatch_due(db)
        if result["claimed"]:
            logger.info("scheduled-jobs dispatched", extra={"result": result})
        return result
    finally:
        db.close()


@celery.task(name="app.tasks.workflow_tasks.relay_outbox")
def relay_outbox() -> dict:
    """Deliver due pending outbox messages (email/webhook), with backoff."""
    db = SessionLocal()
    try:
        result = outbox_service.relay_pending(db)
        if result["claimed"]:
            logger.info("outbox relayed", extra={"result": result})
        return result
    finally:
        db.close()
