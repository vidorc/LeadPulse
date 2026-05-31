"""Hot-lead notification fan-out (email + optional webhook).

Configuration comes from `settings` (no hardcoded webhook URL or creds).
Failures are logged via structured logging and surfaced in the return value
rather than swallowed by `print()`. In Phase 5 the actual delivery moves
behind the outbox relay for exactly-once semantics; this module remains the
channel adapter it calls.
"""

from __future__ import annotations

import logging

import requests

from app.core.config import settings
from app.services.email_service import send_hot_lead_email

logger = logging.getLogger(__name__)


def notify_hot_lead(lead) -> str:
    """Best-effort delivery to all configured channels. Returns a status
    string summarizing each channel's outcome."""
    email_status = "email_skipped"
    webhook_status = "webhook_skipped"

    # ---- Email ----
    if settings.SMTP_USERNAME and settings.SMTP_PASSWORD:
        try:
            send_hot_lead_email(
                lead.name,
                lead.phone,
                lead.email,
                lead.budget,
                lead.location,
            )
            email_status = "email_sent"
        except Exception:  # noqa: BLE001 - report, don't crash the pipeline
            logger.exception("Hot-lead email delivery failed", extra={"lead_id": getattr(lead, "id", None)})
            email_status = "email_failed"

    # ---- Webhook ----
    if settings.WEBHOOK_URL:
        try:
            response = requests.post(
                settings.WEBHOOK_URL,
                json={
                    "lead_id": lead.id,
                    "name": lead.name,
                    "phone": lead.phone,
                    "email": lead.email,
                    "budget": lead.budget,
                    "location": lead.location,
                    "decision": "hot_lead",
                },
                timeout=10,
            )
            response.raise_for_status()
            webhook_status = "webhook_sent"
        except Exception:  # noqa: BLE001
            logger.exception("Hot-lead webhook delivery failed", extra={"lead_id": getattr(lead, "id", None)})
            webhook_status = "webhook_failed"

    return f"{email_status} | {webhook_status}"
