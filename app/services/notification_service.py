"""Notification channel adapters + outbox enqueue helpers.

The exactly-once fix (architecture review §8.5): instead of sending email /
webhook inline inside the qualification task — where a retry duplicates them —
we enqueue an outbox row in the same transaction as the state change. The
Beat-driven relay (outbox_service.relay_pending) performs the actual send.

`dispatch_webhook` and `send_email` (email_service) are the low-level adapters
the relay calls; `enqueue_hot_lead_alert` is what the domain calls.
"""

from __future__ import annotations

import logging

import requests
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.enums import OutboxChannel
from app.services import outbox_service

logger = logging.getLogger(__name__)


def dispatch_webhook(payload: dict) -> None:
    """Deliver a webhook. Raises on failure so the relay can retry/dead-letter."""
    url = payload.get("url") or settings.WEBHOOK_URL
    if not url:
        raise RuntimeError("No webhook URL configured")
    response = requests.post(url, json=payload.get("body", payload), timeout=10)
    response.raise_for_status()


def enqueue_hot_lead_alert(db: Session, *, org_id: int, lead) -> None:
    """Enqueue hot-lead notifications (email + webhook if configured) into the
    outbox. Idempotent per lead via the dedupe key — a task retry won't double
    enqueue, and the relay won't double send."""
    body = (
        "HOT LEAD ALERT\n\n"
        f"Name: {lead.name}\n"
        f"Phone: {lead.phone}\n"
        f"Email: {lead.email}\n"
        f"Budget: {lead.budget}\n"
        f"Location: {lead.location}\n"
    )

    if settings.SMTP_USERNAME and settings.SMTP_PASSWORD:
        outbox_service.enqueue(
            db,
            org_id=org_id,
            channel=OutboxChannel.EMAIL,
            dedupe_key=f"hot_lead_email:lead:{lead.id}",
            payload={
                "to": settings.SMTP_FROM,
                "subject": "HOT LEAD ALERT",
                "body": body,
            },
        )

    if settings.WEBHOOK_URL:
        outbox_service.enqueue(
            db,
            org_id=org_id,
            channel=OutboxChannel.WEBHOOK,
            dedupe_key=f"hot_lead_webhook:lead:{lead.id}",
            payload={
                "url": settings.WEBHOOK_URL,
                "body": {
                    "lead_id": lead.id,
                    "name": lead.name,
                    "phone": lead.phone,
                    "email": lead.email,
                    "budget": lead.budget,
                    "location": lead.location,
                    "decision": "hot_lead",
                },
            },
        )
