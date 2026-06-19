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
from app.services import leak_detection, outbox_service, scheduler

# Import handler-registering services so their scheduler.register_handler()
# side effects run in the worker process (the dispatcher resolves job_type ->
# handler from this registry). Without these imports the worker would have an
# empty registry and fail every scheduled job.
import app.services.followup_service  # noqa: F401,E402

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


@celery.task(name="app.tasks.workflow_tasks.scan_leaks")
def scan_leaks() -> dict:
    """Evaluate all active SLA policies and raise leak alerts for breaches."""
    db = SessionLocal()
    try:
        result = leak_detection.scan(db)
        if result["alerts_created"]:
            logger.info("leak scan", extra={"result": result})
        return result
    finally:
        db.close()
