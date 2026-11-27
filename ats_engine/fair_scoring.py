"""Day 15 / Deliverable 1: Fair scoring improvements.

Builds on the Day 13 ATS scoring engine and adds two things:

1. LESS DEPENDENCE ON KEYWORDS (evidence-aware skill credit)
   A skill that only appears in a skills list is a claim. A skill that is also used in a job or project is evidence.
       listed AND used in experience / projects  -> full credit
       listed only                               -> LISTED_ONLY_CREDIT (70%) of the credit
   Exceptions, so nobody is punished unfairly:
       * soft skills (communication, teamwork...) are never expected inside bullets  -> full credit
       * skills whose name is an ordinary word (express, go, r...) cannot be found reliably in text -> full credit
       * candidates with no experience and no projects text (freshers, short resumes) -> nothing to check against
         -> full credit, and the report says "evidence check not applicable"
   Keyword stuffing (a very long skills list that is mostly unused) is flagged, and an automatic "shortlist"
   becomes "review" so a person looks at the resume.

2. SCORE NORMALIZATION (comparing candidates fairly)
   Raw scores are not on the same scale for every job (a hard job gives everybody lower scores). Inside one job's
   candidate pool the scores can be converted to percentile, T-score (50 +/- 10 per standard deviation) or min-max.
   Pools smaller than MIN_POOL are NOT normalized (it would be meaningless); the raw score is kept and a note is added.

The raw score is never hidden: every report keeps overall_score and adds a `fairness` block and a `normalized` block.

Usage:
    from ats_engine.fair_scoring import FairATSScoringEngine, normalize_reports, fair_score_resumes
    reports = fair_score_resumes({"maya": "data/raw_resumes/Maya.pdf", ...}, job, job_doc, method="percentile")
"""
import math
from collections import defaultdict

from ats_engine.score_generator import generate_score
from ats_engine.scoring_engine import ATSScoringEngine
from ats_engine.weights import COMPONENTS
from parsers import skill_extractor as _sx
from parsers.experience_parser import find_skills
from parsers.skill_taxonomy import SKILLS
from utils.logger import get_logger

log = get_logger(__name__)

FAIRNESS_VERSION = "1.0.0"
LISTED_ONLY_CREDIT = 0.7       # a skill that is only listed earns 70% of the credit of a skill that is also used
MUST_SHARE, GOOD_SHARE = 0.75, 0.25
STUFFING_MIN_LISTED = 20       # a skills list this long ...
STUFFING_MAX_EVIDENCE = 0.35   # ... where fewer than 35% of the skills are used anywhere, looks like keyword stuffing
MIN_POOL = 5                   # smallest candidate pool that can be normalized
METHODS = ("percentile", "zscore", "minmax")


# ----------------------------------------------------------------------------- 1. evidence-aware skills
# Skills whose name is also an ordinary word (express, go, r, spring...). The Day 9 extractor ignores them in plain
# sentences, so "not found in a job bullet" proves nothing about them: they are never penalised for missing evidence.
UNDETECTABLE_IN_TEXT = {_sx._ALIAS_INDEX[k][0] for k in _sx._AMBIGUOUS if k in _sx._ALIAS_INDEX}


def skill_evidence(resume):
    """(set of skills used in experience / projects, whether this check can be done for this resume)."""
    used = set()
    for entry in (resume.get("experience") or {}).get("entries", []):
        used |= set(entry.get("skills_used") or [])
    projects = (resume.get("views") or {}).get("projects", "") or ""
    used |= set(find_skills(projects))
    applicable = bool((resume.get("experience") or {}).get("entries")) or bool(projects.strip())
    return used, applicable


def skill_shares(must, good):
    """How much of the skill score each wanted skill is worth (same split as the Day 12 matcher: 75% / 25%)."""
    shares = {}
    if must and good:
        shares.update({s: MUST_SHARE / len(must) for s in must})
        shares.update({s: GOOD_SHARE / len(good) for s in good})
    else:
        names = must or good
        shares.update({s: 1 / len(names) for s in names})
    return shares


class FairATSScoringEngine(ATSScoringEngine):
    """The Day 13 engine with an evidence-aware skill part. Everything else (weights, missing data) is unchanged."""

    def _skill_match(self, resume, jv):
        part = super()._skill_match(resume, jv)
        if part["status"] != "scored":
            return part
        exact = part["details"]["matched_exact"]
        used, applicable = skill_evidence(resume)
        soft = [s for s in exact if SKILLS.get(s, ("",))[0] == "soft_skill"]
        undetectable = [s for s in exact if s in UNDETECTABLE_IN_TEXT]
        listed_only = [s for s in exact if applicable and s not in used and s not in soft and s not in undetectable]
        evidenced = [s for s in exact if s in used]

        shares = skill_shares(jv.get("must", []), jv.get("good", []))
        penalty = 100 * sum(shares.get(s, 0) * (1 - LISTED_ONLY_CREDIT) for s in listed_only)
        before = part["score"]
        part["score"] = round(max(0.0, before - penalty), 1)

        listed = list(dict.fromkeys(resume.get("skills") or []))
        ratio = round(sum(s in used for s in listed) / len(listed), 2) if (listed and applicable) else None
        stuffing = bool(ratio is not None and len(listed) >= STUFFING_MIN_LISTED and ratio < STUFFING_MAX_EVIDENCE)

        if not applicable:
            part["reasons"].append("Evidence check not applicable (no experience or project text): listed skills get full credit.")
        elif listed_only:
            part["reasons"].append(f"{len(listed_only)} matched skill(s) are listed but not used in any job or project "
                                   f"({', '.join(listed_only)}): credit reduced to {int(LISTED_ONLY_CREDIT * 100)}% "
                                   f"(-{penalty:.1f} points).")
        elif exact:
            part["reasons"].append("All matched skills are backed by use in a job or project: full credit.")
        part["details"]["evidence"] = {"applicable": applicable, "evidenced": evidenced, "listed_only": listed_only,
                                       "soft_skills_exempt": soft, "ambiguous_skills_exempt": undetectable,
                                       "credit_for_listed_only": LISTED_ONLY_CREDIT,
                                       "skill_score_before": before, "skill_points_removed": round(penalty, 1),
                                       "listed_skills": len(listed), "evidence_ratio": ratio, "keyword_stuffing": stuffing}
        return part

    def score(self, resume, job, job_doc=None, candidate_id=None):
        report = super().score(resume, job, job_doc, candidate_id)
        ev = report["components"]["skill_match"]["details"].get("evidence")
        weight = report["components"]["skill_match"]["weight"]
        fairness = {"version": FAIRNESS_VERSION, "keyword_evidence": ev or {"applicable": False},
                    "overall_points_removed": round(weight * ev["skill_points_removed"], 1) if ev else 0.0,
                    "notes": []}
        if ev and ev["keyword_stuffing"]:
            note = (f"Possible keyword stuffing: {ev['listed_skills']} skills listed but only "
                    f"{int(ev['evidence_ratio'] * 100)}% are used in a job or project.")
            report["flags"].append(note)
            fairness["notes"].append(note)
            if report["recommendation"] == "shortlist":
                report["recommendation"] = "review"
                report["recommendation_reason"] = "Score reaches the cutoff, but the skills list looks stuffed: check the resume manually."
        report["fairness"] = fairness
        return report


# ----------------------------------------------------------------------------- 2. score normalization
def percentiles(values):
    """Mid-rank percentile (0-100). Equal scores get the same percentile."""
    n = len(values)
    return [round(100 * (sum(v < x for v in values) + 0.5 * sum(v == x for v in values)) / n, 1) for x in values]


def t_scores(values):
    """50 + 10 * z. The pool average becomes 50. All equal -> everybody 50."""
    mean = sum(values) / len(values)
    std = math.sqrt(sum((v - mean) ** 2 for v in values) / len(values))
    return [50.0 if std == 0 else round(50 + 10 * (v - mean) / std, 1) for v in values]


def min_max(values):
    low, high = min(values), max(values)
    return [50.0 if high == low else round(100 * (v - low) / (high - low), 1) for v in values]


_METHOD_FUNCS = {"percentile": percentiles, "zscore": t_scores, "minmax": min_max}


def normalize_values(values, method="percentile"):
    if method not in _METHOD_FUNCS:
        raise ValueError(f"method must be one of {METHODS}, got '{method}'")
    return _METHOD_FUNCS[method](list(values))


def normalize_reports(reports, method="percentile", min_pool=MIN_POOL, by="job_id"):
    """Adds report['normalized'] to every report, comparing candidates only with others for the SAME job.

    normalized = {"method", "pool_size", "overall": value or None, "components": {name: value}, "note"}
    The raw overall_score is never changed.
    """
    if method not in METHODS:
        raise ValueError(f"method must be one of {METHODS}, got '{method}'")
    pools = defaultdict(list)
    for report in reports:
        pools[report.get(by)].append(report)
    for key, everyone in pools.items():
        empty = [r for r in everyone if r.get("data_completeness", 1) <= 0]       # nothing could be scored (scanned / empty)
        for r in empty:
            r["normalized"] = {"method": method, "pool_size": 0, "overall": None, "components": {},
                               "note": "Nothing could be scored for this resume, so it is left out of the normalization pool."}
        pool = [r for r in everyone if r not in empty]
        n = len(pool)
        if n < min_pool:
            for r in pool:
                r["normalized"] = {"method": method, "pool_size": n, "overall": None, "components": {},
                                   "note": f"Only {n} candidate(s) for this job; at least {min_pool} are needed to normalize. Raw score kept."}
            continue
        overall = normalize_values([r["overall_score"] for r in pool], method)
        for r, value in zip(pool, overall):
            r["normalized"] = {"method": method, "pool_size": n, "overall": value, "components": {}, "note": None}
        for name in COMPONENTS:
            have = [r for r in pool if r["components"][name]["score"] is not None]
            if len(have) >= min_pool:
                for r, value in zip(have, normalize_values([r["components"][name]["score"] for r in have], method)):
                    r["normalized"]["components"][name] = value
    return reports


# ----------------------------------------------------------------------------- 3. convenience
def fair_score_resumes(resumes, job, job_doc=None, engine=None, method="percentile", min_pool=MIN_POOL):
    """resumes: {candidate_id: file path / text / bundle}. Scores every candidate fairly, then normalizes the pool."""
    engine = engine or FairATSScoringEngine()
    reports = [generate_score(resume, job, job_doc, candidate_id=cid, engine=engine) for cid, resume in resumes.items()]
    return normalize_reports(reports, method, min_pool)


def format_fair_line(report):
    n = report.get("normalized") or {}
    norm = f"{n['overall']:>5}" if n.get("overall") is not None else "  n/a"
    removed = report.get("fairness", {}).get("overall_points_removed", 0.0)
    return (f"{str(report['candidate_id'])[:22]:22} score {report['overall_score']:5.1f}  "
            f"keyword adj -{removed:<4}  {n.get('method', '-')}: {norm}  -> {report['recommendation']}")
