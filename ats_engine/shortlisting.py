"""Day 14: Shortlisting automation module.

Input : the ranked output of ranking_engine.build_ranking() (candidates already sorted best first).
Output: for every candidate a decision, plain-English reasons and a recruiter action.

Three zones come from the overall score (numbers live in ats_engine/shortlist_config.json, not here):

    score >= shortlist_score                    SHORTLISTED   "Invite to the next round"
    reject_score <= score < shortlist_score     REVIEW        "Recruiter checks the resume"
    score < reject_score                        REJECTED      "Send rejection"

Safety rules run AFTER the zone, because a number alone must never decide about a person:

    1. low confidence (too little data)     -> always REVIEW (never auto-shortlist, never auto-reject)
    2. too many missing must-have skills    -> a high score is not enough, REVIEW
    3. auto_reject switched off             -> the reject zone becomes REVIEW
    4. max_shortlist (capacity)             -> extra qualified candidates become WAITLIST;
                                               candidates tied with the last place stay together

Threshold order (later wins): default < role override < the job's own ats_cutoff_score < command line.
The job cutoff and the command-line cutoff move the shortlist line and keep the review-zone width.

Pipeline position:
    ranking_engine.build_ranking() -> build_shortlist() -> JSON / CSV / text for the recruiter

Try it:
    python -m ats_engine.shortlisting data/parsed_jobs/jd_mern_developer.profile.json data/raw_resumes
"""
import argparse
import csv
import io
import json
import sys
from pathlib import Path

from ats_engine.ranking_engine import top_candidates
from utils.logger import get_logger

log = get_logger(__name__)

CONFIG_PATH = Path(__file__).with_name("shortlist_config.json")
SHORTLISTED, WAITLIST, REVIEW, REJECTED = "SHORTLISTED", "WAITLIST", "REVIEW", "REJECTED"
ACTIONS = {SHORTLISTED: "Invite to the next round", WAITLIST: "Keep on hold; invite if a place opens",
           REVIEW: "Recruiter checks the resume", REJECTED: "Send rejection"}
ZONE_ORDER = (SHORTLISTED, WAITLIST, REVIEW, REJECTED)
NUMBER_KEYS = ("shortlist_score", "reject_score")


# ------------------------------------------------------------------ step 1: thresholds

def check_thresholds(values, where="thresholds"):
    """Return a list of problems with one set of thresholds (empty list = fine)."""
    problems = []
    for key in NUMBER_KEYS:
        value = values.get(key)
        if isinstance(value, bool) or not isinstance(value, (int, float)) or not 0 <= value <= 100:
            problems.append(f"{where}: '{key}' must be a number from 0 to 100 (got {value!r}).")
    if not problems and values["reject_score"] > values["shortlist_score"]:
        problems.append(f"{where}: reject_score ({values['reject_score']}) must not be above "
                        f"shortlist_score ({values['shortlist_score']}).")
    limit = values.get("max_missing_must_have")
    if isinstance(limit, bool) or not isinstance(limit, int) or limit < 0:
        problems.append(f"{where}: 'max_missing_must_have' must be a whole number, 0 or more (got {limit!r}).")
    cap = values.get("max_shortlist")
    if cap is not None and (isinstance(cap, bool) or not isinstance(cap, int) or cap < 1):
        problems.append(f"{where}: 'max_shortlist' must be null or a whole number, 1 or more (got {cap!r}).")
    if not isinstance(values.get("auto_reject"), bool):
        problems.append(f"{where}: 'auto_reject' must be true or false (got {values.get('auto_reject')!r}).")
    return problems


def validate_config(config):
    """Return a list of problems with the whole config file (empty list = fine)."""
    if not isinstance(config.get("default"), dict):
        return ["config: needs a 'default' section."]
    problems = check_thresholds(config["default"], "default")
    for role, override in (config.get("roles") or {}).items():
        if not isinstance(override, dict):
            problems.append(f"roles.{role}: must be an object.")
            continue
        problems += check_thresholds({**config["default"], **override}, f"roles.{role}")
    return problems


def load_config(path=None):
    """Read and check the config file. Raises ValueError listing every problem."""
    path = Path(path or CONFIG_PATH)
    config = json.loads(path.read_text(encoding="utf-8"))
    problems = validate_config(config)
    if problems:
        raise ValueError("Bad shortlist config " + str(path.name) + ":\n  " + "\n  ".join(problems))
    return config


def resolve_thresholds(job=None, config=None, overrides=None):
    """Final thresholds for one job. Returns the values plus `sources`: where each line came from."""
    config = config or load_config()
    job = job or {}
    values = dict(config["default"])
    sources = ["default config"]
    role = str(job.get("normalized_title") or "").lower()
    if role in {key.lower() for key in config.get("roles", {})}:
        override = next(v for k, v in config["roles"].items() if k.lower() == role)
        values.update(override)
        sources.append(f"role override '{role}'")
    width = values["shortlist_score"] - values["reject_score"]   # review-zone width stays the same

    def move_line(cutoff, label):
        values["shortlist_score"] = cutoff
        values["reject_score"] = max(0, cutoff - width)
        sources.append(label)

    if job.get("ats_cutoff_score"):
        move_line(job["ats_cutoff_score"], f"job ats_cutoff_score {job['ats_cutoff_score']}")
    overrides = {k: v for k, v in (overrides or {}).items() if v is not None}
    if "shortlist_score" in overrides:
        move_line(overrides.pop("shortlist_score"), "command line cutoff")
    if overrides:
        values.update(overrides)
        sources.append("command line: " + ", ".join(sorted(overrides)))
    problems = check_thresholds(values, "final thresholds")
    if problems:
        raise ValueError("\n".join(problems))
    values["sources"] = sources
    return values


# ------------------------------------------------------------------ step 2: zone and safety rules

def _n(number):
    """Show 60.0 as 60 and 72.5 as 72.5."""
    return f"{number:g}"


def zone_for(score, thresholds):
    """The zone from the score alone: SHORTLISTED, REVIEW or REJECTED."""
    if score >= thresholds["shortlist_score"]:
        return SHORTLISTED
    if score >= thresholds["reject_score"]:
        return REVIEW
    return REJECTED


def zone_reason(score, zone, thresholds):
    """One plain sentence about why the score put the candidate in this zone."""
    top, low = _n(thresholds["shortlist_score"]), _n(thresholds["reject_score"])
    if zone == SHORTLISTED:
        return f"Score {_n(score)} reaches the shortlist score of {top}."
    if zone == REVIEW:
        return f"Score {_n(score)} is in the review zone ({low} up to {top})."
    return f"Score {_n(score)} is below the reject line of {low}."


def decide(row, thresholds):
    """Zone + safety rules 1-3 for one ranked row. Returns (decision, reasons, rules_applied)."""
    score = row["overall_score"]
    decision = zone_for(score, thresholds)
    reasons, rules = [zone_reason(score, decision, thresholds)], []

    if row.get("confidence") == "low" and decision != REVIEW:
        decision = REVIEW
        rules.append("low_confidence")
        reasons.append("Confidence is low (too little data, for example a scanned file), so a person "
                       "must decide instead of the score.")
    elif row.get("confidence") == "low":
        rules.append("low_confidence")
        reasons.append("Confidence is low (too little data): check the resume by hand.")

    missing = row.get("missing_must_have") or []
    limit = thresholds["max_missing_must_have"]
    if decision == SHORTLISTED and len(missing) > limit:
        decision = REVIEW
        rules.append("missing_must_have")
        reasons.append(f"{len(missing)} must-have skills are missing (limit {limit}): "
                       + ", ".join(missing) + ". A high score is not enough.")
    elif missing:
        reasons.append("Missing must-have skills: " + ", ".join(missing) + ".")

    if decision == REJECTED and not thresholds["auto_reject"]:
        decision = REVIEW
        rules.append("auto_reject_off")
        reasons.append("Auto-reject is switched off, so a recruiter checks this resume first.")
    return decision, reasons, rules


def apply_capacity(candidates, max_shortlist):
    """Rule 4: keep at most max_shortlist shortlisted; tied candidates stay together; the rest wait."""
    if max_shortlist is None:
        return 0
    shortlisted = [c for c in candidates if c["decision"] == SHORTLISTED]
    if len(shortlisted) <= max_shortlist:
        return 0
    last_rank = shortlisted[max_shortlist - 1]["rank"]      # a tie with the last place is kept
    moved = 0
    for c in shortlisted:
        if c["rank"] > last_rank:
            c["decision"], c["action"] = WAITLIST, ACTIONS[WAITLIST]
            c["safety_rules"].append("capacity")
            c["reasons"].append(f"All {max_shortlist} places are taken by higher-ranked candidates; "
                                "this candidate is on the waitlist.")
            moved += 1
    return moved


# ------------------------------------------------------------------ step 3: the whole shortlist

def make_candidate(row, thresholds):
    """One output row: the ranking facts a recruiter needs plus the decision and the reasons."""
    decision, reasons, rules = decide(row, thresholds)
    return {
        "position": row["position"], "rank": row["rank"], "tied": row["tied"],
        "candidate_id": row["candidate_id"], "overall_score": row["overall_score"], "label": row.get("label"),
        "decision": decision, "action": ACTIONS[decision], "reasons": reasons, "safety_rules": rules,
        "day13_recommendation": row.get("recommendation"), "confidence": row.get("confidence"),
        "missing_must_have": list(row.get("missing_must_have") or []),
    }


def build_warnings(ranking, candidates, thresholds, moved):
    """Honest warnings: say what happened, do not hide it."""
    warnings = [w for w in ranking.get("warnings", []) if w.startswith("Could not score")]
    ids = [str(c["candidate_id"]) for c in candidates]
    dupes = sorted({i for i in ids if ids.count(i) > 1})
    if dupes:
        warnings.append("Duplicate candidate ids: " + ", ".join(dupes) + " (the same person may have applied twice).")
    cutoff = thresholds["shortlist_score"]
    reached = [c for c in candidates if c["overall_score"] >= cutoff]
    held = [c for c in reached if c["decision"] == REVIEW]
    if candidates and not reached:
        best = max(c["overall_score"] for c in candidates)
        warnings.append(f"Nobody reached the shortlist score of {_n(cutoff)} (best score {_n(best)}). "
                        "Check the cutoff or the job requirements.")
    if held:
        warnings.append(f"{len(held)} candidate(s) reached the shortlist score but a safety rule sent them to "
                        "review: " + ", ".join(str(c["candidate_id"]) for c in held) + ".")
    if moved:
        warnings.append(f"{moved} qualified candidate(s) are on the waitlist because max_shortlist is "
                        f"{thresholds['max_shortlist']}.")
    off = [c for c in candidates if "auto_reject_off" in c["safety_rules"]]
    if off:
        warnings.append(f"Auto-reject is OFF: {len(off)} candidate(s) below the reject line were sent to review.")
    low = [c for c in candidates if c["confidence"] == "low"]
    if low:
        warnings.append(f"{len(low)} candidate(s) have low confidence (too little data); a person must check: "
                        + ", ".join(str(c["candidate_id"]) for c in low) + ".")
    return warnings


def build_shortlist(ranking, job=None, config=None, overrides=None, top_n=5):
    """Ranked output -> decisions, top list, warnings. `overrides` holds command-line threshold values."""
    thresholds = resolve_thresholds(job, config, overrides)
    rows = ranking.get("ranking", [])
    candidates = [make_candidate(row, thresholds) for row in rows]
    moved = apply_capacity(candidates, thresholds["max_shortlist"])
    counts = {zone: sum(1 for c in candidates if c["decision"] == zone) for zone in ZONE_ORDER}
    counts["total"] = len(candidates)
    top = top_candidates([c for c in candidates if c["decision"] == SHORTLISTED], top_n)
    warnings = build_warnings(ranking, candidates, thresholds, moved)
    if not candidates:
        warnings.append("No candidates to shortlist.")
    log.info("Shortlist for %s: %s", ranking.get("job_id"), counts)
    return {
        "job_id": ranking.get("job_id"), "job_title": ranking.get("job_title"),
        "thresholds": thresholds, "counts": counts, "candidates": candidates, "top_n": top_n,
        "top_candidates": [{"position": c["position"], "rank": c["rank"], "candidate_id": c["candidate_id"],
                            "overall_score": c["overall_score"]} for c in top],
        "warnings": warnings,
    }


# ------------------------------------------------------------------ step 4: recruiter-friendly outputs

def format_shortlist_text(output):
    """Plain-text summary: counts first, then each zone with the reasons."""
    t, c = output["thresholds"], output["counts"]
    lines = [f"Shortlist for: {output['job_title']} ({output['job_id']})",
             f"Shortlist at {_n(t['shortlist_score'])}+, review {_n(t['reject_score'])} to "
             f"{_n(t['shortlist_score'])}, reject below {_n(t['reject_score'])}"
             + ("" if t["auto_reject"] else " (auto-reject OFF)"),
             f"Candidates: {c['total']}   Shortlisted: {c[SHORTLISTED]}   Waitlist: {c[WAITLIST]}   "
             f"Review: {c[REVIEW]}   Rejected: {c[REJECTED]}"]
    for zone in ZONE_ORDER:
        group = [x for x in output["candidates"] if x["decision"] == zone]
        if not group:
            continue
        lines += ["", f"{zone} ({len(group)}) - {ACTIONS[zone]}", "-" * 60]
        for x in group:
            tie = "T-" if x["tied"] else ""
            lines.append(f"  {tie}{x['rank']}. {x['candidate_id']}  score {_n(x['overall_score'])}")
            lines += [f"       - {reason}" for reason in x["reasons"]]
    if output["top_candidates"]:
        names = ", ".join(f"{t['position']}. {t['candidate_id']}" for t in output["top_candidates"])
        lines += ["", f"Top shortlisted: {names}"]
    lines += [f"Warning: {w}" for w in output["warnings"]]
    return "\n".join(lines)


CSV_COLUMNS = ["position", "rank", "candidate_id", "overall_score", "decision", "action", "confidence",
               "missing_must_have", "reasons"]


def to_csv(output):
    """CSV text for Excel / Google Sheets: one line per candidate, best first."""
    buffer = io.StringIO()
    writer = csv.writer(buffer, lineterminator="\n")
    writer.writerow(CSV_COLUMNS)
    for c in output["candidates"]:
        writer.writerow([c["position"], c["rank"], c["candidate_id"], c["overall_score"], c["decision"],
                         c["action"], c["confidence"], "; ".join(c["missing_must_have"]), " ".join(c["reasons"])])
    return buffer.getvalue()


def save_shortlist(output, out_dir):
    """Write <job_id>.shortlist.json / .csv / .txt into out_dir and return the three paths."""
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    stem = f"{output['job_id'] or 'unknown_job'}.shortlist"
    paths = {ext: out_dir / f"{stem}.{ext}" for ext in ("json", "csv", "txt")}
    paths["json"].write_text(json.dumps(output, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    paths["csv"].write_text(to_csv(output), encoding="utf-8")
    paths["txt"].write_text(format_shortlist_text(output) + "\n", encoding="utf-8")
    return paths


# ------------------------------------------------------------------ step 5: command line

def main(argv=None):
    parser = argparse.ArgumentParser(description="Rank resumes for one job and sort them into zones.")
    parser.add_argument("job_profile", help="a Day 6 *.profile.json file")
    parser.add_argument("resumes", nargs="*", help="resume files and/or folders (not needed with --ranking)")
    parser.add_argument("--ranking", help="a saved <job_id>.ranking.json: skips scoring")
    parser.add_argument("--cutoff", type=float, help="shortlist score (moves the line, keeps the review width)")
    parser.add_argument("--reject-below", type=float, help="reject line")
    parser.add_argument("--max-shortlist", type=int, help="most candidates to shortlist")
    parser.add_argument("--top", type=int, default=5, help="size of the top list (default 5)")
    parser.add_argument("--no-auto-reject", action="store_true", help="send the reject zone to review instead")
    parser.add_argument("--config", help="another shortlist config file")
    parser.add_argument("--out", default="data/shortlists", help="folder for the saved files")
    args = parser.parse_args(argv)

    from ats_engine.score_generator import load_job
    job, job_doc = load_job(args.job_profile)
    if args.ranking:
        ranking = json.loads(Path(args.ranking).read_text(encoding="utf-8"))
    elif args.resumes:
        from ats_engine.ranking_engine import collect_resumes, rank_resume_files
        files = collect_resumes(args.resumes)
        if not files:
            print("No PDF/DOCX resumes found.")
            return 1
        ranking = rank_resume_files(files, job, job_doc, top_n=args.top)
    else:
        parser.error("give resume files/folders or --ranking")
    overrides = {"shortlist_score": args.cutoff, "reject_score": args.reject_below,
                 "max_shortlist": args.max_shortlist, "auto_reject": False if args.no_auto_reject else None}
    try:
        output = build_shortlist(ranking, job, load_config(args.config), overrides, args.top)
    except ValueError as error:
        print(error)
        return 2
    paths = save_shortlist(output, args.out)
    print(format_shortlist_text(output))
    print("\nSaved:", ", ".join(str(p) for p in paths.values()))
    return 0


if __name__ == "__main__":
    sys.exit(main())
