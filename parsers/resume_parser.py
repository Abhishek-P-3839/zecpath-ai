"""Basic resume parser (text only for now).

PDF and DOCX reading will be added later using pypdf and python-docx.
"""
import re

from utils.logger import get_logger

log = get_logger(__name__)

KNOWN_SKILLS = ["python", "java", "react", "node.js", "mongodb", "sql", "git", "docker", "aws"]


def parse_resume_text(text):
    """Take resume text and return a dict with email, skills and years of experience."""
    lowered = text.lower()

    email_match = re.search(r"[\w.+-]+@[\w-]+\.[\w.]+", text)
    skills = [s for s in KNOWN_SKILLS if s in lowered]
    years_match = re.search(r"(\d+)\s*years?", lowered)

    result = {
        "email": email_match.group(0) if email_match else None,
        "skills": skills,
        "experience_years": int(years_match.group(1)) if years_match else 0,
    }
    log.info("Parsed resume: %d skills found", len(skills))
    return result
