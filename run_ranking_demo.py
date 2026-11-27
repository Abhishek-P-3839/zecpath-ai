"""Day 14 demo: rank every sample resume for each parsed job, then sort them into zones.

Run (project root, venv active):   python run_ranking_demo.py
Writes, for every job:
    data/rankings/<job_id>.ranking.json / .csv / .txt     the ranked list
    data/shortlists/<job_id>.shortlist.json / .csv / .txt shortlisted / review / rejected zones
Every resume is scored once per job. Candidates of different jobs are never ranked together.
"""
from pathlib import Path

from ats_engine.ranking_engine import collect_resumes, rank_resume_files, save_ranking
from ats_engine.score_generator import load_job
from ats_engine.shortlisting import build_shortlist, load_config, save_shortlist
from utils.logger import get_logger

log = get_logger(__name__)
ROOT = Path(__file__).resolve().parent


def main():
    files = collect_resumes([ROOT / "data" / "raw_resumes"])
    config = load_config()
    for profile in sorted((ROOT / "data" / "parsed_jobs").glob("*.profile.json")):
        job, job_doc = load_job(profile)
        ranking = rank_resume_files(files, job, job_doc)
        shortlist = build_shortlist(ranking, job, config)
        save_ranking(ranking, ROOT / "data" / "rankings")
        save_shortlist(shortlist, ROOT / "data" / "shortlists")
        c, s = shortlist["counts"], ranking["score_summary"]
        print(f"{job['title']:28s} candidates={c['total']}  shortlisted={c['SHORTLISTED']}  "
              f"waitlist={c['WAITLIST']}  review={c['REVIEW']}  rejected={c['REJECTED']}  "
              f"scores {s['lowest']}-{s['highest']}" if s else f"{job['title']}: no candidates")
        for warning in shortlist["warnings"]:
            print(f"    warning: {warning}")


if __name__ == "__main__":
    main()
