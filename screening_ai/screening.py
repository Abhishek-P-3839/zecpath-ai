"""Screening AI (placeholder).

Checks that the candidate answered all the basic screening questions.
Speech-to-text and AI scoring will be added later.
"""
from utils.logger import get_logger

log = get_logger(__name__)

SCREENING_QUESTIONS = [
    "self_introduction",
    "education",
    "total_experience",
    "relevant_skills",
    "current_location",
    "notice_period",
    "expected_salary",
]


def build_screening_report(answers):
    """answers is a dict like {"education": "B.Tech"}. Returns a simple report."""
    missing = [q for q in SCREENING_QUESTIONS if not answers.get(q)]
    report = {
        "answered": len(SCREENING_QUESTIONS) - len(missing),
        "total": len(SCREENING_QUESTIONS),
        "missing": missing,
    }
    log.info("Screening report: %d/%d answered", report["answered"], report["total"])
    return report
