from app.services.notification_service import notify_hot_lead


def execute_action(
    decision: str,
    lead
):
    if decision == "hot_lead":
        return notify_hot_lead(lead)

    if decision == "warm_lead":
        return "Follow-up scheduled"

    if decision == "cold_lead":
        return "Added to nurture workflow"

    return "No action taken"