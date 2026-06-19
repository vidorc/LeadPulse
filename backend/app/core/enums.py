"""Shared domain enumerations.

Replaces the magic strings the audit flagged (`"yes"/"no"`, free-text
`role`/`status`/`decision`/`urgency`/`intent`) with typed, constrained values
so typos fail loudly and dashboard filters can't silently miss rows.

Stored in the DB as their string `value` via SQLAlchemy `Enum(..., native_enum=False)`
so they are portable and easy to extend without a Postgres type migration.
"""

from __future__ import annotations

import enum


class Role(str, enum.Enum):
    """Org-scoped role, ordered by privilege (OWNER highest)."""

    OWNER = "owner"
    ADMIN = "admin"
    MANAGER = "manager"
    AGENT = "agent"

    @property
    def rank(self) -> int:
        order = {
            Role.OWNER: 4,
            Role.ADMIN: 3,
            Role.MANAGER: 2,
            Role.AGENT: 1,
        }
        return order[self]

    def at_least(self, other: "Role") -> bool:
        """True if this role is at least as privileged as ``other``."""
        return self.rank >= other.rank


class LeadStatus(str, enum.Enum):
    NEW = "new"
    QUALIFYING = "qualifying"
    QUALIFIED = "qualified"
    MANUAL_REVIEW = "manual_review"
    ASSIGNED = "assigned"
    CONVERTED = "converted"
    LOST = "lost"


class LeadDecision(str, enum.Enum):
    HOT_LEAD = "hot_lead"
    WARM_LEAD = "warm_lead"
    COLD_LEAD = "cold_lead"
    MANUAL_REVIEW = "manual_review"


class Urgency(str, enum.Enum):
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


class Intent(str, enum.Enum):
    PURCHASE = "purchase"
    INQUIRY = "inquiry"
    SUPPORT = "support"
    SPAM = "spam"
    UNKNOWN = "unknown"


class EntityType(str, enum.Enum):
    """What kind of domain object a timeline event / scheduled job concerns."""

    LEAD = "lead"
    OPPORTUNITY = "opportunity"
    PROPOSAL = "proposal"
    MEETING = "meeting"
    ENROLLMENT = "enrollment"


class OpportunityStage(str, enum.Enum):
    """Sales pipeline stages, ordered. WON/LOST are terminal."""

    NEW = "new"
    CONTACTED = "contacted"
    QUALIFIED = "qualified"
    PROPOSAL_SENT = "proposal_sent"
    NEGOTIATION = "negotiation"
    WON = "won"
    LOST = "lost"

    @property
    def is_terminal(self) -> bool:
        return self in (OpportunityStage.WON, OpportunityStage.LOST)


class ProposalStatus(str, enum.Enum):
    DRAFT = "draft"
    SENT = "sent"
    ACCEPTED = "accepted"
    REJECTED = "rejected"
    EXPIRED = "expired"


class MeetingStatus(str, enum.Enum):
    SCHEDULED = "scheduled"
    COMPLETED = "completed"
    NO_SHOW = "no_show"
    CANCELLED = "cancelled"


class EnrollmentStatus(str, enum.Enum):
    """State of a lead's enrollment in a follow-up sequence."""

    ACTIVE = "active"
    COMPLETED = "completed"
    CANCELLED = "cancelled"  # e.g. rep engaged the lead, so stop touching it


class LeakType(str, enum.Enum):
    """The temporal-SLA breach categories (architecture review §8.4)."""

    LEAD_IGNORED = "lead_ignored"        # no contact within N hours of creation
    OPP_STALLED = "opp_stalled"          # no stage change within N days
    MEETING_MISSED = "meeting_missed"    # scheduled time passed, not completed
    PROPOSAL_COLD = "proposal_cold"      # no follow-up within N days of sending


class LeakSeverity(str, enum.Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class LeakAlertStatus(str, enum.Enum):
    OPEN = "open"
    RESOLVED = "resolved"
    DISMISSED = "dismissed"


class ScheduledJobStatus(str, enum.Enum):
    PENDING = "pending"
    RUNNING = "running"
    DONE = "done"
    CANCELLED = "cancelled"
    FAILED = "failed"


class OutboxStatus(str, enum.Enum):
    PENDING = "pending"
    SENT = "sent"
    FAILED = "failed"
    DEAD = "dead"  # exceeded max attempts


class OutboxChannel(str, enum.Enum):
    EMAIL = "email"
    WEBHOOK = "webhook"
    IN_APP = "in_app"
