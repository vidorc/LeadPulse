"""Opportunity service — create deals and transition stages.

Every stage change updates ``stage_changed_at`` (what "stalled" is measured
against) and appends a timeline event, in one transaction. Creating/sending a
proposal and scheduling/completing a meeting likewise stamp their first-class
timestamps and emit events, so leak detection has authoritative data to query.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy.orm import Session

from app.core.enums import (
    EntityType,
    MeetingStatus,
    OpportunityStage,
    ProposalStatus,
)
from app.core.tenant import TenantContext
from app.db.mixins import utcnow
from app.db.repository import TenantRepository
from app.models.meeting import Meeting
from app.models.opportunity import Opportunity
from app.models.proposal import Proposal
from app.services import timeline


class OpportunityRepository(TenantRepository[Opportunity]):
    model = Opportunity


class OpportunityService:
    def __init__(self, db: Session, ctx: TenantContext):
        self.db = db
        self.ctx = ctx
        self.repo = OpportunityRepository(db, ctx)

    def create(
        self,
        *,
        title: str,
        lead_id: int | None = None,
        value_amount: float | None = None,
        owner_id: int | None = None,
        team_id: int | None = None,
    ) -> Opportunity:
        now = utcnow()
        opp = Opportunity(
            title=title,
            lead_id=lead_id,
            value_amount=value_amount,
            owner_id=owner_id,
            team_id=team_id,
            stage=OpportunityStage.NEW,
            stage_changed_at=now,
        )
        self.repo.add(opp)
        self.db.flush()
        timeline.append_event(
            self.db,
            org_id=self.ctx.org_id,
            entity_type=EntityType.OPPORTUNITY,
            entity_id=opp.id,
            event_type="OPPORTUNITY_CREATED",
            payload={"title": title, "value": float(value_amount or 0)},
            actor=self.ctx.email,
        )
        self.db.commit()
        self.db.refresh(opp)
        return opp

    def transition_stage(self, opp_id: int, new_stage: OpportunityStage) -> Opportunity:
        opp = self.repo.get(opp_id)
        if opp is None:
            raise LookupError("Opportunity not found")
        if opp.stage == new_stage:
            return opp

        previous = opp.stage
        opp.stage = new_stage
        opp.stage_changed_at = utcnow()
        if new_stage.is_terminal:
            opp.closed_at = utcnow()

        timeline.append_event(
            self.db,
            org_id=self.ctx.org_id,
            entity_type=EntityType.OPPORTUNITY,
            entity_id=opp.id,
            event_type="STAGE_CHANGED",
            payload={"from": previous.value, "to": new_stage.value},
            actor=self.ctx.email,
        )
        self.db.commit()
        self.db.refresh(opp)
        return opp

    # ---- Proposals ----
    def add_proposal(
        self, opp_id: int, *, title: str, amount: float | None = None
    ) -> Proposal:
        opp = self.repo.get(opp_id)
        if opp is None:
            raise LookupError("Opportunity not found")
        proposal = Proposal(
            org_id=self.ctx.org_id,
            opportunity_id=opp.id,
            title=title,
            amount=amount,
            status=ProposalStatus.DRAFT,
        )
        self.db.add(proposal)
        self.db.commit()
        self.db.refresh(proposal)
        return proposal

    def send_proposal(self, proposal_id: int) -> Proposal:
        proposal = self.db.get(Proposal, proposal_id)
        if proposal is None or proposal.org_id != self.ctx.org_id:
            raise LookupError("Proposal not found")
        proposal.status = ProposalStatus.SENT
        proposal.sent_at = utcnow()
        timeline.append_event(
            self.db,
            org_id=self.ctx.org_id,
            entity_type=EntityType.PROPOSAL,
            entity_id=proposal.id,
            event_type="PROPOSAL_SENT",
            payload={"opportunity_id": proposal.opportunity_id},
            actor=self.ctx.email,
        )
        self.db.commit()
        self.db.refresh(proposal)
        return proposal

    # ---- Meetings ----
    def schedule_meeting(
        self, opp_id: int, *, title: str, scheduled_at: datetime
    ) -> Meeting:
        opp = self.repo.get(opp_id)
        if opp is None:
            raise LookupError("Opportunity not found")
        meeting = Meeting(
            org_id=self.ctx.org_id,
            opportunity_id=opp.id,
            title=title,
            scheduled_at=scheduled_at,
            status=MeetingStatus.SCHEDULED,
        )
        self.db.add(meeting)
        self.db.flush()
        timeline.append_event(
            self.db,
            org_id=self.ctx.org_id,
            entity_type=EntityType.MEETING,
            entity_id=meeting.id,
            event_type="MEETING_SCHEDULED",
            payload={"scheduled_at": scheduled_at.isoformat()},
            actor=self.ctx.email,
        )
        self.db.commit()
        self.db.refresh(meeting)
        return meeting

    def complete_meeting(self, meeting_id: int) -> Meeting:
        meeting = self.db.get(Meeting, meeting_id)
        if meeting is None or meeting.org_id != self.ctx.org_id:
            raise LookupError("Meeting not found")
        meeting.status = MeetingStatus.COMPLETED
        timeline.append_event(
            self.db,
            org_id=self.ctx.org_id,
            entity_type=EntityType.MEETING,
            entity_id=meeting.id,
            event_type="MEETING_COMPLETED",
            actor=self.ctx.email,
        )
        self.db.commit()
        self.db.refresh(meeting)
        return meeting
