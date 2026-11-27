"""Day 12 / Deliverable 1: Semantic matching engine.

Compares a resume with a job on three things, each with embeddings:

    skills       what the candidate knows   vs  what the job needs        (exact + meaning-based matches)
    experience   what they did at work      vs  what the job will involve
    projects     what they built            vs  what the job will build

    overall (0-100) = weighted average of the parts that have data (missing parts are skipped, weights re-scaled)

Usage:
    from matching.semantic_engine import SemanticMatcher, resume_views_from_file, job_views
    matcher = SemanticMatcher()                              # picks the best embedder available
    result = matcher.match(resume_views_from_file("data/raw_resumes/Maya.pdf"), job_views(job_profile, job_doc))
"""
import json
import numpy as np

from matching.embedders import get_embedder
from parsers.skill_taxonomy import SKILLS
from utils.logger import get_logger

log = get_logger(__name__)

WEIGHTS = {"skills": 0.45, "experience": 0.35, "projects": 0.20}
SKILL_SEMANTIC_THRESHOLD = 0.70      # two different skills count as "related" above this similarity
SKILL_SEMANTIC_CREDIT = 0.5          # ...and earn this fraction of an exact match
MUST_WEIGHT, GOOD_WEIGHT = 0.75, 0.25
LABELS = [(75, "strong"), (55, "good"), (35, "partial"), (0, "weak")]


# ----------------------------------------------------------------------------- build the "views" (text to compare)
def resume_views(skills, experience_entries, projects_text="", summary=""):
    """skills: canonical skill names. experience_entries: Day 10 entries. Returns the text views of a resume."""
    exp_lines = []
    for e in experience_entries:
        head = f"{e.get('designation', '')} at {e.get('company', '')}".strip()
        body = " ".join(e.get("responsibilities") or []) or (e.get("description") or "")
        exp_lines.append(f"{head}. {body}")
    return {"skills": list(skills), "experience": "\n".join(exp_lines), "projects": projects_text or "", "summary": summary or ""}


def resume_views_from_text(clean_text):
    """Whole resume text -> segment (Day 8) -> skills (Day 9) -> experience (Day 10) -> views."""
    from parsers.experience_parser import parse_experience
    from parsers.section_classifier import segment_resume
    from parsers.skill_extractor import extract_skills_from_segments
    seg = segment_resume(clean_text)
    skills = [s["normalized_name"] for s in extract_skills_from_segments(seg)["skills"] if s.get("confidence", 1) >= 0.4]
    exp = parse_experience(seg["sections"].get("experience", ""))
    return resume_views(skills, exp["entries"], seg["sections"].get("projects", ""), seg["sections"].get("summary", ""))


def resume_views_from_file(path):
    from extraction.extractor import extract_resume
    return resume_views_from_text(extract_resume(path, save=False)["clean_text"])


def job_views(profile, doc=None):
    """profile: Day 6 flat AI profile. doc (optional): the full JD json with description / responsibilities."""
    doc = doc or {}
    resp = doc.get("responsibilities") or []
    resp_text = " ".join(resp) if isinstance(resp, list) else str(resp)
    must, good = profile.get("must_have_skills", []), profile.get("good_to_have_skills", [])
    experience = f"{profile.get('title', '')}. {profile.get('normalized_title', '')}. {resp_text}".strip()
    return {"skills": must + good, "must": must, "good": good, "experience": experience,
            "projects": f"{doc.get('description', '')} {resp_text}".strip(), "summary": profile.get("summary", "")}


# ----------------------------------------------------------------------------- the engine
class SemanticMatcher:
    def __init__(self, embedder=None, weights=None, calibration=None):
        self.embedder = embedder or get_embedder()
        self.weights = weights or dict(WEIGHTS)
        self.calibration = calibration or self.embedder.default_calibration      # (low, high) cosine -> 0..1
        self._cache = {}

    # -- embeddings --------------------------------------------------------
    def embed(self, texts):
        missing = [t for t in dict.fromkeys(texts) if t not in self._cache]
        if missing:
            for t, v in zip(missing, self.embedder.encode(missing)):
                self._cache[t] = v
        return np.stack([self._cache[t] for t in texts])

    def similarity(self, a, b):
        """Cosine similarity of two texts, -1..1 (normally 0..1)."""
        va, vb = self.embed([a, b])
        return float(np.dot(va, vb))

    def calibrate(self, cosine):
        """Raw cosine -> 0..1 'match strength'. Cosines are never near 1 for different texts, so we stretch them."""
        low, high = self.calibration
        return float(min(1.0, max(0.0, (cosine - low) / (high - low))))

    # -- the three comparisons ----------------------------------------------
    def compare_skills(self, resume_skills, job):
        must, good = job.get("must", []), job.get("good", [])
        wanted = must + good
        if not wanted:
            return None
        have = set(resume_skills)
        exact, semantic, missing, credit = [], [], [], {}
        if have:
            have_list = sorted(have)
            sims = self.embed(wanted) @ self.embed(have_list).T
        for i, skill in enumerate(wanted):
            if skill in have:
                exact.append(skill); credit[skill] = 1.0
            elif have:
                j = int(np.argmax(sims[i]))
                if sims[i][j] >= SKILL_SEMANTIC_THRESHOLD:
                    semantic.append({"job_skill": skill, "resume_skill": have_list[j], "similarity": round(float(sims[i][j]), 2)})
                    credit[skill] = SKILL_SEMANTIC_CREDIT * float(sims[i][j])
                    continue
            if skill not in credit:
                missing.append(skill); credit[skill] = 0.0
        part = lambda names: sum(credit[s] for s in names) / len(names) if names else None
        m, g = part(must), part(good)
        coverage = (MUST_WEIGHT * m + GOOD_WEIGHT * g) if (m is not None and g is not None) else (m if m is not None else g)
        cosine = self.similarity(" ".join(sorted(have)), " ".join(wanted)) if have else 0.0
        score = 0.6 * coverage + 0.4 * self.calibrate(cosine)
        return {"score": round(score, 3), "coverage": round(coverage, 3), "cosine": round(cosine, 3),
                "matched_exact": exact, "matched_semantic": semantic, "missing": missing}

    def compare_text(self, resume_text, job_text):
        if not (resume_text or "").strip() or not (job_text or "").strip():
            return None
        cosine = self.similarity(resume_text, job_text)
        return {"score": round(self.calibrate(cosine), 3), "cosine": round(cosine, 3)}

    # -- everything together --------------------------------------------------
    def match(self, resume, job):
        components = {
            "skills": self.compare_skills(resume.get("skills", []), job),
            "experience": self.compare_text(resume.get("experience", ""), job.get("experience", "")),
            "projects": self.compare_text(resume.get("projects", ""), job.get("projects", "")),
        }
        used = {k: self.weights[k] for k, v in components.items() if v is not None}
        total = sum(used.values())
        overall = round(100 * sum(components[k]["score"] * w for k, w in used.items()) / total) if total else 0
        warnings = [f"No data for '{k}': skipped and weights re-scaled." for k, v in components.items() if v is None]
        return {"overall": overall, "label": next(l for t, l in LABELS if overall >= t),
                "components": components, "weights_used": {k: round(w / total, 2) for k, w in used.items()} if total else {},
                "backend": self.embedder.name, "warnings": warnings}
