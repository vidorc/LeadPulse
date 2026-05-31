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
