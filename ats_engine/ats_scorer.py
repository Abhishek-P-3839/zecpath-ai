"""ATS score: how well a resume matches the job requirements."""
from utils.logger import get_logger

log = get_logger(__name__)


def calculate_ats_score(parsed_resume, required_skills, min_experience=0):
    """Return a score from 0 to 100 based on matching skills.

    If the candidate has less than min_experience years, the score becomes 0.
    """
    if not required_skills:
        return 0.0
    if parsed_resume["experience_years"] < min_experience:
        log.info("Candidate rejected: not enough experience")
        return 0.0

    required = [s.lower() for s in required_skills]
    matched = [s for s in required if s in parsed_resume["skills"]]
    score = round(len(matched) / len(required) * 100, 2)
    log.info("ATS score = %s (matched %d of %d skills)", score, len(matched), len(required))
    return score
