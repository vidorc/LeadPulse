"""Multi-channel lead ingestion.

Gates the paid-AI endpoint (architecture review §8.1): inbound channel
webhooks are authenticated by an HMAC signature over the raw body using the
org's `ingest_secret`, deduplicated by an idempotency key, and only then
persisted + enqueued for qualification. CSV upload is the batch variant
(one lead per row, sharing the dedup + routing path).
"""

from __future__ import annotations

import csv
import hashlib
import hmac
import io

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.enums import EntityType, LeadStatus
from app.models.lead import Lead
from app.models.organization import Organization
from app.services import routing_service, timeline


class IngestionError(Exception):
    """Raised for invalid signature / unknown org / malformed payload."""


def verify_signature(*, secret: str, raw_body: bytes, signature: str) -> bool:
    """Constant-time HMAC-SHA256 verification of the raw request body."""
    expected = hmac.new(secret.encode(), raw_body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, signature or "")


def resolve_org(db: Session, slug: str) -> Organization:
    org = db.execute(
        select(Organization).where(
            Organization.slug == slug, Organization.deleted_at.is_(None)
        )
    ).scalar_one_or_none()
    if org is None:
        raise IngestionError("Unknown organization")
    return org


def ingest_lead(
    db: Session,
    *,
    org: Organization,
    source: str,
    name: str | None,
    email: str | None,
    phone: str | None,
    message: str | None,
    idempotency_key: str | None,
    auto_route: bool = True,
) -> tuple[Lead, bool]:
    """Create a lead idempotently. Returns (lead, created). If a lead with the
    same (org, idempotency_key) already exists, returns it with created=False
    and does NOT re-enqueue. Does not commit — caller owns the transaction."""
    if idempotency_key:
        existing = db.execute(
            select(Lead).where(
                Lead.org_id == org.id, Lead.idempotency_key == idempotency_key
            )
        ).scalar_one_or_none()
        if existing is not None:
            return existing, False

    lead = Lead(
        org_id=org.id,
        name=name,
        email=email,
        phone=phone,
        source=source,
        message=message,
        idempotency_key=idempotency_key,
        status=LeadStatus.NEW,
    )
    db.add(lead)
    db.flush()

    timeline.append_event(
        db,
        org_id=org.id,
        entity_type=EntityType.LEAD,
        entity_id=lead.id,
        event_type="LEAD_INGESTED",
        payload={"source": source, "channel": "webhook"},
    )

    if auto_route:
        routing_service.assign_lead(db, org_id=org.id, lead=lead)

    return lead, True


def parse_csv(raw: bytes) -> list[dict]:
    """Parse an uploaded CSV into row dicts. Expected headers: name, email,
    phone, message (source defaults to 'csv'). Raises on undecodable input."""
    try:
        text = raw.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise IngestionError("CSV must be UTF-8 encoded") from exc
    reader = csv.DictReader(io.StringIO(text))
    rows = []
    for i, row in enumerate(reader):
        rows.append(
            {
                "name": (row.get("name") or "").strip() or None,
                "email": (row.get("email") or "").strip() or None,
                "phone": (row.get("phone") or "").strip() or None,
                "message": (row.get("message") or "").strip() or None,
                "row_index": i,
            }
        )
    return rows
