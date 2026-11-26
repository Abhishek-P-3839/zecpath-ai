"""Day 7 demo: push ONE candidate through the whole AI data pipeline and store every result.

Run from the project root (venv active):
    python run_pipeline_demo.py
    python run_pipeline_demo.py data/raw_resumes/alex.pdf     (use another resume)
Output goes to data/store/ (see docs/Day7_Storage_Structure.md).
"""
import sys
from pathlib import Path

from ats_engine.ats_scorer import calculate_ats_score
from extraction.extractor import extract_resume
from interview_ai.interview import get_hr_questions, get_technical_level
from parsers.resume_parser import parse_resume_text
from pipeline.lifecycle import get_history, record_event
from pipeline.storage import load_record, save_record, save_resume_file, verify_record
from pipeline.versioning import build_training_snapshot
from scoring.scoring import combine_scores, get_decision
from screening_ai.screening import build_screening_report

CANDIDATE_ID = "cand_0001"
JOB_ID = "job_python_developer"
REQUIRED_SKILLS = ["Python", "SQL", "Git"]


def main(resume_path):
    # 1. UPLOAD: keep the original file
    save_resume_file(resume_path, CANDIDATE_ID)
    record_event(CANDIDATE_ID, JOB_ID, "uploaded", note="resume file stored")

    # 2. PARSE: text extraction -> structured profile
    extracted = extract_resume(resume_path, save=False)
    parsed = parse_resume_text(extracted["clean_text"])
    profile = {**parsed, "extraction": {"status": extracted["status"], "page_count": extracted["page_count"],
                                        "char_count": extracted["char_count"]}}
    save_record("parsed_profile", profile, CANDIDATE_ID, source_file=Path(resume_path).name)
    record_event(CANDIDATE_ID, JOB_ID, "parsed")

    # 3. ATS SCORE: resume vs job
    ats = calculate_ats_score(parsed, REQUIRED_SKILLS, min_experience=0)
    save_record("ats_score", {"score": ats, "required_skills": REQUIRED_SKILLS,
                              "matched_skills": [s for s in REQUIRED_SKILLS if s.lower() in parsed["skills"]]},
                CANDIDATE_ID, JOB_ID)
    record_event(CANDIDATE_ID, JOB_ID, "ats_scored")

    # 4. SCREENING (sample answers; real ones come from the screening AI later)
    answers = {"self_introduction": "yes", "education": "B.Tech", "total_experience": "1",
               "relevant_skills": "Python", "current_location": "Kochi", "notice_period": "15 days"}
    save_record("screening_report", build_screening_report(answers), CANDIDATE_ID, JOB_ID)
    record_event(CANDIDATE_ID, JOB_ID, "screened")

    # 5. INTERVIEW (sample scores)
    interview = {"hr_questions": get_hr_questions(),
                 "technical_level": get_technical_level(parsed["experience_years"]),
                 "scores": {"hr": 70, "technical": 65, "machine_test": 75}}
    save_record("interview_result", interview, CANDIDATE_ID, JOB_ID)
    record_event(CANDIDATE_ID, JOB_ID, "interviewed")

    # 6. DECISION
    final = combine_scores({"ats": ats, **interview["scores"]})
    save_record("hiring_decision", {"final_score": final, "decision": get_decision(final)}, CANDIDATE_ID, JOB_ID)
    record_event(CANDIDATE_ID, JOB_ID, "decided")

    # Show what happened
    print("\nLifecycle history:")
    for e in get_history(CANDIDATE_ID, JOB_ID):
        print(" ", e["timestamp"], e["stage"])
    saved = load_record("ats_score", CANDIDATE_ID, JOB_ID)
    print("\nLatest ATS record metadata:")
    for k, v in saved["metadata"].items():
        print(f"  {k}: {v}")
    print("Checksum still valid:", verify_record(saved))

    # 7. RETRAINING DATASET: freeze a versioned snapshot
    folder, manifest = build_training_snapshot()
    print("\nTraining snapshot created:", folder)
    print("  version:", manifest["dataset_version"], "| records:", manifest["record_count"])


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "data/raw_resumes/sample_simple.pdf")
