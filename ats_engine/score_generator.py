"""Day 13: Candidate score generator.

Resume file (or text)  ->  every earlier module  ->  one explainable ATS report.

    extract text (Day 5) -> sections (Day 8) -> skills (Day 9) -> experience (Day 10)
    -> education + certifications (Day 11) -> text views (Day 12) -> ATSScoringEngine (Day 13)

Try it:
    python -m ats_engine.score_generator data/raw_resumes/Maya.pdf data/parsed_jobs/jd_mern_developer.profile.json
"""
import json
import os
import sys
from pathlib import Path

from ats_engine.scoring_engine import ATSScoringEngine, format_report
from utils.logger import get_logger

log = get_logger(__name__)

MIN_SKILL_CONFIDENCE = 0.4        # skills the extractor is less sure about than this are ignored


def build_resume_bundle_from_text(clean_text, today=None):
    """Whole resume text -> the bundle the scoring engine reads."""
    from matching.semantic_engine import resume_views
    from parsers.education_parser import parse_from_resume_text
    from parsers.experience_parser import parse_experience
    from parsers.section_classifier import segment_resume
    from parsers.skill_extractor import extract_skills_from_segments

    seg = segment_resume(clean_text or "")
    skills = [s["normalized_name"] for s in extract_skills_from_segments(seg)["skills"]
              if s.get("confidence", 1) >= MIN_SKILL_CONFIDENCE]
    experience = parse_experience(seg["sections"].get("experience", ""), today)
    education = parse_from_resume_text(clean_text or "", today)
    views = resume_views(skills, experience["entries"], seg["sections"].get("projects", ""),
                         seg["sections"].get("summary", ""))
    warnings = [] if (clean_text or "").strip() else ["No text could be read from the resume (scanned file?)."]
    return {"skills": skills, "experience": experience, "education": education, "views": views, "warnings": warnings}


def build_resume_bundle_from_file(path, today=None):
    from extraction.extractor import extract_resume
    extracted = extract_resume(path, save=False)
    bundle = build_resume_bundle_from_text(extracted["clean_text"], today)
    bundle["source_file"] = extracted["source_file"]
    return bundle


def load_job(profile_path):
    """Read a Day 6 job profile (*.profile.json) and, if present, the full JD json next to it."""
    profile_path = str(profile_path)
    profile = json.loads(Path(profile_path).read_text(encoding="utf-8"))
    doc_path = profile_path.replace(".profile.json", ".json")
    doc = json.loads(Path(doc_path).read_text(encoding="utf-8")) if doc_path != profile_path and os.path.exists(doc_path) else None
    return profile, doc


def generate_score(resume, job, job_doc=None, candidate_id=None, engine=None, today=None):
    """resume: a file path, the resume text, or a ready bundle (dict).  Returns the explainable report."""
    engine = engine or ATSScoringEngine(today=today)
    if isinstance(resume, dict):
        bundle = resume
    elif os.path.isfile(str(resume)):
        bundle = build_resume_bundle_from_file(resume, today)
        candidate_id = candidate_id or Path(resume).stem
    else:
        bundle = build_resume_bundle_from_text(str(resume), today)
    return engine.score(bundle, job, job_doc, candidate_id or "unknown")


def rank_candidates(reports):
    """Best candidate first. Equal scores: the one with more real data ranks higher."""
    return sorted(reports, key=lambda r: (-r["overall_score"], -r["data_completeness"], r["candidate_id"] or ""))


def save_report(report, out_dir):
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / f"{report['candidate_id']}__{report['job_id']}.json"
    path.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return path


def main(argv=None):
    args = argv if argv is not None else sys.argv[1:]
    if len(args) != 2:
        print("usage: python -m ats_engine.score_generator <resume.pdf|resume.docx> <job.profile.json>")
        return 1
    job, doc = load_job(args[1])
    print(format_report(generate_score(args[0], job, doc)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
