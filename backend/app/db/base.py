"""Aggregates all ORM models onto a single ``Base.metadata``.

Importing this module guarantees every table is registered, which is what
Alembic autogenerate and any metadata-driven tooling need. It is the single
import point for "all models" — do not scatter model imports elsewhere.

Import order matters for relationship resolution: parents (Organization, User,
Team) before children that FK to them.
"""

from app.db.base_class import Base  # noqa: F401  (re-exported)

# Identity & access (tenancy roots first).
from app.models.organization import Organization  # noqa: F401
from app.models.user import User  # noqa: F401
from app.models.team import Team  # noqa: F401
from app.models.membership import Membership  # noqa: F401
from app.models.refresh_token import RefreshToken  # noqa: F401

# Domain.
from app.models.lead import Lead  # noqa: F401
from app.models.opportunity import Opportunity  # noqa: F401
from app.models.proposal import Proposal  # noqa: F401
from app.models.meeting import Meeting  # noqa: F401
from app.models.sequence import Sequence, SequenceStep, Enrollment  # noqa: F401
from app.models.leak import SLAPolicy, LeakAlert  # noqa: F401

# Workflow engine substrate (timeline, scheduling, outbox).
from app.models.event import Event  # noqa: F401
from app.models.scheduled_job import ScheduledJob  # noqa: F401
from app.models.outbox import OutboxMessage  # noqa: F401

# Governance.
from app.models.audit_log import AuditLog  # noqa: F401

__all__ = [
    "Base",
    "Organization",
    "User",
    "Team",
    "Membership",
    "RefreshToken",
    "Lead",
    "Opportunity",
    "Proposal",
    "Meeting",
    "Sequence",
    "SequenceStep",
    "Enrollment",
    "SLAPolicy",
    "LeakAlert",
    "Event",
    "ScheduledJob",
    "OutboxMessage",
    "AuditLog",
]
