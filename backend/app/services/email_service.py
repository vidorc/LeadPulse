"""SMTP email delivery adapter. Credentials come from `settings`, never hardcoded.

This is a low-level adapter: it only knows how to send a message. The decision
to send, idempotency, and retry/backoff all live in the outbox relay, which
calls this.
"""

from __future__ import annotations

import smtplib
from email.message import EmailMessage

from app.core.config import settings


def send_email(*, to: str, subject: str, body: str, from_addr: str | None = None) -> None:
    """Send a plaintext email via configured SMTP. Raises on failure so the
    outbox relay can record it and retry with backoff."""
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
