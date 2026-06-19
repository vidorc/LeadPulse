"""Revenue Leak Detection — the SLA scanner (the product's headline feature).

Realizes the architecture thesis (§0): leak detection is transition-absence
detection over the timeline + state. SLA policies are data; the scanner reads
each active policy and finds entities breaching its window, creating a LeakAlert
(idempotently — one OPEN alert per entity+type) plus a timeline event and, if
the policy says so, an outbox notification.

Runs in the async plane (Beat). It is org-agnostic at the top: it iterates
active policies across all tenants, each carrying its own org_id.
"""

from __future__ import annotations

from datetime import timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.enums import (
    EntityType,
    LeakAlertStatus,
    LeakType,
    MeetingStatus,
    OpportunityStage,
    OutboxChannel,
    ProposalStatus,
)
from app.db.mixins import utcnow
from app.models.event import Event
from app.models.leak import LeakAlert, SLAPolicy
from app.models.lead import Lead
from app.models.meeting import Meeting
from app.models.opportunity import Opportunity
from app.models.proposal import Proposal
from app.services import outbox_service, timeline

# Statuses meaning a lead has had no human contact yet.
_UNCONTACTED_LEAD_STATUSES = ("new", "qualifying", "qualified", "manual_review")


def _breaching_entities(db: Session, policy: SLAPolicy) -> list[tuple[EntityType, int, str]]:
    """Return (entity_type, entity_id, detail) tuples breaching this policy."""
    now = utcnow()
    cutoff = now - timedelta(hours=policy.threshold_hours)
    org_id = policy.org_id

    if policy.leak_type == LeakType.LEAD_IGNORED:
        rows = db.execute(
            select(Lead.id).where(
                Lead.org_id == org_id,
                Lead.deleted_at.is_(None),
                Lead.created_at < cutoff,
                Lead.status.in_(_UNCONTACTED_LEAD_STATUSES),
            )
        ).scalars().all()
        return [
            (EntityType.LEAD, lid, f"No contact within {policy.threshold_hours}h of creation")
            for lid in rows
        ]

    if policy.leak_type == LeakType.OPP_STALLED:
        rows = db.execute(
            select(Opportunity.id).where(
                Opportunity.org_id == org_id,
                Opportunity.deleted_at.is_(None),
                Opportunity.stage_changed_at < cutoff,
                Opportunity.stage.notin_(
                    [OpportunityStage.WON.value, OpportunityStage.LOST.value]
                ),
            )
        ).scalars().all()
        return [
            (EntityType.OPPORTUNITY, oid, f"No stage change within {policy.threshold_hours}h")
            for oid in rows
        ]

    if policy.leak_type == LeakType.MEETING_MISSED:
        # scheduled_at passed (threshold can be 0) and not completed/cancelled.
        rows = db.execute(
            select(Meeting.id).where(
                Meeting.org_id == org_id,
                Meeting.deleted_at.is_(None),
                Meeting.scheduled_at < cutoff,
                Meeting.status == MeetingStatus.SCHEDULED,
            )
        ).scalars().all()
        return [
            (EntityType.MEETING, mid, "Scheduled time passed without completion")
            for mid in rows
        ]

    if policy.leak_type == LeakType.PROPOSAL_COLD:
        # Sent proposals with no follow-up event since sent_at, past threshold.
        sent = db.execute(
            select(Proposal.id, Proposal.sent_at).where(
                Proposal.org_id == org_id,
                Proposal.deleted_at.is_(None),
                Proposal.status == ProposalStatus.SENT,
                Proposal.sent_at < cutoff,
            )
        ).all()
        breaching = []
        for pid, sent_at in sent:
            followup = db.execute(
                select(Event.id).where(
                    Event.org_id == org_id,
                    Event.entity_type == EntityType.PROPOSAL,
                    Event.entity_id == pid,
                    Event.event_type == "PROPOSAL_FOLLOWUP",
                    Event.occurred_at >= sent_at,
                ).limit(1)
            ).scalar_one_or_none()
            if followup is None:
                breaching.append(
                    (EntityType.PROPOSAL, pid, f"No follow-up within {policy.threshold_hours}h of send")
                )
        return breaching

    return []


def _has_open_alert(db: Session, policy: SLAPolicy, entity_type: EntityType, entity_id: int) -> bool:
    return db.execute(
        select(LeakAlert.id).where(
            LeakAlert.org_id == policy.org_id,
            LeakAlert.leak_type == policy.leak_type,
            LeakAlert.entity_type == entity_type,
            LeakAlert.entity_id == entity_id,
            LeakAlert.status == LeakAlertStatus.OPEN,
        ).limit(1)
    ).scalar_one_or_none() is not None


def scan(db: Session) -> dict[str, int]:
    """Evaluate all active SLA policies and raise alerts for new breaches.
    Returns counts for observability."""
    policies = db.execute(
        select(SLAPolicy).where(SLAPolicy.is_active.is_(True))
    ).scalars().all()

    created = 0
    scanned = 0
    for policy in policies:
        scanned += 1
        for entity_type, entity_id, detail in _breaching_entities(db, policy):
            if _has_open_alert(db, policy, entity_type, entity_id):
                continue
            now = utcnow()
            alert = LeakAlert(
                org_id=policy.org_id,
                leak_type=policy.leak_type,
                entity_type=entity_type,
                entity_id=entity_id,
                severity=policy.severity,
                status=LeakAlertStatus.OPEN,
                detail=detail,
                detected_at=now,
            )
            db.add(alert)
            db.flush()
            timeline.append_event(
                db,
                org_id=policy.org_id,
                entity_type=entity_type,
                entity_id=entity_id,
                event_type="LEAK_DETECTED",
                payload={"leak_type": policy.leak_type.value, "severity": policy.severity.value},
            )
            if policy.notify:
                outbox_service.enqueue(
                    db,
                    org_id=policy.org_id,
                    channel=OutboxChannel.IN_APP,
                    dedupe_key=f"leak:{policy.leak_type.value}:{entity_type.value}:{entity_id}",
                    payload={
                        "leak_type": policy.leak_type.value,
                        "entity_type": entity_type.value,
                        "entity_id": entity_id,
                        "detail": detail,
                    },
                )
            created += 1

    db.commit()
    return {"policies_scanned": scanned, "alerts_created": created}
