"""Interview AI (placeholder).

Right now it only returns fixed questions by experience level.
Real question generation with an AI model will be added later.
"""
from utils.logger import get_logger

log = get_logger(__name__)

HR_QUESTIONS = [
    "Please introduce yourself.",
    "What are your strengths and weaknesses?",
    "Why do you want this job?",
]


def get_hr_questions():
    return list(HR_QUESTIONS)


def get_technical_level(experience_years):
    """Decide the difficulty level from years of experience."""
    if experience_years < 2:
        return "basic"
    if experience_years < 5:
        return "intermediate"
    return "advanced"
