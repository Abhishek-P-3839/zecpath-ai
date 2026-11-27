"""Day 12 / Deliverable 3: metric functions for the matching accuracy report.

Pure functions only (no printing, no files, no embeddings): numbers in, numbers out. That keeps them easy to
test by hand. `run_matching_eval.py` does the real work (scoring resumes, reading labels, writing reports).

The question these answer: "if we say 'match' when the similarity score is >= T, how often are we right?"

    scores   list of similarity scores (0-100), one per (resume, job) pair
    truths   list of True/False, same order. True = a human-style judgment says the pair is a match

Terms:  tp = said match, really a match      fp = said match, really not      (false positive)
        fn = said no,   really a match  (false negative)      tn = said no, really not
        precision = tp / (tp + fp)    recall = tp / (tp + fn)    f1 = 2*p*r / (p + r)
A metric that cannot be computed (division by zero) is None, never a made-up 0.
"""
from itertools import combinations


# ----------------------------------------------------------------------------- basic counts and metrics
def confusion_matrix(truths, predictions):
    """Count tp / fp / fn / tn from two lists of booleans."""
    if len(truths) != len(predictions):
        raise ValueError("truths and predictions must have the same length")
    cm = {"tp": 0, "fp": 0, "fn": 0, "tn": 0}
    for truth, pred in zip(truths, predictions):
        cm[("t" if pred == truth else "f") + ("p" if pred else "n")] += 1
    return cm


def _ratio(top, bottom):
    return round(top / bottom, 3) if bottom else None


def precision(cm):
    """tp / (tp + fp); None if nothing was predicted as a match."""
    return _ratio(cm["tp"], cm["tp"] + cm["fp"])


def recall(cm):
    """tp / (tp + fn); None if there are no real matches."""
    return _ratio(cm["tp"], cm["tp"] + cm["fn"])


def f1_score(cm):
    """Harmonic mean of precision and recall; None if either cannot be computed."""
    p, r = precision(cm), recall(cm)
    if p is None or r is None:
        return None
    return round(2 * p * r / (p + r), 3) if p + r else 0.0


def accuracy(cm):
    """(tp + tn) / all pairs; None if there are no pairs."""
    return _ratio(cm["tp"] + cm["tn"], sum(cm.values()))


def metrics_from_cm(cm):
    """All four metrics plus the counts, in one dict."""
    return {**cm, "precision": precision(cm), "recall": recall(cm), "f1": f1_score(cm), "accuracy": accuracy(cm)}


# ----------------------------------------------------------------------------- thresholds
def evaluate_at_threshold(scores, truths, threshold):
    """Say 'match' when score >= threshold, and measure it."""
    cm = confusion_matrix(truths, [s >= threshold for s in scores])
    return {"threshold": threshold, **metrics_from_cm(cm)}


def threshold_sweep(scores, truths, thresholds):
    """evaluate_at_threshold for every threshold in the list."""
    return [evaluate_at_threshold(scores, truths, t) for t in thresholds]


def best_threshold(sweep):
    """Pick the threshold with the best F1 (accuracy breaks ties).

    Many thresholds often tie (any cut between two neighbouring scores gives the same answers). We take the
    MIDDLE of the tied ones, because the edge of a plateau is fragile. Returns None if the sweep is empty.
    """
    if not sweep:
        return None
    key = lambda row: (row["f1"] or 0.0, row["accuracy"] or 0.0)
    top = max(key(row) for row in sweep)
    tied = sorted(row["threshold"] for row in sweep if key(row) == top)
    return tied[(len(tied) - 1) // 2]


# ----------------------------------------------------------------------------- ranking quality
def pairwise_auc(scores, truths):
    """Chance that a random real match scores higher than a random non-match (ties count half).

    1.0 = every match above every non-match, 0.5 = no better than guessing. None if one group is empty.
    """
    pos = [s for s, t in zip(scores, truths) if t]
    neg = [s for s, t in zip(scores, truths) if not t]
    if not pos or not neg:
        return None
    wins = sum(1.0 if p > n else 0.5 if p == n else 0.0 for p in pos for n in neg)
    return round(wins / (len(pos) * len(neg)), 3)


def precision_at_k(scores, truths, k):
    """Of the k highest-scoring items, the share that are real matches. Ties keep the input order."""
    if k <= 0 or not scores:
        return None
    order = sorted(range(len(scores)), key=lambda i: -scores[i])[:k]
    return round(sum(1 for i in order if truths[i]) / len(order), 3)


def pairwise_order_accuracy(scores, levels):
    """Among pairs whose true levels differ, the share where the higher level got the higher score.

    levels: numbers, bigger = better fit (for example 0 not / 1 partly / 2 relevant). Ties count half.
    """
    good = total = 0.0
    for (s1, l1), (s2, l2) in combinations(zip(scores, levels), 2):
        if l1 == l2:
            continue
        total += 1
        higher, lower = (s1, s2) if l1 > l2 else (s2, s1)
        good += 1.0 if higher > lower else 0.5 if higher == lower else 0.0
    return round(good / total, 3) if total else None


def ranking_quality(scores, levels):
    """How well do the scores rank the candidates of ONE job? levels: 0 not / 1 partly / 2 relevant.

    all_relevant_above_not: the lowest relevant score is higher than the highest not-relevant score.
    (None when the job has no relevant or no not-relevant candidate to compare.)
    """
    rel = [s for s, lv in zip(scores, levels) if lv == 2]
    non = [s for s, lv in zip(scores, levels) if lv == 0]
    positives = [lv >= 1 for lv in levels]
    k = sum(positives)
    return {"candidates": len(scores),
            "all_relevant_above_not": (min(rel) > max(non)) if rel and non else None,
            "auc_at_least_partly": pairwise_auc(scores, positives),
            "precision_at_k": precision_at_k(scores, positives, k), "k": k,
            "pairwise_order_accuracy": pairwise_order_accuracy(scores, levels)}


def group_stats(scores, groups):
    """min / mean / max score for each group name, for example the score range of 'relevant' pairs."""
    out = {}
    for name in dict.fromkeys(groups):
        values = [s for s, g in zip(scores, groups) if g == name]
        out[name] = {"count": len(values), "min": min(values), "max": max(values),
                     "mean": round(sum(values) / len(values), 1)}
    return out


# ----------------------------------------------------------------------------- leave-one-job-out validation
def leave_one_job_out(rows, thresholds):
    """Validate across job types: tune on all jobs but one, test on the one left out, repeat for every job.

    rows: list of {"job": name, "score": number, "truth": bool}. thresholds: candidates to try (for example
    range(0, 101)). The held-out job is NEVER used to choose its own threshold.
    Returns the folds, the pooled test metrics (all held-out predictions together) and the threshold spread.
    """
    jobs = list(dict.fromkeys(r["job"] for r in rows))
    folds, pooled = [], {"tp": 0, "fp": 0, "fn": 0, "tn": 0}
    for held_out in jobs:
        train = [r for r in rows if r["job"] != held_out]
        test = [r for r in rows if r["job"] == held_out]
        sweep = threshold_sweep([r["score"] for r in train], [r["truth"] for r in train], thresholds)
        chosen = best_threshold(sweep)
        result = evaluate_at_threshold([r["score"] for r in test], [r["truth"] for r in test], chosen)
        folds.append({"held_out": held_out, "tuned_on": sorted({r["job"] for r in train}),
                      "train_pairs": len(train), "test_pairs": len(test), **result})
        for key in pooled:
            pooled[key] += result[key]
    chosen_all = [f["threshold"] for f in folds]
    return {"folds": folds, "pooled_test": metrics_from_cm(pooled),
            "threshold_min": min(chosen_all), "threshold_max": max(chosen_all),
            "threshold_spread": max(chosen_all) - min(chosen_all)}
