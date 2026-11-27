"""Day 15 demo: fair scoring on the sample resumes.   python run_fair_scoring_demo.py [job_profile.json] [pool_size_needed]"""
import glob
import os
import sys

from ats_engine.fair_scoring import FairATSScoringEngine, fair_score_resumes, format_fair_line
from ats_engine.score_generator import load_job
from extraction.extractor import SUPPORTED

profile_path = sys.argv[1] if len(sys.argv) > 1 else "data/parsed_jobs/jd_mern_developer.profile.json"
min_pool = int(sys.argv[2]) if len(sys.argv) > 2 else 5
job, doc = load_job(profile_path)
resumes = {os.path.splitext(os.path.basename(p))[0]: p for p in sorted(glob.glob("data/raw_resumes/*"))
           if os.path.splitext(p)[1].lower() in SUPPORTED}

print(f"Job: {job['title']}   candidates: {len(resumes)}   (normalization needs >= {min_pool} per job)\n")
reports = fair_score_resumes(resumes, job, doc, engine=FairATSScoringEngine(), method="percentile", min_pool=min_pool)
for r in sorted(reports, key=lambda r: -r["overall_score"]):
    print(format_fair_line(r))
print()
for r in reports:
    ev = r["fairness"]["keyword_evidence"]
    if ev.get("listed_only"):
        print(f"{r['candidate_id']}: listed but not used -> {', '.join(ev['listed_only'])} (-{ev['skill_points_removed']} skill points)")
    for note in r["fairness"]["notes"]:
        print(f"{r['candidate_id']}: {note}")
if reports and reports[0]["normalized"]["overall"] is None:
    print("\n" + reports[0]["normalized"]["note"])
