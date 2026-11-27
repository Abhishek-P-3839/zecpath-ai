"""Day 14 tests: auto-ranking engine.  Run:  python -m unittest tests.test_ranking -v

Fake Day 13 reports are used, so the tests are instant and do not need any resume files.
"""
import csv
import io
import json
import tempfile
import unittest
from pathlib import Path

from ats_engine.ranking_engine import (
    build_ranking, check_reports, format_ranking_table, rank_by_job, rank_reports, save_ranking,
    score_summary, to_csv, top_candidates,
)


def report(cid, score, skill=60, exp=60, completeness=1.0, confidence="high", job="job_a", missing=None):
    """A minimal stand-in for what ats_engine.score_generator.generate_score() returns."""
    return {
        "candidate_id": cid, "job_id": job, "job_title": "MERN Developer", "overall_score": score,
        "label": "good", "recommendation": "review", "confidence": confidence, "data_completeness": completeness,
        "components": {"skill_match": {"score": skill, "details": {"missing_must_have": missing or []}},
                       "experience_relevance": {"score": exp},
                       "education_alignment": {"score": None},
                       "semantic_similarity": {"score": 70}},
        "strengths": ["Skill match is strong."], "gaps": ["Education is weak."], "flags": [],
    }


class TestOrdering(unittest.TestCase):
    def test_sorted_by_overall_score_best_first(self):
        rows = rank_reports([report("low", 40), report("top", 90), report("mid", 65)])
        self.assertEqual([r["candidate_id"] for r in rows], ["top", "mid", "low"])
        self.assertEqual([r["position"] for r in rows], [1, 2, 3])

    def test_tie_broken_by_skill_match_then_experience(self):
        rows = rank_reports([report("a", 70, skill=50), report("b", 70, skill=80), report("c", 70, skill=80, exp=90)])
        self.assertEqual([r["candidate_id"] for r in rows], ["c", "b", "a"])

    def test_tie_broken_by_data_completeness_then_id(self):
        rows = rank_reports([report("zed", 70, completeness=0.5), report("bob", 70), report("amy", 70)])
        self.assertEqual([r["candidate_id"] for r in rows], ["amy", "bob", "zed"])

    def test_missing_component_score_sorts_after_a_real_one(self):
        rows = rank_reports([report("none", 70, skill=None), report("real", 70, skill=0)])
        self.assertEqual(rows[0]["candidate_id"], "real")

    def test_same_input_always_gives_the_same_order(self):
        reports = [report(c, 70) for c in "edcba"]
        self.assertEqual([r["candidate_id"] for r in rank_reports(reports)],
                         [r["candidate_id"] for r in rank_reports(list(reversed(reports)))])


class TestRanksAndPercentiles(unittest.TestCase):
    def test_equal_scores_share_a_rank_but_not_a_position(self):
        rows = rank_reports([report("a", 80), report("b", 70), report("c", 70), report("d", 50)])
        self.assertEqual([r["rank"] for r in rows], [1, 2, 2, 4])
        self.assertEqual([r["position"] for r in rows], [1, 2, 3, 4])
        self.assertEqual([r["tied"] for r in rows], [False, True, True, False])

    def test_percentile_runs_from_100_to_0(self):
        rows = rank_reports([report("a", 90), report("b", 60), report("c", 30)])
        self.assertEqual([r["percentile"] for r in rows], [100, 50, 0])

    def test_single_candidate(self):
        self.assertEqual(rank_reports([report("only", 55)])[0]["percentile"], 100)


class TestTopLists(unittest.TestCase):
    def setUp(self):
        self.rows = rank_reports([report("a", 90), report("b", 80), report("c", 80), report("d", 50)])

    def test_top_n_includes_ties_at_the_border(self):
        self.assertEqual([r["candidate_id"] for r in top_candidates(self.rows, 2)], ["a", "b", "c"])

    def test_top_n_without_ties(self):
        self.assertEqual(len(top_candidates(self.rows, 2, include_ties=False)), 2)

    def test_min_score_filter(self):
        self.assertEqual([r["candidate_id"] for r in top_candidates(self.rows, 10, min_score=80)], ["a", "b", "c"])

    def test_n_bigger_than_list(self):
        self.assertEqual(len(top_candidates(self.rows, 99)), 4)


class TestBadInput(unittest.TestCase):
    def test_mixed_jobs_are_refused(self):
        with self.assertRaises(ValueError) as ctx:
            rank_reports([report("a", 80, job="job_a"), report("b", 70, job="job_b")])
        self.assertIn("rank_by_job", str(ctx.exception))

    def test_not_an_ats_report(self):
        with self.assertRaises(ValueError):
            check_reports([{"candidate_id": "x"}])

    def test_rank_by_job_ranks_each_job_alone(self):
        result = rank_by_job([report("a", 80, job="job_a"), report("b", 70, job="job_b"), report("c", 60, job="job_a")])
        self.assertEqual([r["candidate_id"] for r in result["job_a"]], ["a", "c"])
        self.assertEqual(result["job_b"][0]["rank"], 1)

    def test_empty_list(self):
        output = build_ranking([])
        self.assertEqual(output["total_candidates"], 0)
        self.assertIn("No candidates to rank.", output["warnings"])


class TestRecruiterOutput(unittest.TestCase):
    def setUp(self):
        self.output = build_ranking([report("amy", 82, missing=["docker"]), report("bob", 64),
                                     report("cat", 30, confidence="low")], top_n=2)

    def test_output_structure(self):
        self.assertEqual(self.output["job_id"], "job_a")
        self.assertEqual(self.output["total_candidates"], 3)
        self.assertEqual(self.output["score_summary"], {"highest": 82, "lowest": 30, "average": 58.67, "median": 64})
        self.assertEqual([t["candidate_id"] for t in self.output["top_candidates"]], ["amy", "bob"])
        json.dumps(self.output)                       # must be JSON-safe

    def test_low_confidence_is_flagged_and_warned(self):
        cat = self.output["ranking"][2]
        self.assertTrue(cat["needs_manual_check"])
        self.assertTrue(any("low confidence" in w for w in self.output["warnings"]))

    def test_duplicate_candidate_ids_warn(self):
        output = build_ranking([report("amy", 80), report("amy", 70)])
        self.assertTrue(any("Duplicate" in w for w in output["warnings"]))
        self.assertEqual(output["total_candidates"], 2)

    def test_table_text(self):
        text = format_ranking_table(self.output)
        self.assertIn("Ranking for: MERN Developer", text)
        self.assertIn("amy", text)
        self.assertIn("missing must-have: docker", text)
        self.assertLess(text.index("amy"), text.index("bob"))

    def test_csv_is_readable_back(self):
        rows = list(csv.DictReader(io.StringIO(to_csv(self.output))))
        self.assertEqual([r["candidate_id"] for r in rows], ["amy", "bob", "cat"])
        self.assertEqual(rows[0]["missing_must_have"], "docker")
        self.assertEqual(rows[0]["education_alignment"], "")       # None -> empty cell

    def test_save_ranking_writes_three_files(self):
        with tempfile.TemporaryDirectory() as folder:
            paths = save_ranking(self.output, folder)
            self.assertEqual(sorted(p.name for p in paths.values()),
                             ["job_a.ranking.csv", "job_a.ranking.json", "job_a.ranking.txt"])
            self.assertEqual(json.loads(Path(paths["json"]).read_text(encoding="utf-8"))["total_candidates"], 3)

    def test_score_summary_empty(self):
        self.assertIsNone(score_summary([]))


if __name__ == "__main__":
    unittest.main()
