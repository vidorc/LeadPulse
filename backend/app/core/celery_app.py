"""Celery application + configuration.

The audit flagged Celery as underconfigured (no serializer, result expiry,
acks_late, prefetch limits, or beat schedule — beat ran but did nothing). This
configures it properly and defines the periodic tasks that *are* the product:
the outbox relay and the scheduled-job dispatcher (architecture review §8.3/§8.5).
"""

from __future__ import annotations

from celery import Celery
from celery.schedules import crontab  # noqa: F401  (available for future cron jobs)

from app.core.config import settings

celery = Celery(
    "leadpulse",
    broker=settings.REDIS_URL,
    backend=settings.REDIS_URL,
    include=[
        "app.tasks.lead_tasks",
        "app.tasks.workflow_tasks",
    ],
)

celery.conf.update(
    # Serialization
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    timezone="UTC",
    enable_utc=True,
    # Reliability: redeliver if a worker dies mid-task; bound prefetch so one
    # worker doesn't hoard the queue.
    task_acks_late=True,
    worker_prefetch_multiplier=1,
    task_reject_on_worker_lost=True,
    # Don't let result keys accumulate in Redis forever.
    result_expires=3600,
    # Periodic tasks (the durable scheduling + delivery substrate).
    beat_schedule={
        "dispatch-scheduled-jobs": {
            "task": "app.tasks.workflow_tasks.dispatch_scheduled_jobs",
            "schedule": 60.0,  # every minute (matches review's ~1-min floor)
        },
        "relay-outbox": {
            "task": "app.tasks.workflow_tasks.relay_outbox",
            "schedule": 30.0,  # every 30s
        },
        "scan-leaks": {
            "task": "app.tasks.workflow_tasks.scan_leaks",
            "schedule": 300.0,  # every 5 min (SLA windows are hours/days)
        },
    },
)
