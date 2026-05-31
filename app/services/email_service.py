"""SMTP email delivery. Credentials come from `settings`, never hardcoded.

This module only knows how to *send*; the decision to send and the
exactly-once guarantee live in the outbox relay (see notifications domain).
Recipient values are passed explicitly by the caller.
"""

from __future__ import annotations

import smtplib
from email.message import EmailMessage

from app.core.config import settings


def send_email(
    *,
    to: str,
    subject: str,
    body: str,
    from_addr: str | None = None,
) -> None:
    """Send a plaintext email via configured SMTP. Raises on failure so the
    caller (outbox relay) can record the failure and retry with backoff."""
    if not settings.SMTP_USERNAME or not settings.SMTP_PASSWORD:
        raise RuntimeError("SMTP credentials are not configured.")

    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = from_addr or settings.SMTP_FROM
    msg["To"] = to
    msg.set_content(body)

    with smtplib.SMTP(settings.SMTP_HOST, settings.SMTP_PORT, timeout=15) as server:
        server.starttls()
        server.login(settings.SMTP_USERNAME, settings.SMTP_PASSWORD)
        server.send_message(msg)


def send_hot_lead_email(
    lead_name: str,
    lead_phone: str,
    lead_email: str,
    budget: str,
    location: str,
    recipient: str | None = None,
) -> None:
    """Compose and send the hot-lead alert. The body is built from explicit
    fields (no untrusted interpolation into headers)."""
    body = (
        "HOT LEAD ALERT\n\n"
        f"Name: {lead_name}\n"
        f"Phone: {lead_phone}\n"
        f"Email: {lead_email}\n"
        f"Budget: {budget}\n"
        f"Location: {location}\n"
    )
    send_email(
        to=recipient or settings.SMTP_FROM,
        subject="HOT LEAD ALERT",
        body=body,
    )
