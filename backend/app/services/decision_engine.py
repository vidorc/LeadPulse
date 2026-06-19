"""Pure decision function: map (score, urgency) → decision + next action.

Deterministic and side-effect-free — trivially unit-testable. Returns enum
values so the caller can assign them directly to typed columns.
"""

from __future__ import annotations

from app.core.enums import LeadDecision, Urgency


def decide_lead_action(score: int, urgency: str | Urgency | None) -> dict:
    urgency_value = urgency.value if isinstance(urgency, Urgency) else (urgency or "")
    is_high = str(urgency_value).lower() == "high"

    if score >= 85 and is_high:
        return {"decision": LeadDecision.HOT_LEAD, "next_action": "assign_immediately"}
    if score >= 60:
        return {"decision": LeadDecision.WARM_LEAD, "next_action": "follow_up"}
    return {"decision": LeadDecision.COLD_LEAD, "next_action": "nurture"}
