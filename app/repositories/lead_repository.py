"""Repositories for the Lead domain — all tenant-scoped via TenantRepository."""

from __future__ import annotations

from sqlalchemy import func, select

from app.core.enums import LeadDecision, LeadStatus
from app.db.repository import TenantRepository
from app.models.lead import Lead


class LeadRepository(TenantRepository[Lead]):
    model = Lead

    def review_queue(self) -> list[Lead]:
        stmt = self.scoped_query().where(Lead.requires_human_review.is_(True))
        return list(self.db.execute(stmt).scalars().all())

    def summary_counts(self) -> dict[str, int]:
        """Aggregate counts for the dashboard, scoped to the tenant.

        Single grouped query rather than N full scans (the audit flagged the
        old dashboard as repeated full scans)."""
        base = select(func.count(Lead.id)).where(
            Lead.org_id == self.ctx.org_id, Lead.deleted_at.is_(None)
        )
        total = self.db.execute(base).scalar_one()
        hot = self.db.execute(
            base.where(Lead.decision == LeadDecision.HOT_LEAD)
        ).scalar_one()
        review = self.db.execute(
            base.where(Lead.requires_human_review.is_(True))
        ).scalar_one()
        converted = self.db.execute(
            base.where(Lead.status == LeadStatus.CONVERTED)
        ).scalar_one()
        return {
            "total_leads": total,
            "hot_leads": hot,
            "manual_reviews": review,
            "converted": converted,
        }
