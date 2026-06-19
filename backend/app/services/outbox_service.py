"""Outbox service — enqueue (in-transaction) and relay (deliver) messages.

`enqueue` writes a pending row in the caller's transaction with a dedupe_key,
so the same logical notification is never sent twice even if the producing
task retries. `relay_pending` is run by Beat: it claims due rows, delivers via
the channel adapter, and marks sent / schedules a backoff retry / dead-letters.
"""

from __future__ import annotations

from datetime import timedelta

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

from app.core.enums import OutboxChannel, OutboxStatus
from app.db.mixins import utcnow
from app.models.outbox import OutboxMessage

# Exponential backoff schedule (seconds) indexed by attempt number.
_BACKOFF_SECONDS = [0, 30, 120, 600, 3600]


def enqueue(
    db: Session,
    *,
    org_id: int,
    channel: OutboxChannel,
    dedupe_key: str,
    payload: dict,
    max_attempts: int = 5,
) -> None:
    """Enqueue a message idempotently. If a row with the same (org_id,
    dedupe_key) already exists, this is a no-op (ON CONFLICT DO NOTHING).
    Does not commit — joins the caller's transaction."""
    stmt = (
        pg_insert(OutboxMessage)
        .values(
            org_id=org_id,
            channel=channel,
            dedupe_key=dedupe_key,
            payload=payload,
            status=OutboxStatus.PENDING,
            max_attempts=max_attempts,
            next_attempt_at=utcnow(),
            created_at=utcnow(),
            updated_at=utcnow(),
        )
        .on_conflict_do_nothing(index_elements=["org_id", "dedupe_key"])
    )
    db.execute(stmt)


def _deliver(message: OutboxMessage) -> None:
    """Dispatch one message to its channel adapter. Raises on failure."""
    from app.services.email_service import send_email
    from app.services.notification_service import dispatch_webhook

    payload = message.payload or {}
    if message.channel == OutboxChannel.EMAIL:
        send_email(
            to=payload["to"],
            subject=payload.get("subject", "Notification"),
            body=payload.get("body", ""),
        )
    elif message.channel == OutboxChannel.WEBHOOK:
        dispatch_webhook(payload)
    elif message.channel == OutboxChannel.IN_APP:
        # In-app notifications are read from the table directly; nothing to send.
        return
    else:  # pragma: no cover - guarded by enum
        raise ValueError(f"Unknown channel {message.channel}")


def relay_pending(db: Session, *, batch_size: int = 50) -> dict[str, int]:
    """Deliver due pending messages. Returns counts for observability."""
    now = utcnow()
    stmt = (
        select(OutboxMessage)
        .where(
            OutboxMessage.status == OutboxStatus.PENDING,
            OutboxMessage.next_attempt_at <= now,
        )
        .order_by(OutboxMessage.next_attempt_at.asc())
        .limit(batch_size)
        .with_for_update(skip_locked=True)
    )
    messages = list(db.execute(stmt).scalars().all())
    sent = failed = dead = 0

    for msg in messages:
        msg.attempts += 1
        try:
            _deliver(msg)
            msg.status = OutboxStatus.SENT
            msg.sent_at = utcnow()
            msg.last_error = None
            sent += 1
        except Exception as exc:  # noqa: BLE001 - record and retry/dead-letter
            msg.last_error = f"{type(exc).__name__}: {exc}"[:1000]
            if msg.attempts >= msg.max_attempts:
                msg.status = OutboxStatus.DEAD
                dead += 1
            else:
                idx = min(msg.attempts, len(_BACKOFF_SECONDS) - 1)
                msg.next_attempt_at = utcnow() + timedelta(seconds=_BACKOFF_SECONDS[idx])
                failed += 1

    db.commit()
    return {"sent": sent, "retry": failed, "dead": dead, "claimed": len(messages)}
