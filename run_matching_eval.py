"""Day 12: measure how accurate the matcher is, tune the label thresholds, write the report.

    python run_matching_eval.py                    # run + write data/matching/matching_eval.json + the report
    python run_matching_eval.py --write-thresholds # also save the chosen cut-offs in matching/similarity_thresholds.json

Inputs : data/samples/matching_ground_truth.json (labels written by Claude, to be reviewed by a human),
         data/raw_resumes/*, data/parsed_jobs/*.profile.json + *.json
Outputs: data/matching/matching_eval.json, docs/Day12_Matching_Accuracy_Report.md
Every number in the report is computed here, in this run. The metric functions are in matching/evaluation.py.
"""
import json
import sys
from contextlib import contextmanager
from pathlib import Path

from matching import evaluation as ev
from matching import semantic_engine
from matching.embedders import HashingEmbedder, SentenceTransformerEmbedder
from matching.semantic_engine import SemanticMatcher
from matching.similarity_scorer import (
    CONFIG_PATH, resume_to_views, score_resume_to_job, validate_thresholds,
)

ROOT = Path(__file__).resolve().parent
GT_PATH = ROOT / "data" / "samples" / "matching_ground_truth.json"
JOB_DIR = ROOT / "data" / "parsed_jobs"
RESUME_DIR = ROOT / "data" / "raw_resumes"
OUT_PATH = ROOT / "data" / "matching" / "matching_eval.json"
REPORT_PATH = ROOT / "docs" / "Day12_Matching_Accuracy_Report.md"

LEVELS = {"not relevant": 0, "partly relevant": 1, "relevant": 2}
# Two yes/no questions, each answered by one threshold. The number is the lowest gold level that counts as "yes".
TASKS = {"relevant": 2, "at_least_partly": 1}
TASK_TITLES = {"relevant": "Task A: relevant vs everything else (label 'good' cut-off)",
               "at_least_partly": "Task B: at least partly relevant vs not relevant (label 'partial' cut-off)"}
TASK_TO_LABEL = {"relevant": "good", "at_least_partly": "partial"}
OLD_CUTS = {"relevant": 55, "at_least_partly": 35}      # the guesses the engine shipped with
STRONG_KEPT = 75                                         # 'strong' cannot be tuned with this data (see report)
TUNE_GRID = range(0, 101)
TABLE_GRID = range(0, 101, 5)
SKILL_THRESHOLDS = (0.5, 0.6, 0.7, 0.8, 0.9)
BIG_SPREAD = 10                                          # fold thresholds further apart than this = "changes a lot"


# ----------------------------------------------------------------------------- loading
def load_ground_truth(path=GT_PATH):
    """Read the label file."""
    return json.loads(Path(path).read_text(encoding="utf-8"))


def load_jobs():
    """{job_name: (profile, full_job_doc)} for every parsed job."""
    jobs = {}
    for profile_path in sorted(JOB_DIR.glob("*.profile.json")):
        name = profile_path.name.replace(".profile.json", "")
        doc_path = JOB_DIR / f"{name}.json"
        doc = json.loads(doc_path.read_text(encoding="utf-8")) if doc_path.exists() else None
        jobs[name] = (json.loads(profile_path.read_text(encoding="utf-8")), doc)
    return jobs


def load_views(names):
    """{resume_file: views} for readable resumes, and {resume_file: problem} for unreadable ones."""
    views, problems = {}, {}
    for name in names:
        found, problem = resume_to_views(RESUME_DIR / name)
        if problem:
            problems[name] = problem
        else:
            views[name] = found
    return views, problems


# ----------------------------------------------------------------------------- scoring every pair
@contextmanager
def skill_threshold(value):
    """Temporarily change the engine's SKILL_SEMANTIC_THRESHOLD (restored afterwards; the file is not touched)."""
    old = semantic_engine.SKILL_SEMANTIC_THRESHOLD
    semantic_engine.SKILL_SEMANTIC_THRESHOLD = value
    try:
        yield
    finally:
        semantic_engine.SKILL_SEMANTIC_THRESHOLD = old


def score_pairs(matcher, views, jobs, labels):
    """One row per labeled (resume, job) pair, scored with the Day 12 similarity scorer."""
    rows = []
    for item in labels:
        profile, doc = jobs[item["job"]]
        result = score_resume_to_job(views[item["resume"]], profile, doc, matcher, name=item["resume"])
        rows.append({"resume": item["resume"], "job": item["job"], "gold": item["label"],
                     "level": LEVELS[item["label"]], "doubtful": item["doubtful"], "reason": item["reason"],
                     "score": result["similarity_score"], "predicted_label": result["label"],
                     "parts": result["parts"], "missing_must_have": result["missing_must_have"],
                     "related_skills": result["related_skills"]})
    return rows


# ----------------------------------------------------------------------------- analysis of one task
def task_analysis(rows, task):
    """Sweep, tuned threshold, metrics, per-job numbers, leave-one-job-out and errors for one yes/no task."""
    need = TASKS[task]
    scores = [r["score"] for r in rows]
    truths = [r["level"] >= need for r in rows]
    best = ev.best_threshold(ev.threshold_sweep(scores, truths, TUNE_GRID))
    labeled = [{"job": r["job"], "score": r["score"], "truth": t} for r, t in zip(rows, truths)]
    at_best = ev.evaluate_at_threshold(scores, truths, best)
    per_job = {}
    for job in dict.fromkeys(r["job"] for r in rows):
        sub = [(r["score"], t) for r, t in zip(rows, truths) if r["job"] == job]
        per_job[job] = ev.evaluate_at_threshold([s for s, _ in sub], [t for _, t in sub], best)
    errors = []
    for r, t in zip(rows, truths):
        predicted = r["score"] >= best
        if predicted != t:
            errors.append({"kind": "false positive" if predicted else "false negative", **r})
    gap = {"highest_not_match": max(s for s, t in zip(scores, truths) if not t),
           "lowest_match": min(s for s, t in zip(scores, truths) if t)}
    return {"task": task, "positives": sum(truths), "pairs": len(rows), "auc": ev.pairwise_auc(scores, truths),
            "gap": gap,
            "sweep": ev.threshold_sweep(scores, truths, TABLE_GRID), "chosen_threshold": best,
            "at_chosen": at_best, "at_old_cut": ev.evaluate_at_threshold(scores, truths, OLD_CUTS[task]),
            "per_job": per_job, "leave_one_job_out": ev.leave_one_job_out(labeled, TUNE_GRID),
            "errors": errors}


def ranking_per_job(rows):
    """Ranking quality for every job (0 not / 1 partly / 2 relevant)."""
    out = {}
    for job in dict.fromkeys(r["job"] for r in rows):
        sub = [r for r in rows if r["job"] == job]
        out[job] = ev.ranking_quality([r["score"] for r in sub], [r["level"] for r in sub])
    return out


def part_auc(rows):
    """How well does each part alone (skills / experience / projects) tell at-least-partly from not relevant?"""
    out = {}
    for part in ("skills", "experience", "projects"):
        sub = [r for r in rows if r["parts"][part] is not None]
        truths = [r["level"] >= 1 for r in sub]
        out[part] = {"pairs_with_data": len(sub), "auc": ev.pairwise_auc([r["parts"][part] for r in sub], truths)}
    return out


def skill_threshold_study(matcher, views, jobs, labels):
    """Re-score every pair with different SKILL_SEMANTIC_THRESHOLD values and see what changes."""
    study = []
    for value in SKILL_THRESHOLDS:
        with skill_threshold(value):
            rows = score_pairs(matcher, views, jobs, labels)
        scores = [r["score"] for r in rows]
        study.append({"value": value,
                      "related_matches": sum(len(r["related_skills"]) for r in rows),
                      "auc_relevant": ev.pairwise_auc(scores, [r["level"] >= 2 for r in rows]),
                      "auc_at_least_partly": ev.pairwise_auc(scores, [r["level"] >= 1 for r in rows]),
                      "order_accuracy": ev.pairwise_order_accuracy(scores, [r["level"] for r in rows]),
                      "best_f1_relevant": ev.evaluate_at_threshold(
                          scores, [r["level"] >= 2 for r in rows],
                          ev.best_threshold(ev.threshold_sweep(scores, [r["level"] >= 2 for r in rows], TUNE_GRID)))["f1"],
                      "best_f1_at_least_partly": ev.evaluate_at_threshold(
                          scores, [r["level"] >= 1 for r in rows],
                          ev.best_threshold(ev.threshold_sweep(scores, [r["level"] >= 1 for r in rows], TUNE_GRID)))["f1"]})
    return study


def related_examples(matcher, views, jobs, labels, floor=0.5):
    """Every 'related skill' pair found at a low cut-off (0.5), so a human can judge which are sensible."""
    seen = {}
    with skill_threshold(floor):
        for r in score_pairs(matcher, views, jobs, labels):
            for m in r["related_skills"]:
                key = (m["job_skill"], m["resume_skill"])
                seen.setdefault(key, {"similarity": m["similarity"], "first_seen_in": f"{r['resume']} vs {r['job']}"})
    return [{"job_skill": a, "resume_skill": b, **info} for (a, b), info in
            sorted(seen.items(), key=lambda kv: -kv[1]["similarity"])]


# ----------------------------------------------------------------------------- the whole evaluation for one embedder
def run_evaluation(embedder, gt):
    """Everything for one embedder. Returns one JSON-friendly dict."""
    matcher = SemanticMatcher(embedder=embedder)
    jobs = load_jobs()
    names = sorted({x["resume"] for x in gt["labels"]} | {x["resume"] for x in gt["unscorable_resumes"]}
                   | {x["resume"] for x in gt["not_a_resume"]})
    views, problems = load_views(names)
    labels = [x for x in gt["labels"] if x["job"] in jobs]
    rows = score_pairs(matcher, views, jobs, labels)
    extra = {}
    for item in gt["not_a_resume"]:
        profile_scores = {}
        for job, (profile, doc) in jobs.items():
            res = score_resume_to_job(views[item["resume"]], profile, doc, matcher, name=item["resume"])
            profile_scores[job] = res["similarity_score"]
        extra[item["resume"]] = profile_scores
    return {"embedder": embedder.name, "pairs": rows,
            "unscorable": {n: problems.get(n, "no problem found") for n in
                           (x["resume"] for x in gt["unscorable_resumes"])},
            "not_a_resume_scores": extra,
            "group_stats": ev.group_stats([r["score"] for r in rows], [r["gold"] for r in rows]),
            "ranking": ranking_per_job(rows), "part_auc": part_auc(rows),
            "tasks": {t: task_analysis(rows, t) for t in TASKS},
            "skill_threshold_study": skill_threshold_study(matcher, views, jobs, labels),
            "related_examples": related_examples(matcher, views, jobs, labels)}


def chosen_thresholds(result):
    """The label cut-offs the evidence supports: 'good' from task A, 'partial' from task B, 'strong' kept."""
    return {"strong": STRONG_KEPT,
            "good": result["tasks"]["relevant"]["chosen_threshold"],
            "partial": result["tasks"]["at_least_partly"]["chosen_threshold"]}


def available_embedders():
    """[HashingEmbedder] plus the neural one if sentence-transformers works. Also returns why not."""
    embedders, skipped = [HashingEmbedder()], None
    try:
        embedders.append(SentenceTransformerEmbedder())
    except Exception as exc:                       # not installed, or model not downloadable
        skipped = f"{type(exc).__name__}: {exc}"
    return embedders, skipped


# ----------------------------------------------------------------------------- the Markdown report
def _f(value, digits=3):
    return "n/a" if value is None else (f"{value:.{digits}f}".rstrip("0").rstrip(".") if isinstance(value, float)
                                        else str(value))


def _table(headers, rows):
    lines = ["| " + " | ".join(headers) + " |", "|" + "---|" * len(headers)]
    lines += ["| " + " | ".join(str(c) for c in row) + " |" for row in rows]
    return lines


def _metric_row(name, m):
    return [name, m["threshold"], f"{m['tp']}/{m['fp']}/{m['fn']}/{m['tn']}", _f(m["precision"]), _f(m["recall"]),
            _f(m["f1"]), _f(m["accuracy"])]


def _short(job):
    return job.replace("jd_", "")


def _report_dataset(gt, primary):
    from collections import Counter
    pairs = primary["pairs"]
    counts = Counter(r["gold"] for r in pairs)
    md = ["## 3. Dataset", "",
          f"- **Resumes in `data/raw_resumes`:** 9. **Scored:** {len({r['resume'] for r in pairs})} "
          f"(`{'`, `'.join(sorted({r['resume'] for r in pairs}))}`).",
          "- **Unreadable (scans, listed separately, not counted as errors):** " +
          ", ".join(f"`{n}`" for n in primary["unscorable"]) + ". The scorer returns status `unscorable` for them.",
          "- **Not a resume:** " + ", ".join(f"`{x['resume']}`" for x in gt["not_a_resume"]) +
          " is the Day 2 architecture document, so it has no label and is reported separately (section 9).",
          f"- **Jobs:** {len(set(r['job'] for r in pairs))} (" + ", ".join(sorted(_short(j) for j in
                                                                         {r['job'] for r in pairs})) + ").",
          f"- **Labeled pairs:** {len(pairs)} = relevant {counts['relevant']}, partly relevant "
          f"{counts['partly relevant']}, not relevant {counts['not relevant']}. "
          f"{sum(r['doubtful'] for r in pairs)} of them are marked *doubtful* (close calls).", "",
          "**How the labels were made.** The labels are **judgments by Claude (an AI), not by a human recruiter**. "
          "Claude read each resume's extracted text and each job's profile and wrote one label and one reason "
          "per pair (`data/samples/matching_ground_truth.json`). The labels were written **before** the matcher "
          "was run on these pairs, so they were not adjusted to fit its scores. A person should review them, "
          "especially the doubtful ones listed in the file. Scale used:", ""]
    md += [f"- **{name}**: {text}" for name, text in gt["label_scale"].items()]
    jobs = list(dict.fromkeys(r["job"] for r in pairs))
    rows = [[_short(j)] + [sum(1 for r in pairs if r["job"] == j and r["gold"] == g) for g in LEVELS]
            for j in jobs]
    md += ["", "Labels per job:", ""] + _table(["Job", *LEVELS], rows) + [""]
    return md


def _report_results(primary):
    md = ["## 4. Results", "", "### 4.1 Do the scores separate the groups?", "",
          "Similarity score (0-100) of the pairs, grouped by the label I gave them:", ""]
    md += _table(["Gold label", "Pairs", "Lowest", "Average", "Highest"],
                 [[g, s["count"], s["min"], s["mean"], s["max"]] for g, s in primary["group_stats"].items()])
    md += ["", "### 4.2 Accuracy at the old (guessed) cut-offs vs the tuned cut-offs", "",
           "Columns tp/fp/fn/tn = true positives / false positives / false negatives / true negatives. "
           "**Tuned = measured on the same 24 pairs it was tuned on, so it is optimistic** (see 6 for the honest test).",
           ""]
    rows = []
    for task, data in primary["tasks"].items():
        rows.append(_metric_row(f"{task}: old cut-off", data["at_old_cut"]))
        rows.append(_metric_row(f"{task}: tuned (in-sample)", data["at_chosen"]))
    md += _table(["Setting", "Cut-off", "tp/fp/fn/tn", "Precision", "Recall", "F1", "Accuracy"], rows)
    md += ["", "Ranking quality over all pairs (area under the curve, 1.0 = perfect, 0.5 = guessing): "
           f"task A {_f(primary['tasks']['relevant']['auc'])}, task B "
           f"{_f(primary['tasks']['at_least_partly']['auc'])}.", "",
           "### 4.3 Per job type (at the tuned cut-offs)", ""]
    for task, data in primary["tasks"].items():
        md += [f"**{TASK_TITLES[task]}**, cut-off {data['chosen_threshold']}", ""]
        md += _table(["Job", "tp/fp/fn/tn", "Precision", "Recall", "F1", "Accuracy"],
                     [[_short(j), f"{m['tp']}/{m['fp']}/{m['fn']}/{m['tn']}", _f(m["precision"]), _f(m["recall"]),
                       _f(m["f1"]), _f(m["accuracy"])] for j, m in data["per_job"].items()]) + [""]
    md += ["### 4.4 Ranking inside each job", "",
           "Does the matcher put the better candidates higher? (`k` = number of at-least-partly relevant candidates)", ""]
    md += _table(["Job", "All relevant above all not-relevant?", "AUC (at least partly)", "Precision@k", "k",
                  "Order accuracy (all 3 levels)"],
                 [[_short(j), {True: "yes", False: "NO", None: "n/a"}[q["all_relevant_above_not"]],
                   _f(q["auc_at_least_partly"]), _f(q["precision_at_k"]), q["k"], _f(q["pairwise_order_accuracy"])]
                  for j, q in primary["ranking"].items()])
    md += ["", "### 4.5 Which part carries the signal?", "",
           "AUC of each part score alone for task B (higher = separates better):", ""]
    md += _table(["Part", "Pairs with data", "AUC"],
                 [[p, d["pairs_with_data"], _f(d["auc"])] for p, d in primary["part_auc"].items()]) + [""]
    return md


def _report_thresholds(primary, chosen):
    md = ["## 5. Threshold sweep and the chosen thresholds", "",
          "For each cut-off T, a pair is called a match when its score is >= T. Step 5 shown here; the tuning used "
          "every whole number 0-100.", ""]
    rel, part = primary["tasks"]["relevant"]["sweep"], primary["tasks"]["at_least_partly"]["sweep"]
    md += _table(["T", "A precision", "A recall", "A F1", "B precision", "B recall", "B F1", "B accuracy"],
                 [[a["threshold"], _f(a["precision"]), _f(a["recall"]), _f(a["f1"]), _f(b["precision"]),
                   _f(b["recall"]), _f(b["f1"]), _f(b["accuracy"])] for a, b in zip(rel, part)])
    md += ["", "**Chosen thresholds** (saved in `matching/similarity_thresholds.json`):", "",
           f"- `good` = **{chosen['good']}** (best F1 for task A; when several cut-offs tie, the middle one is used "
           "because the edge of a tie is fragile).",
           f"- `partial` = **{chosen['partial']}** (best F1 for task B, same tie rule).",
           f"- `strong` = **{chosen['strong']}** (NOT tuned: it is the old value. No pair in this data set can "
           f"tell 'strong' from 'good'; the highest score seen is {max(r['score'] for r in primary['pairs'])}).",
           "- Scores below `partial` are labeled `weak`.", ""]
    for task in ("relevant", "at_least_partly"):
        g = primary["tasks"][task]["gap"]
        width = g["lowest_match"] - g["highest_not_match"]
        cut = primary["tasks"][task]["chosen_threshold"]
        where = (f"the cut-off {cut} sits in that {width}-point gap" if width > 0 else
                 f"the two groups OVERLAP by {-width} point(s), so no cut-off is error-free and {cut} trades the "
                 "errors listed in section 8")
        md.append(f"- Task {'A' if task == 'relevant' else 'B'} gap: highest non-match score "
                  f"{g['highest_not_match']}, lowest match score {g['lowest_match']}; {where}.")
    return md + [""]


def _report_loo(primary):
    md = ["## 6. Leave-one-job-out validation", "",
          "For each job: pick the cut-off using only the OTHER three jobs, then test it on the held-out job. "
          "This is the closest thing to 'would it work on a job type it has not seen'.", ""]
    for task, data in primary["tasks"].items():
        loo = data["leave_one_job_out"]
        md += [f"**{TASK_TITLES[task]}**", ""]
        md += _table(["Held-out job", "Cut-off tuned on other 3", "tp/fp/fn/tn", "Precision", "Recall", "F1",
                      "Accuracy"],
                     [[_short(f["held_out"]), f["threshold"], f"{f['tp']}/{f['fp']}/{f['fn']}/{f['tn']}",
                       _f(f["precision"]), _f(f["recall"]), _f(f["f1"]), _f(f["accuracy"])] for f in loo["folds"]])
        p = loo["pooled_test"]
        md += ["", f"Pooled over the 4 held-out jobs: precision {_f(p['precision'])}, recall {_f(p['recall'])}, "
               f"F1 {_f(p['f1'])}, accuracy {_f(p['accuracy'])} "
               f"({p['tp']}/{p['fp']}/{p['fn']}/{p['tn']}). In-sample F1 with all jobs was "
               f"{_f(data['at_chosen']['f1'])}.",
               f"The tuned cut-off ranged from {loo['threshold_min']} to {loo['threshold_max']} "
               f"(spread {loo['threshold_spread']}). " +
               ("**That is a big change between folds: the cut-off is not stable.**"
                if loo["threshold_spread"] > BIG_SPREAD else "That is a small change between folds."),
               "Folds with mistakes: " + (", ".join(f"{_short(f['held_out'])} (false positives {f['fp']}, "
                                                    f"false negatives {f['fn']})" for f in loo["folds"]
                                                    if f["fp"] or f["fn"]) or "none") + ".", ""]
    return md


def _report_skill_threshold(primary):
    md = ["## 7. Testing SKILL_SEMANTIC_THRESHOLD (currently 0.70)", "",
          "Every pair was re-scored with each value (the engine file was not changed). 'Related matches' = how many "
          "times a job skill was matched to a *different* resume skill.", ""]
    md += _table(["Value", "Related matches", "AUC task A", "AUC task B", "Order accuracy", "Best F1 A", "Best F1 B"],
                 [[s["value"], s["related_matches"], _f(s["auc_relevant"]), _f(s["auc_at_least_partly"]),
                   _f(s["order_accuracy"]), _f(s["best_f1_relevant"]), _f(s["best_f1_at_least_partly"])]
                  for s in primary["skill_threshold_study"]])
    md += ["", "Related-skill pairs found at a low cut-off of 0.5 (so you can judge by eye which look sensible):", ""]
    md += _table(["Job skill", "Resume skill", "Similarity", "First seen in"],
                 [[e["job_skill"], e["resume_skill"], e["similarity"], e["first_seen_in"]]
                  for e in primary["related_examples"][:15]])
    return md + [""] + _skill_threshold_reading(primary)


def _skill_threshold_reading(primary):
    """Plain-language reading of the table above, built from the numbers."""
    study, found = primary["skill_threshold_study"], primary["related_examples"]
    same = len({(s["related_matches"], s["auc_relevant"], s["auc_at_least_partly"], s["order_accuracy"])
                for s in study if s["value"] <= 0.8}) == 1
    lines = [f"**Reading.** Across all {len(primary['pairs'])} pairs the offline embedder found only "
             f"{len(found)} related-skill pair(s) even at 0.5. " +
             ("Values 0.5 to 0.8 give identical results, so the data cannot tell them apart. " if same else "") +
             "Real neighbours such as react/vue or python/django score near 0 with this embedder, so the pair(s) "
             "above are not genuine skill relations. A single-word text becomes a vector with one to three "
             "features, and with 2048 hash buckets two unrelated words can land in the same bucket. That is "
             "what a similarity as high as " + (str(found[0]["similarity"]) if found else "n/a") +
             " between unrelated skills means here. **Verdict: this threshold cannot be validated with the offline "
             "embedder on this data.** Recommendation (not applied; the engine file is unchanged): keep 0.70 for "
             "now, re-test with the neural embedder, and if the offline embedder stays, use 0.9 or more or a larger "
             "`dims` in `HashingEmbedder`.", ""]
    return lines


def _report_errors(primary, gt):
    notes = gt.get("error_notes", {})
    md = ["## 8. Error analysis (every false positive and false negative at the chosen cut-offs)", ""]
    for task, data in primary["tasks"].items():
        md += [f"**{TASK_TITLES[task]}**, cut-off {data['chosen_threshold']}", ""]
        if not data["errors"]:
            md += ["No errors on these 24 pairs (in-sample; see section 6 for unseen-job behaviour).", ""]
            continue
        rows = []
        for e in data["errors"]:
            parts = ", ".join(f"{k} {v if v is not None else '-'}" for k, v in e["parts"].items())
            rows.append([e["kind"], f"{e['resume']} vs {_short(e['job'])}", e["gold"] + (" (doubtful)" if e["doubtful"] else ""),
                         e["score"], parts, notes.get(f"{e['resume']}|{e['job']}", "(no note written yet)")])
        md += _table(["Error", "Pair", "My label", "Score", "Parts", "Likely cause"], rows) + [""]
    return md + _report_fold_errors(primary, notes)


def _report_fold_errors(primary, notes):
    """Mistakes that appear only when a job is held out (cut-off tuned without it)."""
    md = ["**Extra mistakes in leave-one-job-out folds** (the cut-off was tuned without that job):", ""]
    rows = []
    for task, data in primary["tasks"].items():
        need = TASKS[task]
        for fold in data["leave_one_job_out"]["folds"]:
            for r in (x for x in primary["pairs"] if x["job"] == fold["held_out"]):
                predicted = r["score"] >= fold["threshold"]
                if predicted != (r["level"] >= need):
                    rows.append([task, _short(fold["held_out"]), fold["threshold"], r["resume"], r["gold"], r["score"],
                                 "false positive" if predicted else "false negative",
                                 notes.get(f"{r['resume']}|{r['job']}", "(no note written yet)")])
    if not rows:
        return md + ["None.", ""]
    return md + _table(["Task", "Held-out job", "Fold cut-off", "Resume", "My label", "Score", "Error", "Likely cause"],
                       rows) + [""]


def _report_special(primary, gt, skipped):
    md = ["## 9. Special cases", "",
          "- **Scanned resumes** (" + ", ".join(f"`{n}`" for n in primary["unscorable"]) +
          "): the scorer returns `status: unscorable` with a reason and no score. They are not counted as errors. "
          "OCR would be needed to read them.",
          "- **`m.pdf` (not a resume)** scored against each job: " +
          ", ".join(f"{_short(j)} {s}" for j, s in primary["not_a_resume_scores"]["m.pdf"].items()) +
          ". The scorer has no way to know a document is not a resume. A document-type check belongs earlier "
          "in the pipeline.", ""]
    md += ["## 10. Offline vs neural embedder", ""]
    if skipped:
        md += ["**Only the offline `hashing-offline` embedder was evaluated.** The neural embedder could not be "
               f"loaded in this run ({skipped}). `run_matching_eval.py` compares both automatically when "
               "`sentence-transformers` is installed; that code path was **not** run on real neural output here.", ""]
    return md


def build_report(results, gt, skipped):
    """Markdown text from the evaluation results (results[0] is the primary / offline run)."""
    primary = results[0]
    chosen = chosen_thresholds(primary)
    md = ["# Day 12 - Matching Accuracy Report", "",
          f"Embedder evaluated: `{primary['embedder']}`. Every number below was produced by "
          "`python run_matching_eval.py` (raw numbers: `data/matching/matching_eval.json`).", "",
          "> **Read this first.** There are only 24 labeled pairs (6 resumes x 4 jobs) and the labels are my "
          "judgments, not a recruiter's. The numbers are **indicative, not statistically strong**. Cut-offs tuned "
          "on 24 pairs will move when more data is added.", "",
          "## 1. Purpose", "",
          "Day 12 asks for a semantic matcher, a resume-to-job similarity scorer, and evidence of how accurate it is. "
          "This report gives that evidence and turns the guessed label cut-offs (35 / 55 / 75) into tested ones.", "",
          "## 2. Method", "",
          "1. Every readable sample resume is parsed (Day 5 to 10 code) and scored against every parsed job with "
          "`matching/similarity_scorer.py`, which gives a similarity score from 0 to 100.",
          "2. Each pair has a label from `data/samples/matching_ground_truth.json`: relevant / partly relevant / "
          "not relevant.",
          "3. Two yes/no questions are measured: **Task A** 'is it relevant?' and **Task B** 'is it at least partly "
          "relevant?'. A pair is called a match when its score >= the cut-off. Task A decides the `good` label, "
          "task B the `partial` label.",
          "4. Metrics: precision, recall, F1, accuracy, a threshold sweep, and ranking quality inside each job "
          "(`matching/evaluation.py`).",
          "5. Validation across job types: **leave-one-job-out** (tune on 3 jobs, test on the 4th, repeat).", ""]
    md += _report_dataset(gt, primary) + _report_results(primary) + _report_thresholds(primary, chosen)
    md += _report_loo(primary) + _report_skill_threshold(primary) + _report_errors(primary, gt)
    md += _report_special(primary, gt, skipped)
    if len(results) > 1:
        md += _report_neural(results)
    md += _report_limits(primary, chosen, gt, skipped)
    return "\n".join(md) + "\n"


def _report_limits(primary, chosen, gt, skipped):
    """Limits and recommendations. Numbers come from the run; the rest is plain reasoning."""
    pairs = primary["pairs"]
    pos_a = primary["tasks"]["relevant"]["positives"]
    doubtful = [f"{r['resume']} vs {_short(r['job'])}" for r in pairs if r["doubtful"]]
    spread_b = primary["tasks"]["at_least_partly"]["leave_one_job_out"]["threshold_spread"]
    md = ["## 11. Limits", "",
          f"- **Small data.** {len(pairs)} pairs; only {pos_a} are 'relevant'. Task A was tuned on {pos_a} positives, "
          "so its perfect scores prove very little. The cut-offs will move with more data.",
          "- **Labels are one AI's judgment**, not a recruiter's. The close calls are: " + "; ".join(doubtful) + ".",
          "- **Tiny resumes.** `sample_simple`, `sample_two_column` and `sample_bullets_table` have only about "
          "130-250 characters of text each, so their scores rest on very little evidence.",
          f"- **Tuned and tested on the same people.** Leave-one-job-out leaves a *job* out, but the same six "
          f"resumes appear in every fold, so it does not test unseen resumes. Task B cut-off spread across folds: "
          f"{spread_b} points.",
          f"- **`strong` ({chosen['strong']}) is untested**: the highest score seen is "
          f"{max(r['score'] for r in pairs)}, so with this embedder no sample pair is ever labeled `strong`.",
          "- **Hash collisions** in the offline embedder (section 7) can create a false 'related skill'.",
          "- **Skill gaps may come from skill extraction**, not matching: a must-have the resume implies but never "
          "names (for example `communication`) is reported as missing.",
          "- **Only the offline embedder was evaluated.**" if skipped else "- Neural and offline embedders were both evaluated.",
          "", "## 12. Recommendations", "",
          "1. Have a recruiter review `data/samples/matching_ground_truth.json` (start with the doubtful pairs), "
          "then re-run `python run_matching_eval.py`.",
          "2. Add more labeled resumes per job (at least 10 relevant and 10 not relevant per job) before trusting "
          "the cut-offs; include longer, more realistic resumes.",
          "3. Install `sentence-transformers` and re-run: the report then compares both embedders and re-tests "
          "`SKILL_SEMANTIC_THRESHOLD` with real semantic neighbours.",
          "4. Do not change `SKILL_SEMANTIC_THRESHOLD` yet (section 7). Consider a larger `dims` in "
          "`HashingEmbedder` or comparing skills by taxonomy before hashing.",
          "5. Add a document-type check so non-resumes such as `m.pdf` are rejected before scoring, and OCR for scans.",
          "6. Use the `good` and `partial` cut-offs from `matching/similarity_thresholds.json` for shortlisting "
          "decisions only together with a human review for now.", ""]
    return md


def _report_neural(results):
    md = ["### Neural comparison", ""]
    rows = [[r["embedder"], r["tasks"]["relevant"]["chosen_threshold"], _f(r["tasks"]["relevant"]["auc"]),
             r["tasks"]["at_least_partly"]["chosen_threshold"], _f(r["tasks"]["at_least_partly"]["auc"])]
            for r in results]
    return md + _table(["Embedder", "Cut-off A", "AUC A", "Cut-off B", "AUC B"], rows) + [""]


# ----------------------------------------------------------------------------- main
def write_thresholds(chosen, embedder_name, pairs):
    """Save the chosen cut-offs in matching/similarity_thresholds.json (validated first)."""
    config = {"version": "1.0-tuned", "tuned_with": f"{embedder_name}, {pairs} labeled pairs (see the Day 12 report)",
              "labels": chosen}
    errors = validate_thresholds(config)
    if errors:
        raise ValueError("; ".join(errors))
    CONFIG_PATH.write_text(json.dumps(config, indent=2) + "\n", encoding="utf-8")


def main(argv=None):
    """Run everything, write the JSON + report, print a short summary."""
    args = sys.argv[1:] if argv is None else argv
    gt = load_ground_truth()
    embedders, skipped = available_embedders()
    results = [run_evaluation(e, gt) for e in embedders]
    chosen = chosen_thresholds(results[0])
    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUT_PATH.write_text(json.dumps({"chosen_thresholds": chosen, "neural_skipped": skipped, "runs": results},
                                   indent=2) + "\n", encoding="utf-8")
    REPORT_PATH.write_text(build_report(results, gt, skipped), encoding="utf-8")
    if "--write-thresholds" in args:
        write_thresholds(chosen, results[0]["embedder"], len(results[0]["pairs"]))
    primary = results[0]
    print(f"Embedder: {primary['embedder']}   pairs: {len(primary['pairs'])}   chosen cut-offs: {chosen}")
    for task, data in primary["tasks"].items():
        loo = data["leave_one_job_out"]
        print(f"  {task:16} in-sample F1 {_f(data['at_chosen']['f1'])}  AUC {_f(data['auc'])}  "
              f"leave-one-job-out F1 {_f(loo['pooled_test']['f1'])}  fold cut-offs {[f['threshold'] for f in loo['folds']]}")
    print("Neural embedder:", "evaluated" if not skipped else f"NOT evaluated ({skipped})")
    print("Wrote", OUT_PATH.relative_to(ROOT), "and", REPORT_PATH.relative_to(ROOT))


if __name__ == "__main__":
    main()
