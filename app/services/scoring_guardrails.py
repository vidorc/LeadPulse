def normalize_score(
    score: int,
    urgency: str,
    budget: str
):
    normalized = score

    budget_lower = budget.lower()

    if "cr" in budget_lower:
        normalized = max(normalized, 85)

    if urgency == "high":
        normalized = max(normalized, 90)

    return normalized
