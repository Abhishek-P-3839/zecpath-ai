"""Day 14: Auto-ranking engine.

Input : the Day 13 ATS reports (one per candidate) for ONE job.
Output: one ranked, recruiter-friendly list (JSON + CSV + a printable table).

How candidates are ordered (best first). Each rule only matters if the rules above it are equal:

    1. overall_score          higher is better
    2. skill_match score      must-have skills matter most to recruiters
    3. experience score       then relevant experience
    4. data_completeness      a score built on more real data is more trustworthy
    5. candidate_id           alphabetical, so the order is the same every run

Two numbers describe a place in the list:
    position   1, 2, 3, 4 ...   always unique (the order a recruiter reads the list)
    rank       1, 2, 2, 4 ...   candidates with exactly the SAME overall score share a rank ("T-2")

Pipeline position:
    resumes -> Day 13 generate_score() -> reports -> rank_reports() -> build_ranking() -> table / CSV / JSON

Try it:
    python -m ats_engine.ranking_engine data/parsed_jobs/jd_mern_developer.profile.json data/raw_resumes --top 3

This module only ORDERS candidates. Shortlist thresholds and auto-reject / review zones come next
(Day 14, shortlisting module) and will use the ranking built here.
"""
import argparse
import csv
import io
import json
import statistics
import sys
from collections import Counter
from pathlib import Path

from ats_engine.weights import COMPONENTS
from utils.logger import get_logger

log = get_logger(__name__)

SHORT = {"skill_match": "Skills", "experience_relevance": "Experience",
         "education_alignment": "Education", "semantic_similarity": "Text match"}
REQUIRED_KEYS = ("candidate_id", "job_id", "overall_score", "data_completeness")


# ------------------------------------------------------------------ step 1: check and sort

def check_reports(reports):
    """Stop early, with a clear message, if the input is not a list of same-job ATS reports."""
    for number, report in enumerate(reports, start=1):
        missing = [key for key in REQUIRED_KEYS if key not in report]
        if missing:
            raise ValueError(f"Report #{number} is not a Day 13 ATS report (missing: {', '.join(missing)}).")
    jobs = sorted({str(report["job_id"]) for report in reports})
    if len(jobs) > 1:
        raise ValueError("Reports are for different jobs (" + ", ".join(jobs) + "). "
                         "Scores of different jobs cannot be compared: use rank_by_job().")


def component_score(report, name):
    """The 0-100 score of one scoring part, or None if that part could not be scored."""
    return (report.get("components", {}).get(name) or {}).get("score")


def _best_first(value):
    """Sort helper: a bigger number sorts earlier, a missing number (None) sorts last."""
    return 1 if value is None else -value


def sort_key(report):
    """The ordering rules from the top of this file, as a tuple Python can sort."""
    return (_best_first(report["overall_score"]),
            _best_first(component_score(report, "skill_match")),
            _best_first(component_score(report, "experience_relevance")),
            _best_first(report["data_completeness"]),
            str(report["candidate_id"]))


# ------------------------------------------------------------------ step 2: ranked rows

def make_row(report, position, rank):
    """One line of the ranked list: only what a recruiter needs, not the whole report."""
    skill_details = (report.get("components", {}).get("skill_match") or {}).get("details", {})
    return {
        "position": position,
        "rank": rank,
        "tied": False,                       # filled in by rank_reports()
        "candidate_id": report["candidate_id"],
        "overall_score": report["overall_score"],
        "label": report.get("label"),
        "recommendation": report.get("recommendation"),   # Day 13's advice: shortlist / review / reject
        "confidence": report.get("confidence"),
        "data_completeness": report["data_completeness"],
        "percentile": None,                  # filled in by rank_reports()
        "scores": {name: component_score(report, name) for name in COMPONENTS},
        "strengths": list(report.get("strengths", []))[:3],
        "gaps": list(report.get("gaps", []))[:3],
        "missing_must_have": list(skill_details.get("missing_must_have", [])),
        "flags": list(report.get("flags", [])),
        "needs_manual_check": report.get("confidence") == "low",
    }


def rank_reports(reports):
    """Sort the reports (best first) and return one row per candidate with position, rank, percentile."""
    check_reports(reports)
    rows = []
    for position, report in enumerate(sorted(reports, key=sort_key), start=1):
        same_as_previous = rows and rows[-1]["overall_score"] == report["overall_score"]
        rank = rows[-1]["rank"] if same_as_previous else position
        rows.append(make_row(report, position, rank))

    total = len(rows)
    shared = Counter(row["rank"] for row in rows)
    for row in rows:
        row["tied"] = shared[row["rank"]] > 1
        # 100 = best candidate, 0 = lowest rank
        row["percentile"] = 100 if total == 1 else round(100 * (total - row["rank"]) / (total - 1))
    return rows


def rank_by_job(reports):
    """Reports for several jobs -> {job_id: ranked rows}. Each job is ranked on its own."""
    grouped = {}
    for report in reports:
        grouped.setdefault(report.get("job_id"), []).append(report)
    return {job_id: rank_reports(group) for job_id, group in grouped.items()}


# ------------------------------------------------------------------ step 3: top lists and summary

def top_candidates(rows, n=5, min_score=None, include_ties=True):
    """The top-N list. Optionally only candidates with at least `min_score`.

    include_ties=True: everyone who shares the rank of the n-th candidate is included too
    (it would be unfair to drop one of two candidates with the same score), so the list can be longer than n.
    """
    chosen = [row for row in rows if min_score is None or row["overall_score"] >= min_score]
    if n is None or len(chosen) <= n:
        return chosen
    if include_ties:
        last_rank = chosen[n - 1]["rank"]
        return [row for row in chosen if row["rank"] <= last_rank]
    return chosen[:n]


def score_summary(rows):
    """Highest, lowest, average and median overall score (None if there are no candidates)."""
    if not rows:
        return None
    scores = [row["overall_score"] for row in rows]
    return {"highest": max(scores), "lowest": min(scores),
            "average": round(statistics.mean(scores), 2), "median": round(statistics.median(scores), 2)}


def build_ranking(reports, top_n=5, min_score=None, extra_warnings=None):
    """The ranked candidate output: summary + full ranking + top list + warnings. Ready to save as JSON."""
    warnings = list(extra_warnings or [])
    if not reports:
        return {"job_id": None, "job_title": None, "total_candidates": 0, "score_summary": None,
                "ranking": [], "top_n": top_n, "min_score": min_score, "top_candidates": [],
                "warnings": warnings + ["No candidates to rank."]}

    rows = rank_reports(reports)
    ids = [row["candidate_id"] for row in rows]
    duplicates = sorted({i for i in ids if ids.count(i) > 1}, key=str)
    if duplicates:
        warnings.append("Duplicate candidate ids: " + ", ".join(map(str, duplicates))
                        + " (the same person may have applied twice).")
    manual = [str(row["candidate_id"]) for row in rows if row["needs_manual_check"]]
    if manual:
        warnings.append(f"{len(manual)} candidate(s) have low confidence (too little data): "
                        + ", ".join(manual) + ". Check their resumes by hand.")

    top = top_candidates(rows, top_n, min_score)
    log.info("Ranked %d candidate(s) for %s; top list has %d", len(rows), reports[0]["job_id"], len(top))
    return {
        "job_id": reports[0]["job_id"],
        "job_title": reports[0].get("job_title"),
        "total_candidates": len(rows),
        "score_summary": score_summary(rows),
        "ranking": rows,
        "top_n": top_n,
        "min_score": min_score,
        "top_candidates": [{"position": r["position"], "rank": r["rank"], "candidate_id": r["candidate_id"],
                            "overall_score": r["overall_score"], "label": r["label"]} for r in top],
        "warnings": warnings,
    }


# ------------------------------------------------------------------ step 4: recruiter-friendly outputs

def _cell(value):
    return "-" if value is None else f"{value:.0f}"


def format_ranking_table(output):
    """A plain-text table a recruiter can read in the terminal or paste into an email."""
    lines = [f"Ranking for: {output['job_title']} ({output['job_id']})   candidates: {output['total_candidates']}"]
    summary = output["score_summary"]
    if summary:
        lines.append(f"Scores: highest {summary['highest']}, lowest {summary['lowest']}, "
                     f"average {summary['average']}, median {summary['median']}")
    lines += ["", f"{'Rank':<5} {'Candidate':<22} {'Score':>6}  {'Fit':<8} {'Skill':>5} {'Exp':>4} {'Edu':>4} "
                  f"{'Text':>4}  {'Conf':<6} Advice", "-" * 92]
    for row in output["ranking"]:
        rank = ("T-" if row["tied"] else "") + str(row["rank"])
        s = row["scores"]
        lines.append(f"{rank:<5} {str(row['candidate_id'])[:22]:<22} {row['overall_score']:>6.1f}  "
                     f"{str(row['label']):<8} {_cell(s['skill_match']):>5} {_cell(s['experience_relevance']):>4} "
                     f"{_cell(s['education_alignment']):>4} {_cell(s['semantic_similarity']):>4}  "
                     f"{str(row['confidence']):<6} {row['recommendation']}")
    if output["top_candidates"]:
        names = ", ".join(f"{t['position']}. {t['candidate_id']}" for t in output["top_candidates"])
        lines += ["", f"Top {output['top_n']}: {names}"]
    notes = [f"  #{r['position']} {r['candidate_id']}: " + "; ".join(
        (["missing must-have: " + ", ".join(r["missing_must_have"])] if r["missing_must_have"] else [])
        + (["low confidence, check manually"] if r["needs_manual_check"] else []))
        for r in output["ranking"] if r["missing_must_have"] or r["needs_manual_check"]]
    if notes:
        lines += ["", "Notes:"] + notes
    lines += [f"Warning: {w}" for w in output["warnings"]]
    return "\n".join(lines)


CSV_COLUMNS = ["position", "rank", "candidate_id", "overall_score", "label", "recommendation", "confidence",
               "data_completeness", *COMPONENTS, "missing_must_have", "top_strength", "top_gap", "needs_manual_check"]


def to_csv(output):
    """CSV text (opens in Excel / Google Sheets). One line per candidate, best first."""
    buffer = io.StringIO()
    writer = csv.writer(buffer, lineterminator="\n")
    writer.writerow(CSV_COLUMNS)
    for r in output["ranking"]:
        writer.writerow([r["position"], r["rank"], r["candidate_id"], r["overall_score"], r["label"],
                         r["recommendation"], r["confidence"], r["data_completeness"],
                         *("" if r["scores"][name] is None else r["scores"][name] for name in COMPONENTS),
                         "; ".join(r["missing_must_have"]), r["strengths"][0] if r["strengths"] else "",
                         r["gaps"][0] if r["gaps"] else "", r["needs_manual_check"]])
    return buffer.getvalue()


def save_ranking(output, out_dir):
    """Write <job_id>.ranking.json / .csv / .txt into out_dir and return the three paths."""
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    stem = f"{output['job_id'] or 'unknown_job'}.ranking"
    paths = {ext: out_dir / f"{stem}.{ext}" for ext in ("json", "csv", "txt")}
    paths["json"].write_text(json.dumps(output, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    paths["csv"].write_text(to_csv(output), encoding="utf-8")
    paths["txt"].write_text(format_ranking_table(output) + "\n", encoding="utf-8")
    return paths


# ------------------------------------------------------------------ step 5: from resume files

def collect_resumes(paths):
    """Folders -> every PDF/DOCX inside; files stay as they are."""
    from extraction.extractor import SUPPORTED
    files = []
    for path in map(Path, paths):
        files += sorted(f for f in path.iterdir() if f.suffix.lower() in SUPPORTED) if path.is_dir() else [path]
    return files


def rank_resume_files(files, job, job_doc=None, today=None, top_n=5, min_score=None):
    """Score every resume file against the job (Day 13) and rank them. A broken file is skipped, not fatal."""
    from ats_engine.score_generator import generate_score
    from ats_engine.scoring_engine import ATSScoringEngine
    engine = ATSScoringEngine(today=today)      # built once, used for every resume
    reports, problems = [], []
    for file in files:
        try:
            reports.append(generate_score(file, job, job_doc, engine=engine, today=today))
        except Exception as error:               # one bad resume must not stop the whole ranking
            log.warning("Skipped %s: %s", file, error)
            problems.append(f"Could not score {Path(file).name}: {error}")
    return build_ranking(reports, top_n, min_score, extra_warnings=problems)


def main(argv=None):
    parser = argparse.ArgumentParser(description="Rank resumes for one job.")
    parser.add_argument("job_profile", help="a Day 6 *.profile.json file")
    parser.add_argument("resumes", nargs="+", help="resume files and/or folders (PDF, DOCX)")
    parser.add_argument("--top", type=int, default=5, help="size of the top list (default 5)")
    parser.add_argument("--min-score", type=float, default=None, help="only list candidates at or above this score")
    parser.add_argument("--out", default="data/rankings", help="folder for the saved files")
    args = parser.parse_args(argv)

    from ats_engine.score_generator import load_job
    job, job_doc = load_job(args.job_profile)
    files = collect_resumes(args.resumes)
    if not files:
        print("No PDF/DOCX resumes found.")
        return 1
    output = rank_resume_files(files, job, job_doc, top_n=args.top, min_score=args.min_score)
    paths = save_ranking(output, args.out)
    print(format_ranking_table(output))
    print("\nSaved:", ", ".join(str(p) for p in paths.values()))
    return 0


if __name__ == "__main__":
    sys.exit(main())
