"""Measures how accurate the section classifier is (Day 8).

Compares the classifier's section for every line with the hand-made answer key in
data/labeled_resumes/, and writes a Markdown report plus a JSON file with the numbers.

    from parsers.section_eval import evaluate, write_report
    results = evaluate()
    write_report(results)

Metrics (all counted per line):
    accuracy            correct lines / all lines
    content accuracy    same, but ignoring lines the rules recognise as headings
                        (headings are easy; this number shows how well the NLP part works)
    precision / recall / F1 per section
"""
import json
from collections import Counter, defaultdict
from pathlib import Path

from parsers.section_classifier import classify_lines, detect_heading
from parsers.section_taxonomy import SECTIONS

ROOT = Path(__file__).resolve().parent.parent
LABELED_DIR = ROOT / "data" / "labeled_resumes"
REPORT_PATH = ROOT / "docs" / "Day8_Section_Detection_Accuracy_Report.md"
RESULTS_PATH = LABELED_DIR / "evaluation_results.json"
SPLITS = ("real", "dev", "holdout")


def load_labeled(path):
    """Read a *.labeled.txt file. Returns (resume_text, [gold_label_for_each_nonblank_line])."""
    text_lines, gold = [], []
    for row in Path(path).read_text(encoding="utf-8").split("\n"):
        if "\t" in row:
            label, text = row.split("\t", 1)
            gold.append(label)
            text_lines.append(text)
        else:
            text_lines.append(row)
    while text_lines and not text_lines[-1].strip():
        text_lines.pop()
    return "\n".join(text_lines), gold


def load_manifest(labeled_dir=LABELED_DIR):
    """Return the list of samples from manifest.json."""
    return json.loads((Path(labeled_dir) / "manifest.json").read_text(encoding="utf-8"))


def _prf(tp, fp, fn):
    precision = tp / (tp + fp) if tp + fp else 0.0
    recall = tp / (tp + fn) if tp + fn else 0.0
    f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
    return round(precision, 3), round(recall, 3), round(f1, 3)


def evaluate(mode="hybrid", splits=SPLITS, labeled_dir=LABELED_DIR):
    """Run the classifier on every labeled sample in the given splits and score it."""
    samples, errors = [], []
    confusion = defaultdict(Counter)
    total = correct = content_total = content_correct = 0
    for item in load_manifest(labeled_dir):
        if item["split"] not in splits:
            continue
        text, gold = load_labeled(Path(labeled_dir) / f"{item['name']}.labeled.txt")
        tags = classify_lines(text, mode)
        if len(tags) != len(gold):
            raise ValueError(f"{item['name']}: {len(tags)} tagged lines but {len(gold)} labels")
        ok = 0
        for tag, expected in zip(tags, gold):
            hit = tag.section == expected
            confusion[expected][tag.section] += 1
            ok += hit
            is_heading = detect_heading(tag.text) is not None
            if not is_heading:
                content_total += 1
                content_correct += hit
            if not hit:
                errors.append({"sample": item["name"], "line_no": tag.line_no, "expected": expected,
                               "predicted": tag.section, "method": tag.method,
                               "confidence": tag.confidence, "text": tag.text.strip()[:90]})
        total += len(gold)
        correct += ok
        samples.append({**item, "correct": ok, "total": len(gold), "accuracy": round(ok / len(gold), 3)})

    per_section = {}
    for label in SECTIONS:
        tp = confusion[label][label]
        fn = sum(confusion[label].values()) - tp
        fp = sum(confusion[other][label] for other in SECTIONS if other != label)
        precision, recall, f1 = _prf(tp, fp, fn)
        per_section[label] = {"precision": precision, "recall": recall, "f1": f1,
                              "support": sum(confusion[label].values())}
    present = [v["f1"] for v in per_section.values() if v["support"]]

    by_category = defaultdict(lambda: [0, 0])
    for sample in samples:
        by_category[sample["category"]][0] += sample["correct"]
        by_category[sample["category"]][1] += sample["total"]

    return {
        "mode": mode, "splits": list(splits), "samples": samples,
        "lines_total": total, "lines_correct": correct,
        "accuracy": round(correct / total, 3) if total else 0.0,
        "content_lines_total": content_total, "content_lines_correct": content_correct,
        "content_accuracy": round(content_correct / content_total, 3) if content_total else 0.0,
        "macro_f1": round(sum(present) / len(present), 3) if present else 0.0,
        "per_section": per_section,
        "by_category": {k: {"correct": v[0], "total": v[1], "accuracy": round(v[0] / v[1], 3)}
                        for k, v in sorted(by_category.items())},
        "confusion": {k: dict(v) for k, v in confusion.items()},
        "errors": errors,
    }


def _pct(value):
    return f"{value * 100:.1f}%"


def build_report(runs):
    """Build the Markdown report text from {name: evaluate()-result} (see write_report)."""
    hybrid_all = runs["hybrid_all"]
    md = ["# Day 8 - Section Detection Accuracy Report", "",
          "How well does the Resume Section Classifier (`parsers/section_classifier.py`) put each line "
          "of a resume into the right section? Every number below is **per line**, measured against "
          "answer keys labeled by hand (`data/labeled_resumes/`).", "",
          "## 1. Headline results", "",
          "| Test set | Resumes | Lines | Rules only | Hybrid (rules + NLP) |",
          "|---|---|---|---|---|"]
    for key, title in (("all", "All samples"), ("real", "Real resumes (Day 5 output)"),
                       ("dev", "Hand-written, dev (used for tuning)"),
                       ("holdout", "Hand-written, holdout (never tuned on)")):
        rule, hyb = runs[f"rules_{key}"], runs[f"hybrid_{key}"]
        md.append(f"| {title} | {len(hyb['samples'])} | {hyb['lines_total']} | {_pct(rule['accuracy'])} | "
                  f"**{_pct(hyb['accuracy'])}** |")
    holdout = runs["hybrid_holdout"]
    md += ["",
           "**Read the holdout row as the honest estimate.** The dev and real rows are the samples the rules "
           "were tuned on, so they are optimistic. The holdout resumes were written before tuning and "
           "were not used to adjust any weight.", "",
           f"On the holdout set, content lines only (lines that are *not* headings) are "
           f"{_pct(holdout['content_accuracy'])} correct, because heading lines are easy and push the "
           "plain accuracy up. Over all samples the content-line accuracy is "
           f"{_pct(hybrid_all['content_accuracy'])}; the macro-F1 (average of the per-section F1 scores) is "
           f"{hybrid_all['macro_f1']}.", "",
           "## 2. Accuracy by resume layout (hybrid, all samples)", "",
           "| Layout | Correct / Lines | Accuracy | Rules only |", "|---|---|---|---|"]
    rule_cat = runs["rules_all"]["by_category"]
    for category, stat in hybrid_all["by_category"].items():
        md.append(f"| {category} | {stat['correct']} / {stat['total']} | {_pct(stat['accuracy'])} | "
                  f"{_pct(rule_cat[category]['accuracy'])} |")
    md += ["", "The rules-only column is the baseline (headings found, everything before the first heading "
           "is called *header*). It collapses on resumes with no headings, which is exactly what the "
           "NLP layer is for.", "",
           "## 3. Per-section quality (hybrid, all samples)", "",
           "| Section | Precision | Recall | F1 | Lines |", "|---|---|---|---|---|"]
    for label in SECTIONS:
        stat = hybrid_all["per_section"][label]
        md.append(f"| {label} | {stat['precision']} | {stat['recall']} | {stat['f1']} | {stat['support']} |")
    md += ["", "## 4. Confusion matrix (hybrid, all samples)", "",
           "Rows = the correct section, columns = what the classifier said. Only the off-diagonal cells "
           "are mistakes.", "", "| correct \\ predicted | " + " | ".join(SECTIONS) + " |",
           "|---|" + "---|" * len(SECTIONS)]
    for expected in SECTIONS:
        row = hybrid_all["confusion"].get(expected, {})
        if row:
            md.append(f"| **{expected}** | " + " | ".join(str(row.get(p, 0)) for p in SECTIONS) + " |")
    md += ["", "## 5. Every mistake (hybrid, all samples)", ""]
    if hybrid_all["errors"]:
        md += ["| Sample | Line | Correct | Predicted | Why (method, confidence) | Text |", "|---|---|---|---|---|---|"]
        for e in hybrid_all["errors"]:
            text = e["text"].replace("|", "\\|")
            md.append(f"| {e['sample']} | {e['line_no']} | {e['expected']} | {e['predicted']} | "
                      f"{e['method']}, {e['confidence']} | {text} |")
    else:
        md.append("None.")
    md += ["", "## 6. What the mistakes teach us", "",
           "- **Context can override a clear line.** An obvious certification line sitting between two skills "
           "lines can be pulled into *skills* by the smoothing step. A stronger fix is a sequence model "
           "(Viterbi / CRF) that also learns typical section order.",
           "- **Missing vocabulary.** `ACCA Qualification` and `Languages: Arabic, English, French` fail because "
           "the keyword lists in `parsers/section_taxonomy.py` do not know them. Adding words fixes this "
           "without touching code.",
           "- **Project titles are ambiguous without a heading.** `Online Quiz Portal - developed with React...` "
           "looks like a job line (verb + tools). With no heading, only neighbours can help.",
           "- **Small test set.** About 190 lines in 20 resumes. Treat the percentages as a guide, not a guarantee; "
           "add more labeled resumes (real, anonymised) before trusting them.",
           "- **Not covered yet:** two-column PDFs whose columns interleave line by line, headings embedded inside "
           "images, and non-English resumes.", "",
           "## 7. How the labeled samples were made", "",
           "- `real` resumes: the Day 5 extractor output, labeled by hand using line ranges "
           "(`tests/labeled_sample_builder.py`).",
           "- `dev` / `holdout`: short hand-written resumes covering caps, numbered, inline, typo, combined, "
           "table, two-column and no-heading layouts.",
           "- Convention: a heading line belongs to its own section; a combined heading such as "
           "`Skills & Certifications` is labeled with the first section named.",
           "- One answer-key typo (two certification lines labeled *skills* in `hold_combined_heading`) was "
           "corrected after the first holdout run; no classifier change was made for it.",
           "- Regenerate this report: `python run_section_eval.py`", ""]
    return "\n".join(md)


def run_all(labeled_dir=LABELED_DIR):
    """Evaluate both modes on every split combination used in the report."""
    runs = {}
    for mode in ("rules", "hybrid"):
        runs[f"{mode}_all"] = evaluate(mode, SPLITS, labeled_dir)
        for split in SPLITS:
            runs[f"{mode}_{split}"] = evaluate(mode, (split,), labeled_dir)
    return runs


def write_report(runs, report_path=REPORT_PATH, results_path=RESULTS_PATH):
    """Save the Markdown report and the JSON numbers. Returns the report path."""
    report_path, results_path = Path(report_path), Path(results_path)
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(build_report(runs), encoding="utf-8")
    summary = {name: {k: v for k, v in run.items() if k not in ("errors", "confusion")}
               for name, run in runs.items()}
    summary["hybrid_all_errors"] = runs["hybrid_all"]["errors"]
    results_path.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    return report_path
