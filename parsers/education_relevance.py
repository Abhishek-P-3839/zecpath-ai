"""Day 11: Education relevance scoring.

Question answered: "How well do this candidate's education and certifications fit THIS job?"

Inputs
    source   the candidate side: the academic profile (parsers.academic_profile), the parse result of
             parsers.education_parser.parse_from_file(), or just a list of education entries
    job      the flat AI profile from parsers.jd_parser.build_ai_profile()  (Day 6)

This is the ONE place where "education relevance" is calculated. The Day 13 ATS engine calls
score_education() from here; it has no copy of the logic any more.

How the education score is built, 0 - 100:

    score = 100 * (level_weight * level_fit + field_weight * field_fit) / (sum of the weights used)

    level_fit  candidate's highest degree vs the job's minimum level
                   equal or higher ............ 1.0
                   degree still in progress ... 0.8
                   one level below ............ 0.5
                   two or more below .......... 0.2
    field_fit  the candidate's field of study vs the job's preferred fields (best entry wins)
                   same field ................. 1.0
                   same field category ........ 0.7    (Data Science vs Computer Science)
                   related category ........... 0.5    (Electronics vs Computer Science)
                   unrelated .................. 0.3
               a degree that is still in progress counts only 80% of that credit.

    The weights (60% / 40%) and all the credits above come from ats_weights.json ("education").

How the certification score is built, 0 - 100 (see score_certifications):
    every certification is rated high / medium / low for the job, turned into points, and the best one
    counts fully while every other one adds a little (diminishing returns).

How both are combined (see score_education_with_certifications):

    combined = min(100, education_score + 10 * certification_score / 100)

    So certifications can add at most 10 points, and only half of that when the required degree level
    is not met. They can NEVER replace a missing required degree.

Every number is returned with `reasons`, so a recruiter can see WHY a score is what it is.
"""

import copy
import re

from parsers.education_parser import LEVEL_ORDER, field_category, normalize_field, tag_certification
from parsers.experience_relevance import hard_skills
from utils.logger import get_logger

log = get_logger(__name__)

# ----------------------------------------------------------------------- tunable settings
# These defaults are a copy of the "education" section of ats_engine/ats_weights.json. The engine always
# passes the real file, so the JSON wins; a unit test checks that the two never drift apart.
DEFAULT_CONFIG = {
    "level_weight": 0.6,
    "field_weight": 0.4,
    "in_progress_factor": 0.8,  # a degree that is not finished yet counts 80% in the field match
    "level_credit": {
        "met": 1.0,
        "in_progress_met": 0.8,
        "one_below": 0.5,
        "two_or_more_below": 0.2,
    },
    "field_credit": {"exact": 1.0, "same_category": 0.7, "related_category": 0.5, "different": 0.3},
}

# Used when a technical job names a degree level but no field: a sensible default, not a guess at random.
DEFAULT_TECH_FIELDS = ["Computer Science", "Information Technology"]
ANY_DEGREE_WORDS = {
    "any",
    "any degree",
    "any_degree",
    "degree",
    "graduate",
}  # all mean "a bachelor's, any field"

# Field categories (from education_parser.field_category) that are close to each other.
RELATED_CATEGORIES = [
    frozenset({"computer_it", "engineering"}),  # electronics / electrical -> software work
    frozenset({"computer_it", "science"}),  # maths / statistics -> data work
    frozenset({"engineering", "science"}),
    frozenset({"business", "arts_humanities"}),  # psychology / sociology -> HR and marketing work
]

# ----------------------------------------------------------------------- certification knowledge
# Which certification categories belong to which role (keys are the Day 6 normalized_title values).
ROLE_CERT_CATEGORIES = {
    "full stack developer": ["software_development", "database"],
    "frontend developer": ["software_development"],
    "backend developer": ["software_development", "database", "cloud"],
    "software engineer": ["software_development", "cloud"],
    "mobile developer": ["software_development"],
    "data analyst": ["data_ai", "database"],
    "data scientist": ["data_ai"],
    "machine learning engineer": ["data_ai", "cloud"],
    "devops engineer": ["devops", "cloud"],
    "qa engineer": ["software_development"],
    "hr executive": ["business"],
    "sales executive": ["business"],
    "digital marketing executive": ["business"],
    "accountant": ["business"],
}
# A certification name may say "Amazon Web Services" where the job skill says "aws".
SKILL_ALIASES = {
    "aws": ["amazon web services"],
    "gcp": ["google cloud"],
    "node.js": ["nodejs", "node js"],
    "power bi": ["powerbi"],
    "kubernetes": ["cka", "ckad"],
    "javascript": ["js"],
}

RELEVANCE_POINTS = {"high": 1.0, "medium": 0.6, "low": 0.15}
FOUNDATIONAL_FACTOR = 0.7  # "Cloud Practitioner" is worth less than "Solutions Architect"
COURSE_FACTOR = 0.7  # a course certificate is worth less than a proctored exam
EXPIRED_FACTOR = 0.5  # an expired certification still shows the learning, but is worth half
EXTRA_CERT_WEIGHT = 0.25  # the 2nd, 3rd ... best certifications add 25% of their points each
CERT_BONUS_MAX = 10  # certifications can add at most this many points to the education score
BONUS_FACTOR_BELOW_LEVEL = 0.5  # ... and only half of it when the required degree level is not met


# ----------------------------------------------------------------------- small helpers
def merged_config(config=None):
    """DEFAULT_CONFIG with any values from ats_weights.json laid on top (nested dicts are merged)."""
    result = copy.deepcopy(DEFAULT_CONFIG)
    for key, value in (config or {}).items():
        if isinstance(value, dict) and isinstance(result.get(key), dict):
            result[key].update(value)
        else:
            result[key] = value
    return result


def entries_of(source):
    """Education entries from a profile, a parse result or a plain list. Anything else -> []."""
    if isinstance(source, dict):
        source = source.get("education")
    return list(source) if isinstance(source, list) else []


def certs_of(source):
    """Certification list from a profile or a parse result. A plain list of entries has none."""
    certs = source.get("certifications") if isinstance(source, dict) else None
    return list(certs) if isinstance(certs, list) else []


def _index(entry):
    level = entry.get("level")
    return LEVEL_ORDER.index(level) if level in LEVEL_ORDER else None


def _best_levels(entries):
    """(best finished level index, best in-progress level index); None when there is none."""
    done = [_index(e) for e in entries if _index(e) is not None and not e.get("in_progress")]
    ongoing = [_index(e) for e in entries if _index(e) is not None and e.get("in_progress")]
    return (max(done) if done else None), (max(ongoing) if ongoing else None)


def required_level(job):
    """The job's minimum level as a LEVEL_ORDER name ('any degree' -> 'bachelor'), or None."""
    required = job.get("education_min_level")
    if isinstance(required, str) and required.strip().lower() in ANY_DEGREE_WORDS:
        return "bachelor"
    return required


def field_targets(job):
    """(fields to compare with, where they came from: 'job' / 'default' / 'none').

    'none' means the job accepts any field of study ("any degree"), so the field part is not scored.
    """
    preferred = [f for f in (job.get("preferred_fields") or []) if f]
    if preferred:
        return preferred, "job"
    if required_level(job) in LEVEL_ORDER and job.get("role_category") == "technical":
        return list(DEFAULT_TECH_FIELDS), "default"
    return [], "none"


def _part(status, score=None, reasons=None, details=None):
    return {
        "status": status,
        "score": score,
        "reasons": list(reasons or []),
        "details": details or {},
    }


# ----------------------------------------------------------------------- level fit
def level_fit(entries, required, cfg):
    """(credit 0..1, reason) for the candidate's degree level against the required level."""
    best_done, best_ongoing = _best_levels(entries)
    need, credit = LEVEL_ORDER.index(required), cfg["level_credit"]
    have = LEVEL_ORDER[best_done] if best_done is not None else "no recognised degree"
    if best_done is not None and best_done >= need:
        return credit["met"], f"Highest degree ({have}) meets the required level ({required})."
    if best_ongoing is not None and best_ongoing >= need:  # still studying: some credit, not full
        return (
            credit["in_progress_met"],
            f"A {LEVEL_ORDER[best_ongoing]} degree is in progress (required: {required}).",
        )
    gap = need - (best_done if best_done is not None else -1)
    value = credit["one_below"] if gap == 1 else credit["two_or_more_below"]
    return value, f"Highest degree ({have}) is below the required level ({required})."


# ----------------------------------------------------------------------- field fit
def field_relation(candidate_field, wanted_field):
    """How are two fields related? -> 'exact' / 'same_category' / 'related_category' / 'different'."""
    if normalize_field(candidate_field).casefold() == normalize_field(wanted_field).casefold():
        return "exact"
    a, b = field_category(candidate_field), field_category(wanted_field)
    if a == b and a not in (None, "other"):
        return "same_category"
    if frozenset({a, b}) in RELATED_CATEGORIES:
        return "related_category"
    return "different"


_RELATION_TEXT = {
    "exact": "Field '{c}' matches the preferred field '{w}'.",
    "same_category": "Field '{c}' is in the same area as '{w}'.",
    "related_category": "Field '{c}' is a related area to '{w}'.",
    "different": "Field '{c}' is different from the preferred fields.",
}


def field_fit(entries, wanted_fields, cfg):
    """(credit 0..1, reason) for the best field match, or None when no entry names a field of study.

    Only degree-level entries (diploma and above) are compared: the "Science" stream of a school
    certificate says little about the job. If the candidate has no such entry, all entries are used.
    """
    degrees = [e for e in entries if (_index(e) or 0) >= LEVEL_ORDER.index("diploma")]
    pool = [e for e in (degrees or entries) if e.get("field_of_study")]
    if not pool:
        return None
    best = (-1.0, "")
    for entry in pool:
        for wanted in wanted_fields:
            relation = field_relation(entry["field_of_study"], wanted)
            value, reason = cfg["field_credit"][relation], _RELATION_TEXT[relation].format(
                c=entry["field_of_study"], w=wanted
            )
            if entry.get("in_progress"):  # unfinished degrees count less
                value *= cfg["in_progress_factor"]
                reason += f" (degree in progress: counts {cfg['in_progress_factor']:.0%})"
            if value > best[0]:
                best = (value, reason)
    return best


# ----------------------------------------------------------------------- education score
def score_education(source, job, config=None):
    """Main entry point: (profile or entries, job profile) -> {status, score, reasons, details}.

    status is one of the Day 13 statuses:
        missing_job        the job states no education requirement
        missing_candidate  no education was found in the resume
        scored             score is a number 0 - 100
    """
    cfg = merged_config(config)
    required = required_level(job)
    wanted, wanted_source = field_targets(job)
    if not required and not wanted:
        return _part("missing_job", reasons=["The job states no education requirement."])
    entries = entries_of(source)
    if not entries:
        return _part("missing_candidate", reasons=["No education found in the resume."])

    parts, reasons = [], []  # parts: (credit, weight)
    level_credit = field_credit = None
    if required in LEVEL_ORDER:
        level_credit, why = level_fit(entries, required, cfg)
        parts.append((level_credit, cfg["level_weight"]))
        reasons.append(why)
    if wanted:
        result = field_fit(entries, wanted, cfg)
        if result is None:
            reasons.append("Field of study not found: field match skipped (not penalised).")
        else:
            field_credit = result[0]
            parts.append((field_credit, cfg["field_weight"]))
            reasons.append(result[1])
            if wanted_source == "default":
                reasons.append(
                    "The job names no field, so the usual fields for a technical role were used."
                )
    elif required in LEVEL_ORDER:
        reasons.append("The job accepts any field of study: only the degree level is scored.")

    if not parts:
        return _part("missing_job", reasons=["Education could not be compared."])
    score = 100 * sum(v * w for v, w in parts) / sum(w for _v, w in parts)
    best_done, _ongoing = _best_levels(entries)
    details = {
        "required_level": required,
        "preferred_fields": [f for f in (job.get("preferred_fields") or []) if f],
        "highest_level": LEVEL_ORDER[best_done] if best_done is not None else None,
        "level_credit": level_credit,
        "field_credit": field_credit,
        "level_met": (
            level_credit == cfg["level_credit"]["met"] if level_credit is not None else None
        ),
        "fields_used": wanted,
        "fields_source": wanted_source,
    }
    return _part("scored", round(score, 1), reasons, details)


# ----------------------------------------------------------------------- certification score
def _skill_in_text(skill, text):
    """True when the skill (or an alias) appears in the text as a whole word ('java' is not in 'javascript')."""
    for name in [skill] + SKILL_ALIASES.get(skill, []):
        if re.search(rf"(?<![a-z0-9]){re.escape(name)}(?![a-z0-9])", text):
            return True
    return False


def job_cert_view(job):
    """What the job wants from certifications: {role_categories, skill_categories, must, good}."""
    must = hard_skills(job.get("must_have_skills") or [])
    good = hard_skills(job.get("good_to_have_skills") or [])
    role = job.get("normalized_title") or ""
    role_cats = ROLE_CERT_CATEGORIES.get(role) or [
        c for c in tag_certification(job.get("title") or role)["categories"] if c != "other"
    ]
    skill_cats = (
        [c for c in tag_certification(" ".join(must + good))["categories"] if c != "other"]
        if (must or good)
        else []
    )
    return {
        "role_categories": role_cats,
        "skill_categories": skill_cats,
        "must": must,
        "good": good,
    }


def rate_certification(cert, view):
    """One certification -> {name, relevance, points, categories, matched skills, reasons}.

    high    names a must-have skill, or belongs to the role's own area (e.g. cloud for a DevOps role)
    medium  names a good-to-have skill, or is in an area the job's skills belong to
    low     anything else
    points = RELEVANCE_POINTS[relevance], then x0.7 if foundational or a course, x0.5 if expired.
    """
    text = f"{cert.get('name', '')} {cert.get('issuer') or ''}".lower()
    cats = [c for c in (cert.get("categories") or []) if c != "other"]
    must = [s for s in view["must"] if _skill_in_text(s, text)]
    good = [s for s in view["good"] if _skill_in_text(s, text)]
    role_hit = [c for c in cats if c in view["role_categories"]]
    area_hit = [c for c in cats if c in view["skill_categories"]]

    reasons = []
    if must or role_hit:
        relevance = "high"
        reasons.append(
            "names must-have skill(s): " + ", ".join(must)
            if must
            else f"belongs to this role's area ({role_hit[0]})"
        )
    elif good or area_hit:
        relevance = "medium"
        reasons.append(
            "names good-to-have skill(s): " + ", ".join(good)
            if good
            else f"in an area the job's skills belong to ({area_hit[0]})"
        )
    else:
        relevance = "low"
        reasons.append("no link to the job's skills or role")

    points = RELEVANCE_POINTS[relevance]
    if cert.get("level") == "foundational":
        points *= FOUNDATIONAL_FACTOR
        reasons.append("foundational level counts 70%")
    if cert.get("kind") == "course":
        points *= COURSE_FACTOR
        reasons.append("a course certificate counts 70%")
    if cert.get("expired"):
        points *= EXPIRED_FACTOR
        reasons.append("expired: counts 50%")
    return {
        "name": cert.get("name"),
        "issuer": cert.get("issuer"),
        "categories": cats or ["other"],
        "relevance": relevance,
        "points": round(points, 2),
        "matched_must_have": must,
        "matched_good_to_have": good,
        "reasons": reasons,
    }


def score_certifications(certifications, job):
    """Rate every certification for this job and give an overall 0 - 100 score.

    overall = 100 * min(1, best_points + 0.25 * (points of all the others))
    -> one strong certification is enough for a high score, more of them can only add a little.
    """
    view = job_cert_view(job)
    if not (view["role_categories"] or view["skill_categories"] or view["must"] or view["good"]):
        return {
            **_part(
                "missing_job", reasons=["The job gives nothing to compare certifications with."]
            ),
            "items": [],
            "counts": {"high": 0, "medium": 0, "low": 0},
        }
    items = sorted(
        (rate_certification(c, view) for c in (certifications or [])), key=lambda i: -i["points"]
    )
    counts = {level: sum(1 for i in items if i["relevance"] == level) for level in RELEVANCE_POINTS}
    if not items:
        return {
            **_part("missing_candidate", reasons=["No certifications found in the resume."]),
            "items": [],
            "counts": counts,
        }
    total = items[0]["points"] + EXTRA_CERT_WEIGHT * sum(i["points"] for i in items[1:])
    score = round(100 * min(1.0, total), 1)
    reasons = [
        f"{counts['high']} high, {counts['medium']} medium, {counts['low']} low relevance certification(s).",
        f"Best: {items[0]['name']} ({items[0]['relevance']}, {items[0]['points']} points).",
    ]
    return {**_part("scored", score, reasons), "items": items, "counts": counts}


# ----------------------------------------------------------------------- combined
def score_education_with_certifications(source, job, config=None):
    """Education score + a small, capped certification bonus.

        combined = min(100, education_score + 10 * certification_score / 100)

    Rules that keep certifications honest:
        * the bonus is never more than CERT_BONUS_MAX (10) points;
        * it is halved when the job's required degree level is not met;
        * if there is no education at all, certifications give at most the bonus: they never replace it;
        * if the job states no education requirement, there is nothing to add a bonus to (missing_job).
    """
    edu = score_education(source, job, config)
    certs = score_certifications(certs_of(source), job)
    cert_score = certs["score"] or 0.0
    bonus = CERT_BONUS_MAX * cert_score / 100
    reasons = list(edu["reasons"])

    if edu["status"] == "missing_job":
        return {
            **edu,
            "education_score": None,
            "certification_score": certs["score"],
            "bonus": 0.0,
            "formula": "no education requirement",
            "certifications": certs,
        }
    if edu["status"] == "missing_candidate":
        bonus = round(bonus, 1)
        reasons.append(
            f"Certifications cannot replace a missing degree: at most {CERT_BONUS_MAX} points "
            f"({bonus} earned)."
        )
        return {
            "status": "missing_candidate",
            "score": bonus,
            "reasons": reasons,
            "details": edu["details"],
            "education_score": None,
            "certification_score": certs["score"],
            "bonus": bonus,
            "formula": f"0 (no education) + {bonus} (certification bonus)",
            "certifications": certs,
        }

    if edu["details"].get("level_met") is False:
        bonus *= BONUS_FACTOR_BELOW_LEVEL
        reasons.append(
            "The required degree level is not met, so the certification bonus counts half."
        )
    bonus = round(bonus, 1)
    score = round(min(100.0, edu["score"] + bonus), 1)
    if bonus:
        reasons.append(f"Certifications add {bonus} points (best: {certs['items'][0]['name']}).")
    return {
        "status": "scored",
        "score": score,
        "reasons": reasons,
        "details": edu["details"],
        "education_score": edu["score"],
        "certification_score": certs["score"],
        "bonus": bonus,
        "formula": f"{score} = {edu['score']} (education) + {bonus} (certification bonus, max {CERT_BONUS_MAX})",
        "certifications": certs,
    }
