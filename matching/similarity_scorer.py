"""Day 12 / Deliverable 2: Resume <-> Job Description similarity scorer.

One small entry point on top of the Day 12 SemanticMatcher. It gives ONE clear answer for a resume
and a job: a 0-100 score, a label (strong / good / partial / weak), the three part scores, the skills
that matched or are missing, and short plain-English reasons.

The label cut-offs are NOT written in this file. They live in `matching/similarity_thresholds.json`
(the values the accuracy report tunes), and are checked when they are loaded.

    from matching.similarity_scorer import score_resume_to_job, score_many
    result = score_resume_to_job("data/raw_resumes/Maya.pdf", job_profile, job_doc)
    ranked = score_many(["a.pdf", "b.pdf"], job_profile, job_doc)

Command line:
    python -m matching.similarity_scorer data/raw_resumes/Maya.pdf data/parsed_jobs/jd_mern_developer.profile.json
"""
import json
import sys
from pathlib import Path

from matching.semantic_engine import (
    SemanticMatcher, job_views, resume_views_from_text,
)
from utils.logger import get_logger

log = get_logger(__name__)

CONFIG_PATH = Path(__file__).with_name("similarity_thresholds.json")
LABEL_NAMES = ("strong", "good", "partial")          # anything below "partial" is "weak"
PARTS = ("skills", "experience", "projects")
_cache = {}


# ----------------------------------------------------------------------------- thresholds (config file)
def validate_thresholds(config):
    """Return a list of problems with a thresholds config (empty list = fine)."""
    labels = config.get("labels") if isinstance(config, dict) else None
    if not isinstance(labels, dict):
        return ["'labels' must be an object like {\"strong\": 75, \"good\": 55, \"partial\": 35}"]
    errors = []
    if set(labels) != set(LABEL_NAMES):
        errors.append(f"labels: must contain exactly {list(LABEL_NAMES)}")
    values = [labels.get(name) for name in LABEL_NAMES]
    if any(isinstance(v, bool) or not isinstance(v, (int, float)) for v in values):
        errors.append("labels: every value must be a number")
    elif any(v < 0 or v > 100 for v in values):
        errors.append("labels: every value must be between 0 and 100")
    elif not values[0] > values[1] > values[2]:
        errors.append("labels: must satisfy strong > good > partial")
    return errors


def load_thresholds(path=None):
    """Read (and cache) the thresholds file. Raises ValueError with all problems if it is bad."""
    path = Path(path) if path else CONFIG_PATH
    key = str(path.resolve())
    if key not in _cache:
        config = json.loads(path.read_text(encoding="utf-8"))
        errors = validate_thresholds(config)
        if errors:
            raise ValueError("Bad similarity thresholds: " + "; ".join(errors))
        _cache[key] = config
    return _cache[key]


def label_for(score, thresholds=None):
    """Score (0-100) -> 'strong' / 'good' / 'partial' / 'weak'. A score equal to a cut-off gets the higher one."""
    labels = (thresholds or load_thresholds())["labels"]
    for name in LABEL_NAMES:
        if score >= labels[name]:
            return name
    return "weak"


# ----------------------------------------------------------------------------- turning inputs into views
def _is_views(resume):
    return isinstance(resume, dict) and "skills" in resume


def _looks_like_path(text):
    """A one-line string that ends in .pdf / .docx is meant as a file name, not as resume text."""
    return "\n" not in text and text.strip().lower().endswith((".pdf", ".docx"))


def resume_to_views(resume):
    """Accept a file path, resume text or ready views. Returns (views, problem). problem is None if fine."""
    if _is_views(resume):
        return resume, None
    is_file = isinstance(resume, Path) or (
        isinstance(resume, str) and (Path(resume).exists() or _looks_like_path(resume)))
    if is_file:
        from extraction.extractor import extract_resume
        extracted = extract_resume(resume, save=False)          # raises if the file is missing / wrong type
        if extracted["status"] != "ok" or not extracted["clean_text"].strip():
            why = "scanned image (needs OCR)" if extracted.get("needs_ocr") else "no readable text"
            return None, f"Resume file has {why}; it cannot be scored."
        return resume_views_from_text(extracted["clean_text"]), None
    if isinstance(resume, str):
        return resume_views_from_text(resume), None
    raise TypeError("resume must be a file path, text, or views dict")


def default_name(resume):
    """File name for a path, otherwise None (text and views have no name of their own)."""
    if isinstance(resume, Path) or (isinstance(resume, str) and _looks_like_path(resume)):
        return Path(resume).name
    return None


def _has_words(text):
    """True if the text has at least one letter or digit (job_views can produce a text like '. .')."""
    return any(ch.isalnum() for ch in (text or ""))


def _has_resume_data(views):
    return bool(views.get("skills")) or any(_has_words(views.get(k)) for k in ("experience", "projects"))


def _has_job_data(job):
    return bool(job.get("skills")) or any(_has_words(job.get(k)) for k in ("experience", "projects"))


# ----------------------------------------------------------------------------- the result
def _unscorable(name, job_id, reason, embedder_name):
    """A result for something that cannot be scored. The score is None, never a fake 0."""
    return {"status": "unscorable", "resume": name, "job": job_id, "similarity_score": None, "label": None,
            "parts": {p: None for p in PARTS}, "matched_skills": [], "related_skills": [],
            "missing_must_have": [], "parts_without_data": [], "embedder": embedder_name,
            "reasons": [reason]}


def _names(items, limit=5):
    shown = ", ".join(items[:limit])
    return shown + (f" (+{len(items) - limit} more)" if len(items) > limit else "")


def build_reasons(score, label, parts, skills, must, no_data):
    """A few short plain-English sentences that explain the score."""
    reasons = [f"Overall similarity {score}/100, which is '{label}'."]
    if skills:
        exact_must = [s for s in skills["matched_exact"] if s in must]
        if must:
            have = _names(exact_must) or "none"
            reasons.append(f"Has {len(exact_must)} of {len(must)} must-have skills: {have}.")
        missing = [s for s in skills["missing"] if s in must]
        if missing:
            reasons.append(f"Missing must-have skills: {_names(missing)}.")
        if skills["matched_semantic"]:
            pairs = [f"{m['resume_skill']} ~ {m['job_skill']}" for m in skills["matched_semantic"]]
            reasons.append(f"Related (not identical) skills: {_names(pairs, 3)}.")
    scored = {k: v for k, v in parts.items() if v is not None}
    if len(scored) > 1:
        weakest = min(scored, key=scored.get)
        reasons.append(f"Weakest part: {weakest} ({scored[weakest]}/100).")
    if no_data:
        reasons.append(f"No data for {', '.join(no_data)}: skipped, other parts count more.")
    return reasons


def score_resume_to_job(resume, job_profile, job_doc=None, matcher=None, name=None, thresholds=None):
    """Score one resume against one job. resume: file path, text, or views. job_profile: Day 6 profile dict.

    Returns a dict with status 'scored' or 'unscorable' (see _unscorable). A resume with no readable text
    is 'unscorable' (similarity_score None); a missing file raises FileNotFoundError.
    """
    matcher = matcher or SemanticMatcher()
    job_id = job_profile.get("job_id") or job_profile.get("title")
    name = name or default_name(resume)
    views, problem = resume_to_views(resume)
    if problem or not _has_resume_data(views):
        log.warning("Resume %s is unscorable", name)
        return _unscorable(name, job_id, problem or "Resume has no skills, experience or project text.",
                           matcher.embedder.name)
    job = job_views(job_profile, job_doc)
    if not _has_job_data(job):
        return _unscorable(name, job_id, "Job has no skills or text to compare with.", matcher.embedder.name)

    match = matcher.match(views, job)
    parts = {p: (round(100 * c["score"]) if c else None) for p, c in match["components"].items()}
    no_data = [p for p, v in parts.items() if v is None]
    score = match["overall"]
    label = label_for(score, thresholds)
    skills = match["components"]["skills"] or {"matched_exact": [], "matched_semantic": [], "missing": []}
    must = job.get("must", [])
    return {"status": "scored", "resume": name, "job": job_id, "similarity_score": score, "label": label,
            "parts": parts, "matched_skills": list(skills["matched_exact"]),
            "related_skills": list(skills["matched_semantic"]),
            "missing_must_have": [s for s in skills["missing"] if s in must],
            "parts_without_data": no_data, "embedder": match["backend"],
            "reasons": build_reasons(score, label, parts, match["components"]["skills"], must, no_data)}


def score_many(resumes, job_profile, job_doc=None, matcher=None, thresholds=None):
    """Score many resumes against ONE job. resumes: list, or {name: resume}. Best first, unscorable last."""
    matcher = matcher or SemanticMatcher()                 # one matcher = embeddings are re-used
    items = resumes.items() if isinstance(resumes, dict) else [(None, r) for r in resumes]
    results = []
    for i, (name, resume) in enumerate(items, 1):
        name = name or default_name(resume) or f"resume_{i}"
        results.append(score_resume_to_job(resume, job_profile, job_doc, matcher, name=name,
                                           thresholds=thresholds))
    return sorted(results, key=lambda r: (r["status"] != "scored", -(r["similarity_score"] or 0),
                                          r["resume"] or ""))


# ----------------------------------------------------------------------------- command line
def format_result(result):
    """Plain-text version of one result (used by the command line)."""
    if result["status"] != "scored":
        return f"{result['resume']}: UNSCORABLE - {result['reasons'][0]}"
    parts = "  ".join(f"{p} {v if v is not None else '-'}" for p, v in result["parts"].items())
    lines = [f"{result['resume']} vs {result['job']}: {result['similarity_score']}/100 ({result['label']})",
             f"  parts: {parts}   embedder: {result['embedder']}"]
    lines += [f"  - {r}" for r in result["reasons"]]
    return "\n".join(lines)


def main(argv=None):
    """python -m matching.similarity_scorer <resume> <job.profile.json>  (add --json for raw output)"""
    args = list(sys.argv[1:] if argv is None else argv)
    as_json = "--json" in args
    args = [a for a in args if a != "--json"]
    if len(args) != 2:
        print("Usage: python -m matching.similarity_scorer <resume.pdf|.docx> <job.profile.json> [--json]")
        return 2
    profile_path = Path(args[1])
    profile = json.loads(profile_path.read_text(encoding="utf-8"))
    doc_path = Path(str(profile_path).replace(".profile.json", ".json"))
    has_doc = doc_path != profile_path and doc_path.exists()
    doc = json.loads(doc_path.read_text(encoding="utf-8")) if has_doc else None
    result = score_resume_to_job(Path(args[0]), profile, doc)
    print(json.dumps(result, indent=2) if as_json else format_result(result))
    return 0


if __name__ == "__main__":
    sys.exit(main())
