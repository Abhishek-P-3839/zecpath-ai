"""Day 13 demo: score every resume against every parsed job and rank the candidates.

    python run_ats_demo.py

Output:  data/ats_scores/<resume>__<job>.json  (full explainable report for each pair)
         the ranking per job and the full explanation of the best candidate are printed.
"""
from pathlib import Path

from ats_engine.score_generator import (build_resume_bundle_from_file, generate_score, load_job,
                                        rank_candidates, save_report)
from ats_engine.scoring_engine import ATSScoringEngine, format_report
from extraction.extractor import SUPPORTED

RAW_DIR, JOB_DIR, OUT_DIR = Path("data/raw_resumes"), Path("data/parsed_jobs"), Path("data/ats_scores")


def main():
    engine = ATSScoringEngine()
    print("Embedding backend:", getattr(engine.matcher, "embedder", None) and engine.matcher.embedder.name)
    jobs = {p.name.removesuffix(".profile.json"): load_job(p) for p in sorted(JOB_DIR.glob("*.profile.json"))}
    bundles = {}
    for path in sorted(p for p in RAW_DIR.iterdir() if p.suffix.lower() in SUPPORTED):
        bundles[path.stem] = build_resume_bundle_from_file(path)

    for job_name, (job, doc) in jobs.items():
        reports = [generate_score(b, job, doc, candidate_id=stem, engine=engine) for stem, b in bundles.items()]
        for r in reports:
            save_report(r, OUT_DIR)
        ranking = rank_candidates(reports)
        print(f"\n=== {job['title']}  (weights: {ranking[0]['weights']['source']}) ===")
        for i, r in enumerate(ranking, 1):
            print(f"{i:2}. {r['candidate_id']:24} {r['overall_score']:5.1f}  {r['label']:8} {r['recommendation']:9} "
                  f"confidence {r['confidence']}")
        print("\nWhy the top candidate scored this way:\n")
        print(format_report(ranking[0]))
    print(f"\nFull reports saved in {OUT_DIR}/")


if __name__ == "__main__":
    main()
