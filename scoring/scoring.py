"""Combine the scores of all rounds into one final score and a decision."""
from utils.logger import get_logger

log = get_logger(__name__)

# weights add up to 1.0 (can be changed per job role later)
DEFAULT_WEIGHTS = {"ats": 0.2, "hr": 0.2, "technical": 0.4, "machine_test": 0.2}


def combine_scores(scores, weights=None):
    """scores is a dict like {"ats": 80, "hr": 70, "technical": 60, "machine_test": 75}."""
    weights = weights or DEFAULT_WEIGHTS
    total = sum(scores[name] * weight for name, weight in weights.items())
    return round(total, 2)


def get_decision(final_score, select_above=70, reject_below=40):
    """Return selected / hold / rejected."""
    if final_score >= select_above:
        decision = "selected"
    elif final_score < reject_below:
        decision = "rejected"
    else:
        decision = "hold"
    log.info("Final score %s -> %s", final_score, decision)
    return decision
