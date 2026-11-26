"""Day 10: Experience relevance scoring.

Question answered: "How much of this candidate's experience is useful for THIS job?"

Inputs
    experience  the structured object from parsers.experience_parser.parse_experience()
    job         the flat AI profile from parsers.jd_parser.build_ai_profile()  (Day 6)

How one job (a resume entry) is scored against the job description, 0.0 - 1.0:

    relevance = 0.5 * title_similarity   (is the ROLE similar?  see role_similarity())
              + 0.5 * skill_score        (did they use the skills the job asks for?)

How the whole career is scored, 0 - 100:

    50%  years_fit         relevant years (recent work counts more) compared with the years required
    30%  best_relevance    the single most relevant job
    20%  recent_relevance  the most recent job (is the candidate still working in this area?)

Every number is returned with the reasons, so a recruiter can see WHY a score is what it is.
"""
import re
from datetime import date

from parsers.experience_parser import month_index
from parsers.jd_parser import normalize_role
from parsers.skill_taxonomy import SKILLS as SKILL_DICTIONARY
from utils.logger import get_logger

log = get_logger(__name__)

# ----------------------------------------------------------------------- tunable settings
RECENCY_HALF_LIFE_YEARS = 5      # work that ended 5 years ago counts half as much
TITLE_WEIGHT = 0.5
SKILL_WEIGHT = 0.5
MUST_WEIGHT = 0.75               # inside skill_score: must-have skills vs good-to-have skills
GOOD_WEIGHT = 0.25
YEARS_WEIGHT, BEST_WEIGHT, RECENT_WEIGHT = 0.5, 0.3, 0.2
MIN_REQUIRED_YEARS = 0.5         # a job that asks for "0 years" still wants about 6 months of real work

# ----------------------------------------------------------------------- role knowledge
# Which "family" does a role belong to?  Same family -> the roles are related.
ROLE_FAMILY = {
    "full stack developer": "software", "frontend developer": "software", "backend developer": "software",
    "software engineer": "software", "mobile developer": "software",
    "data analyst": "data", "data scientist": "data", "machine learning engineer": "data",
    "devops engineer": "infra", "qa engineer": "quality", "ui/ux designer": "design",
    "hr executive": "hr", "sales executive": "sales", "customer support executive": "support",
    "digital marketing executive": "marketing", "accountant": "finance",
}
# Words in a free-text title that reveal the family when the title is not in the role list
# ("Python Developer", "Project Analyst").
FAMILY_KEYWORDS = {
    "software": ["software", "python", "java", "javascript", "react", "node", "web", "frontend", "backend",
                 "full stack", "fullstack", "mobile", "android", "ios", "application", "programmer", "sde",
                 "developer", "api"],
    "data": ["data", "analytics", "bi", "machine learning", "ml", "ai", "statistician", "mis"],
    "infra": ["devops", "cloud", "sre", "infrastructure", "platform", "sysadmin"],
    "quality": ["qa", "quality", "tester", "testing", "sdet"],
    "design": ["designer", "ux", "ui", "graphic", "creative"],
    "hr": ["hr", "recruiter", "recruitment", "talent", "human resources"],
    "sales": ["sales", "business development", "bde", "account executive"],
    "support": ["support", "customer service", "customer care", "helpdesk", "help desk"],
    "marketing": ["marketing", "seo", "content", "social media", "growth", "campaign"],
    "finance": ["accountant", "accounts", "finance", "audit", "tax", "bookkeeping"],
    "operations": ["operations", "project", "program", "logistics", "supply chain", "coordinator", "admin"],
}
# Roles that are close even though the names differ: similarity from 0 to 1.
CLOSE_ROLES = {
    frozenset({"full stack developer", "frontend developer"}): 0.80,
    frozenset({"full stack developer", "backend developer"}): 0.80,
    frozenset({"full stack developer", "software engineer"}): 0.85,
    frozenset({"software engineer", "backend developer"}): 0.85,
    frozenset({"software engineer", "frontend developer"}): 0.80,
    frozenset({"frontend developer", "backend developer"}): 0.60,
    frozenset({"software engineer", "mobile developer"}): 0.70,
    frozenset({"data analyst", "data scientist"}): 0.70,
    frozenset({"data scientist", "machine learning engineer"}): 0.80,
    frozenset({"data analyst", "machine learning engineer"}): 0.50,
    frozenset({"software engineer", "machine learning engineer"}): 0.55,
    frozenset({"software engineer", "devops engineer"}): 0.55,
    frozenset({"software engineer", "qa engineer"}): 0.50,
    frozenset({"hr executive", "sales executive"}): 0.15,
    frozenset({"sales executive", "digital marketing executive"}): 0.45,
    frozenset({"customer support executive", "sales executive"}): 0.40,
}
SAME_FAMILY_SCORE = 0.60

# Level words -> number. Used to see whether the seniority of a past role matches the job.
LEVELS = {"intern": 0, "fresher": 0, "junior": 1, "mid": 2, "senior": 3, "lead": 4, "manager": 5}
_LEVEL_PATTERNS = [
    ("intern", re.compile(r"\b(intern|internship|trainee|apprentice)\b", re.I)),
    ("manager", re.compile(r"\b(manager|head of|director|vp|vice president)\b", re.I)),
    ("lead", re.compile(r"\b(lead|principal|architect|staff)\b", re.I)),
    ("senior", re.compile(r"\b(senior|sr\.?|iii)\b", re.I)),
    ("junior", re.compile(r"\b(junior|jr\.?|associate|assistant|entry)\b", re.I)),
]

# For comparing titles word by word: generic job words matter less than the domain words.
GENERIC_WORDS = {"engineer", "developer", "manager", "analyst", "executive", "specialist", "associate",
                 "coordinator", "officer", "consultant", "administrator", "assistant", "lead", "programmer"}
SENIORITY_WORDS = {"senior", "sr", "junior", "jr", "intern", "trainee", "principal", "staff", "head",
                   "chief", "associate", "i", "ii", "iii", "iv", "of", "the", "and", "at"}
WORD_SYNONYMS = {"developer": "engineer", "programmer": "engineer", "sde": "software engineer",
                 "frontend": "front end", "backend": "back end", "fullstack": "full stack",
                 "recruiter": "recruitment", "recruiting": "recruitment", "marketer": "marketing",
                 "accounts": "accounting", "accountant": "accounting", "tester": "testing",
                 "js": "javascript", "reactjs": "react", "nodejs": "node"}


def hard_skills(names):
    """Drop soft skills ('communication'): job bullets rarely use the word, so judging them is unfair."""
    return [n for n in names if SKILL_DICTIONARY.get(n, ("other",))[0] != "soft_skill"]


# ----------------------------------------------------------------------- role-to-role similarity

def _title_words(title):
    text = re.sub(r"[^a-z0-9+#/ ]", " ", (title or "").lower())
    words = []
    for word in text.split():
        word = WORD_SYNONYMS.get(word, word)
        words.extend(word.split())
    return [w for w in words if w not in SENIORITY_WORDS]


def _weighted_overlap(a_words, b_words):
    """Weighted Jaccard: shared domain words count 1.0, shared generic words (engineer...) only 0.4."""
    weight = lambda w: 0.4 if w in GENERIC_WORDS else 1.0
    a, b = set(a_words), set(b_words)
    union = sum(weight(w) for w in a | b)
    return sum(weight(w) for w in a & b) / union if union else 0.0


def role_family(title):
    """'Python Developer' -> 'software'.  Returns None when nothing matches."""
    canonical = normalize_role(title or "")
    if canonical in ROLE_FAMILY:
        return ROLE_FAMILY[canonical]
    lowered = " " + re.sub(r"[^a-z0-9+#/ ]", " ", (title or "").lower()) + " "
    best, best_hits = None, 0
    for family, words in FAMILY_KEYWORDS.items():
        hits = sum(1 for w in words if f" {w} " in lowered)
        if hits > best_hits:
            best, best_hits = family, hits
    return best


def role_similarity(title_a, title_b):
    """How similar are two job titles? 0.0 (unrelated) .. 1.0 (same role).

    1. both titles map to the same canonical role           -> 1.0   ('MERN Developer' = 'Full Stack Engineer')
    2. both map to roles listed as close in CLOSE_ROLES     -> that value
    3. same role family                                     -> 0.6
    4. otherwise: weighted word overlap of the two titles   -> 0.0 .. ~0.7
    The best of these wins.
    """
    a, b = (title_a or "").strip(), (title_b or "").strip()
    if not a or not b:
        return 0.0
    canon_a, canon_b = normalize_role(a), normalize_role(b)
    scores = [_weighted_overlap(_title_words(a), _title_words(b))]
    if canon_a and canon_b:
        if canon_a == canon_b:
            return 1.0
        scores.append(CLOSE_ROLES.get(frozenset({canon_a, canon_b}), 0.0))
    fam_a, fam_b = role_family(a), role_family(b)
    if fam_a and fam_a == fam_b:
        scores.append(SAME_FAMILY_SCORE)
    return round(min(max(scores), 1.0), 2)


def detect_level(title):
    """'Senior Project Analyst' -> 'senior'. No level word -> 'mid'."""
    for name, pattern in _LEVEL_PATTERNS:
        if pattern.search(title or ""):
            return name
    return "mid"


def seniority_fit(candidate_level, job_level):
    """1.0 same level, 0.5 one step apart, ... never below 0. Level names come from jd_parser (Day 6)."""
    c = LEVELS.get(candidate_level)
    j = LEVELS.get(job_level or "mid")
    if c is None or j is None:
        return None
    return round(max(0.0, 1.0 - 0.5 * abs(c - j)), 2)


def similarity_matrix(titles):
    """Table of role_similarity for every pair of titles: {a: {b: score}}. Handy for studying and debugging."""
    return {a: {b: role_similarity(a, b) for b in titles} for a in titles}


# ----------------------------------------------------------------------- scoring one entry

def skill_score(skills_used, must_have, good_to_have):
    """(score 0..1, matched_must, matched_good).  Uses the same canonical names as Day 6 / Day 9."""
    used = set(skills_used)
    matched_must = [s for s in must_have if s in used]
    matched_good = [s for s in good_to_have if s in used]
    must_part = len(matched_must) / len(must_have) if must_have else None
    good_part = len(matched_good) / len(good_to_have) if good_to_have else None
    if must_part is not None and good_part is not None:
        score = MUST_WEIGHT * must_part + GOOD_WEIGHT * good_part
    else:
        score = must_part if must_part is not None else (good_part or 0.0)
    return round(score, 2), matched_must, matched_good


def recency_weight(end_index, today):
    """1.0 for work that is current, then halves every RECENCY_HALF_LIFE_YEARS."""
    years_ago = max(0, month_index(today.year, today.month) - end_index) / 12
    return round(0.5 ** (years_ago / RECENCY_HALF_LIFE_YEARS), 3)


def score_entry(entry, job, today):
    """Relevance of ONE past job to the target job. Returns a dict with all the parts."""
    must = hard_skills(job.get("must_have_skills", []))
    good = hard_skills(job.get("good_to_have_skills", []))
    title_sim = role_similarity(entry["designation"], job.get("title", "")) if entry["designation"] != "Unknown" else 0.0
    normalized_job = job.get("normalized_title")
    if normalized_job:                                   # the canonical title is usually the cleaner target
        title_sim = max(title_sim, role_similarity(entry["designation"], normalized_job))
    s_score, matched_must, matched_good = skill_score(entry["skills_used"], must, good)

    if must or good:
        relevance = TITLE_WEIGHT * title_sim + SKILL_WEIGHT * s_score
    else:
        relevance = title_sim                           # the job lists no skills: judge by role only

    level = detect_level(entry["designation"])
    reasons = []
    if title_sim >= 0.8:
        reasons.append("same or very close role")
    elif title_sim >= 0.5:
        reasons.append("related role")
    else:
        reasons.append("different role")
    if matched_must:
        reasons.append(f"used {len(matched_must)}/{len(must)} must-have skills")
    return {
        "company": entry["company"], "designation": entry["designation"],
        "start_date": entry["start_date"], "end_date": entry["end_date"],
        "duration_months": entry["duration_months"],
        "title_similarity": title_sim, "skill_score": s_score,
        "matched_must_have": matched_must, "matched_good_to_have": matched_good,
        "relevance": round(relevance, 2),
        "recency_weight": recency_weight(entry["_end_index"], today) if entry["_end_index"] is not None else 0.0,
        "level": level, "seniority_fit": seniority_fit(level, job.get("level")),
        "reasons": reasons,
    }


# ----------------------------------------------------------------------- scoring the whole career

def _label(score):
    if score >= 75: return "strong"
    if score >= 50: return "good"
    if score >= 25: return "partial"
    return "weak"


def score_experience(experience, job, today=None):
    """Main entry point: (structured experience, job profile) -> relevance report.

    Months are counted ONE time even if two jobs overlap: for every calendar month we keep the most
    relevant job that covers it. Then each month is weighted by how recent it is.
    """
    today = today or date.today()
    entries = [e for e in experience["entries"] if e["_start_index"] is not None]
    scored = [(e, score_entry(e, job, today)) for e in entries]

    month_relevance = {}
    for e, s in scored:
        for m in range(e["_start_index"], e["_end_index"] + 1):
            month_relevance[m] = max(month_relevance.get(m, 0.0), s["relevance"])
    today_i = month_index(today.year, today.month)
    relevant_months = sum(month_relevance.values())
    effective_months = sum(r * 0.5 ** (max(0, today_i - m) / 12 / RECENCY_HALF_LIFE_YEARS)
                           for m, r in month_relevance.items())
    relevant_years = round(relevant_months / 12, 1)
    effective_years = round(effective_months / 12, 1)

    min_years = job.get("min_years") or 0
    required = max(min_years, MIN_REQUIRED_YEARS)
    years_fit = min(1.0, effective_years / required)
    best = max((s for _, s in scored), key=lambda s: s["relevance"], default=None)
    latest = max(scored, key=lambda p: p[0]["_end_index"], default=(None, None))[1]
    best_rel = best["relevance"] if best else 0.0
    recent_rel = latest["relevance"] if latest else 0.0
    score = round(100 * (YEARS_WEIGHT * years_fit + BEST_WEIGHT * best_rel + RECENT_WEIGHT * recent_rel))

    # skills the job needs, seen anywhere in the experience
    all_used = {s for e in entries for s in e["skills_used"]}
    must = hard_skills(job.get("must_have_skills", []))
    covered = [s for s in must if s in all_used]
    missing = [s for s in must if s not in all_used]

    notes = []
    if not entries:
        notes.append("No dated work experience found (fresher, or experience could not be parsed).")
    else:
        notes.append(f"{experience['total_experience_years']} total years, about {relevant_years} relevant "
                     f"({effective_years} after giving recent work more weight); job asks for {min_years}+.")
    max_years = job.get("max_years")
    if max_years and experience["total_experience_years"] > max_years + 3:
        notes.append(f"Has more experience than the {max_years}-year upper range: may be over-qualified.")
    if latest and latest["relevance"] < 0.3 and best_rel >= 0.5:
        notes.append("Most relevant work is older; the latest role is in a different area.")
    if missing:
        notes.append("Must-have skills not seen in experience: " + ", ".join(missing) + ".")
    if best and best["seniority_fit"] is not None and best["seniority_fit"] < 0.5:
        notes.append(f"Seniority differs from the job (candidate: {best['level']}, job: {job.get('level')}).")

    result = {
        "score": score, "label": _label(score),
        "total_years": experience["total_experience_years"],
        "relevant_years": relevant_years, "effective_years": effective_years,
        "required_years": min_years, "years_fit": round(years_fit, 2),
        "best_match": best, "most_recent": latest,
        "must_have_covered": covered, "must_have_missing": missing,
        "entries": [s for _, s in sorted(scored, key=lambda p: -p[1]["relevance"])],
        "notes": notes,
    }
    log.info("Experience relevance for '%s': %d (%s)", job.get("title"), score, result["label"])
    return result
