"""Map a lead decision to its descriptive next-action result string.

Side effects (email/webhook) are NOT performed here anymore — they are enqueued
into the outbox within the qualification task's transaction for exactly-once
delivery. This function only describes the action taken, for `lead.action_result`.
"""

from __future__ import annotations

from app.core.enums import LeadDecision


def describe_action(decision: LeadDecision | str) -> str:
    value = decision.value if isinstance(decision, LeadDecision) else decision

    if value == LeadDecision.HOT_LEAD.value:
        return "Hot lead alert queued"
    if value == LeadDecision.WARM_LEAD.value:
        return "Follow-up scheduled"
    if value == LeadDecision.COLD_LEAD.value:
        return "Added to nurture workflow"
    return "No action taken"
