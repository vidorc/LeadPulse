"""Lead routing & assignment.

A pragmatic round-robin assigner: distributes leads across the org's active
members (optionally within a team), balancing by current open-lead load so no
one rep is overloaded. The seam is deliberately simple but real — a richer
rule engine (by location/source/workload weighting) can replace the selection
logic behind this same interface without touching callers.
"""

from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.enums import EntityType, LeadStatus
from app.models.lead import Lead
from app.models.membership import Membership
from app.services import timeline


def _candidate_user_ids(db: Session, *, org_id: int, team_id: int | None) -> list[int]:
    stmt = select(Membership.user_id).where(
        Membership.org_id == org_id, Membership.deleted_at.is_(None)
    )
    if team_id is not None:
        stmt = stmt.where(Membership.team_id == team_id)
    return list(db.execute(stmt).scalars().all())


def assign_lead(db: Session, *, org_id: int, lead: Lead, team_id: int | None = None) -> int | None:
    """Assign the lead to the least-loaded eligible member. Returns the chosen
    user id (or None if the org has no members). Appends a timeline event.
    Does not commit — joins the caller's transaction."""
    candidates = _candidate_user_ids(db, org_id=org_id, team_id=team_id)
    if not candidates:
        return None

    # Current open-lead load per candidate (NEW/QUALIFYING/QUALIFIED/ASSIGNED).
    open_statuses = [
        LeadStatus.NEW,
        LeadStatus.QUALIFYING,
        LeadStatus.QUALIFIED,
        LeadStatus.ASSIGNED,
    ]
    load_rows = db.execute(
        select(Lead.owner_id, func.count(Lead.id))
        .where(
            Lead.org_id == org_id,
            Lead.owner_id.in_(candidates),
            Lead.status.in_(open_statuses),
            Lead.deleted_at.is_(None),
        )
        .group_by(Lead.owner_id)
    ).all()
    load = {uid: 0 for uid in candidates}
    for uid, count in load_rows:
        if uid is not None:
            load[uid] = count

    # Least-loaded wins; ties broken by lowest user id for determinism.
    chosen = min(candidates, key=lambda uid: (load[uid], uid))

    lead.owner_id = chosen
    if team_id is not None:
        lead.team_id = team_id
    if lead.status == LeadStatus.NEW:
        lead.status = LeadStatus.ASSIGNED

    timeline.append_event(
        db,
        org_id=org_id,
        entity_type=EntityType.LEAD,
        entity_id=lead.id,
        event_type="LEAD_ASSIGNED",
        payload={"owner_id": chosen},
    )
    return chosen
