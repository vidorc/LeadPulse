"""Aggregates all ORM models onto a single ``Base.metadata``.

Importing this module guarantees every table is registered, which is what
Alembic autogenerate and any metadata-driven tooling need. It is the single
import point for "all models" — do not scatter model imports elsewhere.
"""

from app.db.base_class import Base  # noqa: F401  (re-exported)

# Import every model module for its side effect of registering on Base.metadata.
from app.models.user import User  # noqa: F401
from app.models.lead import Lead  # noqa: F401
from app.models.lead_event import LeadEvent  # noqa: F401

__all__ = ["Base", "User", "Lead", "LeadEvent"]
