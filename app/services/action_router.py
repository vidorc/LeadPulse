"""Route a lead decision to its side effect.

Enum-aware. In Phase 5 the side effects move behind the outbox relay for
exactly-once delivery; today it calls the notification adapter directly.
"""

from __future__ import annotations

from app.core.enums import LeadDecision
from app.services.notification_service import notify_hot_lead


def execute_action(decision: LeadDecision | str, lead) -> str:
    value = decision.value if isinstance(decision, LeadDecision) else decision

    if value == LeadDecision.HOT_LEAD.value:
        return notify_hot_lead(lead)
    if value == LeadDecision.WARM_LEAD.value:
        return "Follow-up scheduled"
    if value == LeadDecision.COLD_LEAD.value:
        return "Added to nurture workflow"
    return "No action taken"
