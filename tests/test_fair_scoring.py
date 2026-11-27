"""Day 15 tests: evidence-aware skill credit and score normalization.  python -m unittest tests.test_fair_scoring -v"""
import unittest
from datetime import date

from ats_engine.fair_scoring import (FairATSScoringEngine, MIN_POOL, min_max, normalize_reports, normalize_values,
                                     percentiles, t_scores)
from ats_engine.score_generator import build_resume_bundle_from_text
from ats_engine.scoring_engine import ATSScoringEngine
from tests.test_ats_engine import JOB, StubMatcher

TODAY = date(2026, 11, 1)

USED = """Jane Doe
Experience
Full Stack Developer | Acme  Jan 2022 - Present
- Built React and Node.js apps with MongoDB and Express, deployed with Docker
Skills
React, Node.js, MongoDB, Express, Docker
Education
B.Sc in Computer Science, University X 2021
"""
LISTED = """Jane Doe
Experience
Office Assistant | Acme  Jan 2022 - Present
- Managed office supplies and scheduling
Skills
React, Node.js, MongoDB, Express, Docker
Education
B.Sc in Computer Science, University X 2021
"""
FRESHER = """Jane Doe
Skills
React, Node.js, MongoDB, Express, Docker
Education
B.Sc in Computer Science, University X 2021
"""


def fair():
    return FairATSScoringEngine(matcher=StubMatcher(), today=TODAY)


def base():
    return ATSScoringEngine(matcher=StubMatcher(), today=TODAY)


def bundle(text):
    return build_resume_bundle_from_text(text, TODAY)


class EvidenceTests(unittest.TestCase):
    def test_used_skills_get_full_credit(self):
        r = fair().score(bundle(USED), JOB, candidate_id="a")
        ev = r["components"]["skill_match"]["details"]["evidence"]
        self.assertEqual(ev["listed_only"], [])
        self.assertEqual(ev["skill_points_removed"], 0)

    def test_listed_only_skills_earn_less(self):
        b = bundle(LISTED)
        raw = base().score(b, JOB, candidate_id="a")["components"]["skill_match"]["score"]
        adj = fair().score(b, JOB, candidate_id="a")["components"]["skill_match"]["score"]
        self.assertLess(adj, raw)
        self.assertGreater(adj, 0)

    def test_penalty_size(self):
        b = bundle(LISTED)
        raw = base().score(b, JOB, candidate_id="a")["components"]["skill_match"]["score"]
        adj = fair().score(b, JOB, candidate_id="a")["components"]["skill_match"]["score"]
        # react, node.js, mongodb (must, 18.75 each) and docker (good, 12.5) lose 30%; "express" is exempt (ambiguous word)
        self.assertAlmostEqual(raw - adj, 0.3 * (3 * 18.75 + 12.5), delta=0.1)

    def test_fresher_is_not_punished(self):
        b = bundle(FRESHER)
        r = fair().score(b, JOB, candidate_id="a")
        ev = r["components"]["skill_match"]["details"]["evidence"]
        self.assertFalse(ev["applicable"])
        self.assertEqual(r["components"]["skill_match"]["score"], base().score(b, JOB, candidate_id="a")["components"]["skill_match"]["score"])

    def test_soft_skills_exempt(self):
        b = bundle(LISTED)
        b["skills"] = b["skills"] + ["communication"]
        job = dict(JOB, must_have_skills=["communication"], good_to_have_skills=[])
        ev = fair().score(b, job, candidate_id="a")["components"]["skill_match"]["details"]["evidence"]
        self.assertEqual(ev["listed_only"], [])
        self.assertEqual(ev["soft_skills_exempt"], ["communication"])

    def test_fairness_block_and_reasons(self):
        r = fair().score(bundle(LISTED), JOB, candidate_id="a")
        self.assertGreater(r["fairness"]["overall_points_removed"], 0)
        self.assertTrue(any("listed but not used" in x for x in r["components"]["skill_match"]["reasons"]))


class StuffingTests(unittest.TestCase):
    def stuffed(self):
        b = bundle(LISTED)
        b["skills"] = b["skills"] + ["java", "c++", "ruby", "php", "go", "rust", "swift", "kotlin", "scala", "perl",
                                     "matlab", "sql", "oracle", "redis", "kafka", "spark", "hadoop", "tableau"]
        return b

    def test_flagged(self):
        r = fair().score(self.stuffed(), JOB, candidate_id="a")
        self.assertTrue(r["components"]["skill_match"]["details"]["evidence"]["keyword_stuffing"])
        self.assertTrue(any("keyword stuffing" in f for f in r["flags"]))

    def test_shortlist_becomes_review(self):
        engine = fair()
        engine.config["thresholds"]["shortlist_score"] = 1          # make everybody reach the cutoff
        r = engine.score(self.stuffed(), JOB, candidate_id="a")
        self.assertEqual(r["recommendation"], "review")

    def test_normal_resume_not_flagged(self):
        r = fair().score(bundle(USED), JOB, candidate_id="a")
        self.assertFalse(r["components"]["skill_match"]["details"]["evidence"]["keyword_stuffing"])


class NormalizationTests(unittest.TestCase):
    def test_percentile(self):
        self.assertEqual(percentiles([10, 20, 30, 40, 50]), [10.0, 30.0, 50.0, 70.0, 90.0])

    def test_percentile_ties_share_value(self):
        p = percentiles([50, 50, 80])
        self.assertEqual(p[0], p[1])
        self.assertLess(p[0], p[2])

    def test_t_score_mean_is_50(self):
        self.assertAlmostEqual(sum(t_scores([10, 20, 30, 40])) / 4, 50, delta=0.2)

    def test_all_equal_is_50(self):
        self.assertEqual(t_scores([7, 7, 7]), [50.0] * 3)
        self.assertEqual(min_max([7, 7, 7]), [50.0] * 3)

    def test_min_max_range(self):
        self.assertEqual(min_max([20, 60, 40]), [0.0, 100.0, 50.0])

    def test_order_is_preserved(self):
        for method in ("percentile", "zscore", "minmax"):
            v = normalize_values([30, 90, 60, 10, 75], method)
            self.assertEqual(sorted(range(5), key=lambda i: v[i]), [3, 0, 2, 4, 1])

    def test_unknown_method(self):
        with self.assertRaises(ValueError):
            normalize_values([1, 2], "magic")

    def make(self, job, scores):
        return [{"candidate_id": f"c{i}", "job_id": job, "overall_score": s,
                 "components": {n: {"score": s} for n in ("skill_match", "experience_relevance", "education_alignment", "semantic_similarity")}}
                for i, s in enumerate(scores)]

    def test_small_pool_is_not_normalized(self):
        reports = normalize_reports(self.make("j1", [50, 60, 70]))
        self.assertIsNone(reports[0]["normalized"]["overall"])
        self.assertIn("at least", reports[0]["normalized"]["note"])

    def test_pool_normalized_and_raw_kept(self):
        reports = normalize_reports(self.make("j1", [40, 50, 60, 70, 80]))
        self.assertEqual(reports[4]["normalized"]["overall"], 90.0)
        self.assertEqual(reports[4]["overall_score"], 80)
        self.assertEqual(reports[0]["normalized"]["components"]["skill_match"], 10.0)

    def test_unscorable_resumes_leave_the_pool(self):
        reports = self.make("j1", [40, 50, 60, 70, 80, 0])
        reports[5]["data_completeness"] = 0                                  # scanned resume: nothing scored
        normalize_reports(reports)
        self.assertIsNone(reports[5]["normalized"]["overall"])
        self.assertEqual(reports[0]["normalized"]["overall"], 10.0)         # pool is still the five real scores
        self.assertEqual(reports[0]["normalized"]["pool_size"], 5)

    def test_jobs_are_normalized_separately(self):
        reports = normalize_reports(self.make("easy", [80, 85, 90, 92, 95]) + self.make("hard", [20, 25, 30, 32, 35]))
        self.assertEqual(reports[0]["normalized"]["overall"], reports[5]["normalized"]["overall"])   # both are the worst of their pool


if __name__ == "__main__":
    unittest.main()
