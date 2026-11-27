"""Day 13 tests: weights, explainable report, missing data handling, end to end."""
import copy
import unittest
from datetime import date

from ats_engine.scoring_engine import ATSScoringEngine, format_report
from ats_engine.score_generator import build_resume_bundle_from_text, generate_score, rank_candidates
from ats_engine.weights import COMPONENTS, load_config, normalize, rescale, resolve_weights, validate_config

TODAY = date(2026, 11, 1)


class StubMatcher:
    """Deterministic stand-in for the Day 12 SemanticMatcher (no numpy / model needed)."""
    class embedder:
        name = "stub"

    def compare_skills(self, have, job):
        wanted = job["must"] + job["good"]
        exact = [s for s in wanted if s in have]
        missing = [s for s in wanted if s not in have]
        m = sum(s in have for s in job["must"]) / len(job["must"]) if job["must"] else None
        g = sum(s in have for s in job["good"]) / len(job["good"]) if job["good"] else None
        cov = 0.75 * m + 0.25 * g if (m is not None and g is not None) else (m if m is not None else g)
        return {"coverage": cov, "matched_exact": exact, "matched_semantic": [], "missing": missing}

    def compare_text(self, a, b):
        if not (a or "").strip() or not (b or "").strip():
            return None
        return {"score": 0.6, "cosine": 0.5}


JOB = {"job_id": "job_0001", "title": "MERN Stack Developer", "normalized_title": "full stack developer",
       "role_category": "technical", "level": "mid", "min_years": 2, "max_years": 5,
       "must_have_skills": ["react", "node.js", "mongodb", "express"], "good_to_have_skills": ["docker", "aws"],
       "education_min_level": "bachelor", "preferred_fields": ["Computer Science", "Information Technology"]}


def entry(title, company, start, end, skills):
    from parsers.experience_parser import parse_experience
    text = f"{title} | {company}  {start} - {end}\n- Built web apps\n"
    return parse_experience(text, TODAY)


def bundle(skills, exp, level="bachelor", field="Computer Science", in_progress=False, edu=True):
    education = {"education": [{"degree": "B.Tech", "level": level, "field_of_study": field, "institution": "X College",
                                "in_progress": in_progress}] if edu else [], "certifications": []}
    return {"skills": skills, "experience": exp, "education": education,
            "views": {"skills": skills, "experience": "Built web apps", "projects": "", "summary": ""}, "warnings": []}


def engine(config=None):
    return ATSScoringEngine(config=config, matcher=StubMatcher(), today=TODAY)


class TestWeights(unittest.TestCase):
    def test_default_config_is_valid_and_adds_to_one(self):
        cfg = load_config()
        self.assertEqual(validate_config(cfg), [])
        self.assertAlmostEqual(sum(resolve_weights({}, cfg)["weights"].values()), 1.0)

    def test_profile_choice(self):
        cfg = load_config()
        self.assertEqual(resolve_weights({"level": "fresher"}, cfg)["source"], "profile: entry_level")
        self.assertEqual(resolve_weights({"level": "senior"}, cfg)["source"], "profile: senior")
        self.assertEqual(resolve_weights({"role_category": "non_technical"}, cfg)["source"], "profile: non_technical")
        self.assertEqual(resolve_weights({"normalized_title": "data scientist"}, cfg)["source"], "role: data scientist")
        self.assertEqual(resolve_weights({"level": "mid", "role_category": "technical"}, cfg)["source"], "default")

    def test_job_override_is_normalized(self):
        r = resolve_weights({"ats_weights": {"skill_match": 0.9}}, load_config())
        self.assertAlmostEqual(sum(r["weights"].values()), 1.0)
        self.assertGreater(r["weights"]["skill_match"], 0.5)
        self.assertIn("job override", r["source"])

    def test_normalize_and_rescale(self):
        self.assertEqual(normalize({"skill_match": 2, "experience_relevance": 2}), {"skill_match": 0.5, "experience_relevance": 0.5})
        w = rescale({"skill_match": 0.4, "experience_relevance": 0.25, "education_alignment": 0.1, "semantic_similarity": 0.25},
                    ["skill_match", "experience_relevance", "semantic_similarity"])
        self.assertAlmostEqual(sum(w.values()), 1.0)
        self.assertAlmostEqual(w["skill_match"], 0.4 / 0.9)

    def test_bad_config_is_rejected(self):
        cfg = copy.deepcopy(load_config())
        cfg["default_weights"]["skill_match"] = -1
        cfg["missing_data"]["skill_match"] = "maybe"
        self.assertEqual(len(validate_config(cfg)), 2)
        with self.assertRaises(ValueError):
            normalize({"skill_match": 1, "colour": 1})


class TestScoring(unittest.TestCase):
    def setUp(self):
        self.exp = entry("Full Stack Developer", "WebCo", "Jan 2022", "Present", [])
        self.strong = bundle(["react", "node.js", "mongodb", "express", "docker"], self.exp)
        self.weak = bundle(["excel"], {"entries": [], "total_experience_years": 0}, level="higher_secondary", field="Commerce")

    def test_strong_beats_weak(self):
        eng = engine()
        a, b = eng.score(self.strong, JOB, candidate_id="a"), eng.score(self.weak, JOB, candidate_id="b")
        self.assertGreater(a["overall_score"], b["overall_score"] + 25)
        self.assertEqual(a["recommendation"], "shortlist")
        self.assertEqual(rank_candidates([b, a])[0]["candidate_id"], "a")

    def test_report_is_explainable(self):
        r = engine().score(self.strong, JOB, candidate_id="a")
        total = sum(c["contribution"] for c in r["components"].values())
        self.assertAlmostEqual(total, r["overall_score"], delta=0.2)
        self.assertAlmostEqual(sum(c["weight"] for c in r["components"].values()), 1.0, delta=0.01)
        self.assertIn("=", r["formula"])
        for name in COMPONENTS:
            self.assertTrue(r["components"][name]["reasons"])
        self.assertIn("OVERALL", format_report(r))

    def test_missing_must_have_is_flagged(self):
        r = engine().score(bundle(["react"], self.exp), JOB, candidate_id="a")
        self.assertTrue(any("node.js" in f for f in r["flags"]))

    def test_missing_education_is_skipped_and_weights_rescaled(self):
        r = engine().score(bundle(["react", "node.js", "mongodb", "express"], self.exp, edu=False), JOB, candidate_id="a")
        edu = r["components"]["education_alignment"]
        self.assertIsNone(edu["score"])
        self.assertEqual(edu["weight"], 0)
        self.assertAlmostEqual(sum(c["weight"] for c in r["components"].values()), 1.0, delta=0.01)
        self.assertLess(r["data_completeness"], 1.0)
        self.assertTrue(any("Education alignment was skipped" in w for w in r["warnings"]))

    def test_missing_data_policies(self):
        cfg = copy.deepcopy(load_config())
        b = bundle(["react", "node.js", "mongodb", "express"], self.exp, edu=False)
        cfg["missing_data"]["education_alignment"] = "neutral"
        self.assertEqual(engine(cfg).score(b, JOB)["components"]["education_alignment"]["score"], 50.0)
        cfg["missing_data"]["education_alignment"] = "zero"
        self.assertEqual(engine(cfg).score(b, JOB)["components"]["education_alignment"]["score"], 0.0)

    def test_job_without_education_requirement_skips_education(self):
        job = {k: v for k, v in JOB.items() if k not in ("education_min_level", "preferred_fields")}
        r = engine().score(self.strong, job)
        self.assertEqual(r["components"]["education_alignment"]["status"], "missing_job")

    def test_fresher_not_punished_for_entry_level_job_but_punished_for_senior(self):
        fresher = bundle(["react", "node.js", "mongodb", "express"], {"entries": [], "total_experience_years": 0})
        entry_job = dict(JOB, level="fresher", min_years=0)
        r1 = engine().score(fresher, entry_job)
        self.assertEqual(r1["components"]["experience_relevance"]["status"], "skipped_entry_level")
        self.assertIsNone(r1["components"]["experience_relevance"]["score"])
        r2 = engine().score(fresher, dict(JOB, min_years=4))
        self.assertEqual(r2["components"]["experience_relevance"]["score"], 0.0)

    def test_empty_resume_gives_low_confidence_review_not_crash(self):
        r = engine().score({"skills": [], "experience": None, "education": None, "views": {}, "warnings": ["empty"]}, JOB)
        self.assertEqual(r["confidence"], "low")
        self.assertEqual(r["recommendation"], "review")      # never auto-reject a resume we could not read
        self.assertIn("empty", r["warnings"])

    def test_education_level_logic(self):
        eng = engine()
        ok = eng.score(bundle(["react"], self.exp, level="master"), JOB)["components"]["education_alignment"]["score"]
        below = eng.score(bundle(["react"], self.exp, level="diploma"), JOB)["components"]["education_alignment"]["score"]
        way_below = eng.score(bundle(["react"], self.exp, level="secondary"), JOB)["components"]["education_alignment"]["score"]
        ongoing = eng.score(bundle(["react"], self.exp, level="bachelor", in_progress=True), JOB)["components"]["education_alignment"]["score"]
        self.assertGreater(ok, ongoing)
        self.assertGreater(ongoing, below)
        self.assertGreater(below, way_below)

    def test_education_field_logic(self):
        eng = engine()
        exact = eng.score(bundle(["react"], self.exp, field="Computer Science"), JOB)["components"]["education_alignment"]["score"]
        related = eng.score(bundle(["react"], self.exp, field="Data Science"), JOB)["components"]["education_alignment"]["score"]
        other = eng.score(bundle(["react"], self.exp, field="Commerce"), JOB)["components"]["education_alignment"]["score"]
        self.assertGreater(exact, related)
        self.assertGreater(related, other)

    def test_role_weights_change_the_score(self):
        b = bundle(["react", "node.js", "mongodb", "express"], self.exp)
        base = engine().score(b, JOB)
        heavy_skills = engine().score(b, dict(JOB, ats_weights={"skill_match": 5}))
        self.assertGreater(heavy_skills["weights"]["effective"]["skill_match"], base["weights"]["effective"]["skill_match"])

    def test_cutoff_and_review_band(self):
        r = engine().score(self.strong, dict(JOB, ats_cutoff_score=99))
        self.assertIn(r["recommendation"], ("review", "reject"))


class TestEndToEnd(unittest.TestCase):
    RESUME = """Priya Nair
priya@example.com

SKILLS
React, Node.js, MongoDB, Express, Git

EXPERIENCE
Full Stack Developer | WebNest Solutions   Jan 2022 - Present
- Built React pages and REST APIs with Node.js and MongoDB

EDUCATION
B.Tech in Computer Science, Cochin University, 2018 - 2022
"""

    def test_text_to_report(self):
        try:
            from matching.embedders import HashingEmbedder
            from matching.semantic_engine import SemanticMatcher
            matcher = SemanticMatcher(embedder=HashingEmbedder())
        except Exception as exc:                                          # numpy not installed
            self.skipTest(f"semantic matcher not available: {exc}")
        eng = ATSScoringEngine(matcher=matcher, today=TODAY)
        report = generate_score(self.RESUME, JOB, candidate_id="priya", engine=eng, today=TODAY)
        self.assertGreater(report["overall_score"], 50)
        self.assertEqual(report["components"]["education_alignment"]["status"], "scored")
        self.assertEqual(report["components"]["semantic_similarity"]["details"]["backend"], matcher.embedder.name)


if __name__ == "__main__":
    unittest.main()
