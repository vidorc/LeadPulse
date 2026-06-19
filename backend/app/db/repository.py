"""Tenant-scoped repository base.

Defense-in-depth layer 3 (architecture review §7.1): repositories cannot build
a query without applying the tenant filter. Every read goes through
``scoped_query`` / ``get`` which inject ``org_id == ctx.org_id`` and exclude
soft-deleted rows by default. This makes the "every user sees all leads" IDOR
class structurally hard to reintroduce — a query that forgets the scope simply
isn't expressible through this base.
"""

from __future__ import annotations

from typing import Generic, TypeVar

from sqlalchemy import select
from sqlalchemy.orm import Session
from sqlalchemy.sql import Select

from app.core.tenant import TenantContext
from app.db.base_class import Base

ModelT = TypeVar("ModelT", bound=Base)


class TenantRepository(Generic[ModelT]):
    """Base repository that scopes all access to a single tenant.

    ``model`` must have an ``org_id`` column (TenantMixin). Soft-deleted rows
    (``deleted_at IS NOT NULL``) are excluded unless ``include_deleted=True``.
    """

    model: type[ModelT]

    def __init__(self, db: Session, ctx: TenantContext):
        self.db = db
        self.ctx = ctx

    def scoped_query(self, *, include_deleted: bool = False) -> Select:
        """A SELECT pre-filtered to this tenant. The only sanctioned entry
        point for reads."""
        stmt = select(self.model).where(self.model.org_id == self.ctx.org_id)
        if not include_deleted and hasattr(self.model, "deleted_at"):
            stmt = stmt.where(self.model.deleted_at.is_(None))
        return stmt

    def get(self, entity_id: int, *, include_deleted: bool = False) -> ModelT | None:
        """Fetch one row by id, scoped to the tenant. Returns None if it does
        not exist *or* belongs to another tenant (no cross-tenant disclosure)."""
        stmt = self.scoped_query(include_deleted=include_deleted).where(
            self.model.id == entity_id
        )
        return self.db.execute(stmt).scalar_one_or_none()

    def list(self, *, include_deleted: bool = False) -> list[ModelT]:
        stmt = self.scoped_query(include_deleted=include_deleted)
        return list(self.db.execute(stmt).scalars().all())

    def add(self, entity: ModelT) -> ModelT:
        """Persist a new row, forcing its org_id to the tenant scope so a
        caller cannot create rows in another tenant."""
        entity.org_id = self.ctx.org_id
        self.db.add(entity)
        return entity

    def soft_delete(self, entity: ModelT) -> None:
        from app.db.mixins import utcnow

        if hasattr(entity, "deleted_at"):
            entity.deleted_at = utcnow()
        else:  # pragma: no cover - misuse guard
            raise TypeError(f"{self.model.__name__} does not support soft delete")
