"""Day 12 tests: metric functions in matching/evaluation.py (all numbers can be checked by hand).

Run:  python -m unittest tests.test_matching_eval -v
"""
import unittest

from matching.evaluation import (
    accuracy, best_threshold, confusion_matrix, evaluate_at_threshold, f1_score, group_stats,
    leave_one_job_out, pairwise_auc, pairwise_order_accuracy, precision, precision_at_k,
    ranking_quality, recall, threshold_sweep,
)

TRUTHS = [True, True, False, True, False]
SCORES = [90, 80, 60, 40, 20]


class BasicMetricTests(unittest.TestCase):
    def test_confusion_matrix_counts(self):
        cm = confusion_matrix([True, True, False, True, False], [True, True, True, False, False])
        self.assertEqual(cm, {"tp": 2, "fp": 1, "fn": 1, "tn": 1})

    def test_length_mismatch_raises(self):
        with self.assertRaises(ValueError):
            confusion_matrix([True], [True, False])

    def test_precision_recall_f1_accuracy(self):
        cm = {"tp": 2, "fp": 1, "fn": 1, "tn": 1}
        self.assertEqual(precision(cm), 0.667)
        self.assertEqual(recall(cm), 0.667)
        self.assertEqual(f1_score(cm), 0.667)
        self.assertEqual(accuracy(cm), 0.6)

    def test_undefined_metrics_are_none_not_zero(self):
        nothing_predicted = {"tp": 0, "fp": 0, "fn": 2, "tn": 3}
        no_real_matches = {"tp": 0, "fp": 1, "fn": 0, "tn": 4}
        self.assertIsNone(precision(nothing_predicted))
        self.assertIsNone(f1_score(nothing_predicted))
        self.assertIsNone(recall(no_real_matches))
        self.assertIsNone(accuracy({"tp": 0, "fp": 0, "fn": 0, "tn": 0}))

    def test_f1_is_zero_when_precision_and_recall_are_zero(self):
        self.assertEqual(f1_score({"tp": 0, "fp": 2, "fn": 2, "tn": 0}), 0.0)


class ThresholdTests(unittest.TestCase):
    def test_evaluate_at_threshold_uses_greater_or_equal(self):
        row = evaluate_at_threshold(SCORES, TRUTHS, 60)             # 60 itself counts as a match
        self.assertEqual((row["tp"], row["fp"], row["fn"], row["tn"]), (2, 1, 1, 1))
        row = evaluate_at_threshold(SCORES, TRUTHS, 61)
        self.assertEqual((row["tp"], row["fp"], row["fn"], row["tn"]), (2, 0, 1, 2))

    def test_sweep_has_one_row_per_threshold(self):
        sweep = threshold_sweep(SCORES, TRUTHS, [0, 50, 100])
        self.assertEqual([r["threshold"] for r in sweep], [0, 50, 100])
        self.assertEqual(sweep[0]["recall"], 1.0)                    # threshold 0: everything is a match
        self.assertIsNone(sweep[2]["precision"])                     # threshold 100: nothing is a match

    def test_best_threshold_takes_middle_of_tied_plateau(self):
        sweep = threshold_sweep([80, 70], [True, False], range(0, 101))
        self.assertEqual(best_threshold(sweep), 75)                  # perfect for 71..80 -> middle is 75

    def test_best_threshold_empty_sweep(self):
        self.assertIsNone(best_threshold([]))


class RankingTests(unittest.TestCase):
    def test_pairwise_auc(self):
        self.assertEqual(pairwise_auc([3, 1, 2], [True, True, False]), 0.5)   # 3>2 wins, 1<2 loses
        self.assertEqual(pairwise_auc([2, 2], [True, False]), 0.5)            # a tie counts half
        self.assertEqual(pairwise_auc([9, 1], [True, False]), 1.0)

    def test_pairwise_auc_needs_both_groups(self):
        self.assertIsNone(pairwise_auc([1, 2], [True, True]))

    def test_precision_at_k(self):
        scores, truths = [9, 8, 7, 1], [True, False, True, True]
        self.assertEqual(precision_at_k(scores, truths, 2), 0.5)
        self.assertEqual(precision_at_k(scores, truths, 3), 0.667)
        self.assertIsNone(precision_at_k(scores, truths, 0))

    def test_pairwise_order_accuracy(self):
        self.assertEqual(pairwise_order_accuracy([90, 50, 10], [2, 1, 0]), 1.0)
        self.assertEqual(pairwise_order_accuracy([10, 50, 90], [2, 1, 0]), 0.0)
        self.assertEqual(pairwise_order_accuracy([50, 50], [2, 1]), 0.5)
        self.assertIsNone(pairwise_order_accuracy([50, 60], [1, 1]))         # no pair with different levels

    def test_ranking_quality_perfect_job(self):
        q = ranking_quality([80, 60, 30, 10], [2, 1, 1, 0])
        self.assertTrue(q["all_relevant_above_not"])
        self.assertEqual((q["k"], q["precision_at_k"], q["auc_at_least_partly"]), (3, 1.0, 1.0))

    def test_ranking_quality_detects_a_relevant_below_a_not_relevant(self):
        q = ranking_quality([30, 40], [2, 0])
        self.assertFalse(q["all_relevant_above_not"])

    def test_ranking_quality_without_relevant_is_none(self):
        self.assertIsNone(ranking_quality([30, 40], [1, 0])["all_relevant_above_not"])

    def test_group_stats(self):
        stats = group_stats([10, 20, 90], ["not", "not", "yes"])
        self.assertEqual(stats["not"], {"count": 2, "min": 10, "max": 20, "mean": 15.0})
        self.assertEqual(stats["yes"]["max"], 90)


class LeaveOneJobOutTests(unittest.TestCase):
    ROWS = [{"job": j, "score": s, "truth": t}
            for j, pos, neg in (("a", 80, 20), ("b", 70, 10), ("c", 75, 15))
            for s, t in ((pos, True), (neg, False))]

    def test_threshold_is_tuned_without_the_held_out_job(self):
        result = leave_one_job_out(self.ROWS, range(0, 101))
        # held out a: train b,c is perfect for 16..70 -> middle 43. b: 21..75 -> 48. c: 21..70 -> 45.
        self.assertEqual([f["threshold"] for f in result["folds"]], [43, 48, 45])
        self.assertEqual([f["held_out"] for f in result["folds"]], ["a", "b", "c"])
        for fold in result["folds"]:
            self.assertNotIn(fold["held_out"], fold["tuned_on"])
            self.assertEqual((fold["train_pairs"], fold["test_pairs"]), (4, 2))

    def test_pooled_result_and_spread(self):
        result = leave_one_job_out(self.ROWS, range(0, 101))
        pooled = result["pooled_test"]
        self.assertEqual((pooled["tp"], pooled["fp"], pooled["fn"], pooled["tn"]), (3, 0, 0, 3))
        self.assertEqual(pooled["f1"], 1.0)
        spread = (result["threshold_min"], result["threshold_max"], result["threshold_spread"])
        self.assertEqual(spread, (43, 48, 5))

    def test_a_bad_held_out_job_is_reported_as_errors(self):
        rows = self.ROWS[:4] + [{"job": "z", "score": 90, "truth": False},
                                {"job": "z", "score": 10, "truth": True}]
        folds = leave_one_job_out(rows, range(0, 101))["folds"]
        z_fold = next(f for f in folds if f["held_out"] == "z")
        self.assertEqual((z_fold["fp"], z_fold["fn"]), (1, 1))


if __name__ == "__main__":
    unittest.main()
