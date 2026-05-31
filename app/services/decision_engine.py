def decide_lead_action(
    score: int,
    urgency: str
):
    if score >= 85 and urgency == "high":
        return {
            "decision": "hot_lead",
            "next_action": "assign_immediately"
        }

    if score >= 60:
        return {
            "decision": "warm_lead",
            "next_action": "follow_up"
        }

    return {
        "decision": "cold_lead",
        "next_action": "nurture"
    }