def requires_review(
    score: int,
    intent: str
):
    if score < 50:
        return True

    if intent == "inquiry":
        return True

    return False
