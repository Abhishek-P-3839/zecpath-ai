"""Day 12 tests: resume <-> job similarity scorer (matching/similarity_scorer.py).

Run:  python -m unittest tests.test_similarity_scorer -v
Uses the offline HashingEmbedder, so no downloads and the tests are fast.
"""
import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from matching.embedders import HashingEmbedder
from matching.semantic_engine import SemanticMatcher
from matching.similarity_scorer import (
    CONFIG_PATH, default_name, format_result, label_for, load_thresholds, resume_to_views,
    score_many, score_resume_to_job, validate_thresholds,
)

THRESHOLDS = {"labels": {"strong": 75, "good": 55, "partial": 35}}
JOB = {"job_id": "job_py", "title": "Python Developer", "normalized_title": "python developer",
       "must_have_skills": ["python", "django", "docker"], "good_to_have_skills": ["aws"]}
STRONG = {"skills": ["python", "django", "docker", "aws"],
          "experience": "Python developer. Built Django REST APIs and deployed them with Docker on AWS.",
          "projects": "", "summary": ""}
WEAK = {"skills": ["excel"], "experience": "HR executive. Managed payroll and recruitment for staff.",
        "projects": "", "summary": ""}
EMPTY = {"skills": [], "experience": "", "projects": "", "summary": ""}


def matcher():
    return SemanticMatcher(embedder=HashingEmbedder())


class LabelTests(unittest.TestCase):
    def test_labels_at_the_boundaries(self):
        expected = {100: "strong", 75: "strong", 74: "good", 55: "good", 54: "partial", 35: "partial",
                    34: "weak", 0: "weak"}
        for score, label in expected.items():
            self.assertEqual(label_for(score, THRESHOLDS), label, score)


class ConfigTests(unittest.TestCase):
    def test_shipped_config_is_valid(self):
        self.assertEqual(validate_thresholds(load_thresholds(CONFIG_PATH)), [])

    def test_valid_config_has_no_errors(self):
        self.assertEqual(validate_thresholds(THRESHOLDS), [])

    def test_bad_configs_are_reported(self):
        bad = [
            ({}, "labels"),                                                        # missing labels
            ({"labels": {"strong": 50, "good": 60, "partial": 35}}, "strong > good > partial"),
            ({"labels": {"strong": 75, "good": 55, "partial": 55}}, "strong > good > partial"),
            ({"labels": {"strong": 150, "good": 55, "partial": 35}}, "between 0 and 100"),
            ({"labels": {"strong": 75, "good": "55", "partial": 35}}, "number"),
            ({"labels": {"strong": 75, "good": 55}}, "exactly"),
            ({"labels": {"strong": 75, "good": 55, "partial": 35, "extra": 1}}, "exactly"),
        ]
        for config, word in bad:
            errors = validate_thresholds(config)
            self.assertTrue(errors and any(word in e for e in errors), (config, errors))

    def test_loading_a_bad_file_raises(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "t.json"
            path.write_text(json.dumps({"labels": {"strong": 10, "good": 20, "partial": 30}}), encoding="utf-8")
            with self.assertRaises(ValueError):
                load_thresholds(path)

    def test_label_for_reads_the_config_file_by_default(self):
        labels = load_thresholds()["labels"]
        self.assertEqual(label_for(labels["strong"]), "strong")
        self.assertEqual(label_for(labels["partial"] - 1), "weak")


class ScoreOneTests(unittest.TestCase):
    def test_strong_resume_scores_higher_than_weak_resume(self):
        strong = score_resume_to_job(STRONG, JOB, matcher=matcher(), thresholds=THRESHOLDS)
        weak = score_resume_to_job(WEAK, JOB, matcher=matcher(), thresholds=THRESHOLDS)
        self.assertEqual(strong["status"], "scored")
        self.assertGreater(strong["similarity_score"], weak["similarity_score"])
        self.assertIn(strong["label"], ("strong", "good"))
        self.assertEqual(weak["label"], "weak")

    def test_result_has_all_the_documented_fields(self):
        r = score_resume_to_job(STRONG, JOB, matcher=matcher(), thresholds=THRESHOLDS)
        for key in ("status", "similarity_score", "label", "parts", "matched_skills", "related_skills",
                    "missing_must_have", "parts_without_data", "embedder", "reasons"):
            self.assertIn(key, r)
        self.assertEqual(set(r["parts"]), {"skills", "experience", "projects"})
        self.assertEqual(r["embedder"], "hashing-offline")
        self.assertTrue(0 <= r["similarity_score"] <= 100)
        self.assertEqual(r["matched_skills"], ["python", "django", "docker", "aws"])

    def test_missing_must_have_skills_are_listed(self):
        r = score_resume_to_job({**STRONG, "skills": ["python"]}, JOB, matcher=matcher(), thresholds=THRESHOLDS)
        self.assertEqual(r["missing_must_have"], ["django", "docker"])       # 'aws' is only good-to-have
        self.assertTrue(any("Missing must-have" in text for text in r["reasons"]))

    def test_part_without_data_is_skipped_and_named(self):
        r = score_resume_to_job(STRONG, JOB, matcher=matcher(), thresholds=THRESHOLDS)
        self.assertEqual(r["parts_without_data"], ["projects"])
        self.assertIsNone(r["parts"]["projects"])
        self.assertTrue(any("No data for projects" in text for text in r["reasons"]))

    def test_resume_with_no_content_is_unscorable_not_zero(self):
        r = score_resume_to_job(EMPTY, JOB, matcher=matcher(), thresholds=THRESHOLDS)
        self.assertEqual(r["status"], "unscorable")
        self.assertIsNone(r["similarity_score"])
        self.assertIsNone(r["label"])

    def test_scanned_file_is_unscorable_with_a_reason(self):
        scanned = {"status": "ok", "clean_text": "", "needs_ocr": True}
        with mock.patch("extraction.extractor.extract_resume", return_value=scanned):
            r = score_resume_to_job(Path("scan.pdf"), JOB, matcher=matcher(), thresholds=THRESHOLDS)
        self.assertEqual(r["status"], "unscorable")
        self.assertIsNone(r["similarity_score"])
        self.assertIn("scanned", r["reasons"][0])
        self.assertEqual(r["resume"], "scan.pdf")

    def test_failed_extraction_is_unscorable(self):
        failed = {"status": "failed", "clean_text": "", "needs_ocr": False}
        with mock.patch("extraction.extractor.extract_resume", return_value=failed):
            r = score_resume_to_job(Path("broken.pdf"), JOB, matcher=matcher(), thresholds=THRESHOLDS)
        self.assertEqual(r["status"], "unscorable")

    def test_job_without_content_is_unscorable(self):
        r = score_resume_to_job(STRONG, {"job_id": "empty"}, matcher=matcher(), thresholds=THRESHOLDS)
        self.assertEqual(r["status"], "unscorable")

    def test_missing_file_raises_instead_of_scoring_it_as_text(self):
        with self.assertRaises(FileNotFoundError):
            score_resume_to_job("no_such_resume.pdf", JOB, matcher=matcher(), thresholds=THRESHOLDS)

    def test_bad_input_type_raises(self):
        with self.assertRaises(TypeError):
            resume_to_views(42)

    def test_resume_text_is_turned_into_views(self):
        views, problem = resume_to_views("Skills\nPython, Django\nExperience\nBuilt Python APIs for a startup")
        self.assertIsNone(problem)
        self.assertIn("python", views["skills"])

    def test_default_name(self):
        self.assertEqual(default_name(Path("data/a/Maya.pdf")), "Maya.pdf")
        self.assertIsNone(default_name(STRONG))


class ScoreManyTests(unittest.TestCase):
    def test_sorted_best_first_and_unscorable_last(self):
        resumes = {"weak": WEAK, "empty": EMPTY, "strong": STRONG}
        results = score_many(resumes, JOB, matcher=matcher(), thresholds=THRESHOLDS)
        self.assertEqual([r["resume"] for r in results], ["strong", "weak", "empty"])
        self.assertEqual(results[-1]["status"], "unscorable")

    def test_list_input_gets_default_names(self):
        results = score_many([WEAK, STRONG], JOB, matcher=matcher(), thresholds=THRESHOLDS)
        self.assertEqual([r["resume"] for r in results], ["resume_2", "resume_1"])

    def test_equal_scores_are_ordered_by_name(self):
        results = score_many({"b": STRONG, "a": STRONG}, JOB, matcher=matcher(), thresholds=THRESHOLDS)
        self.assertEqual([r["resume"] for r in results], ["a", "b"])


class FormatTests(unittest.TestCase):
    def test_format_scored_and_unscorable(self):
        scored = score_resume_to_job(STRONG, JOB, matcher=matcher(), thresholds=THRESHOLDS, name="strong")
        self.assertIn("strong vs job_py", format_result(scored))
        unscorable = score_resume_to_job(EMPTY, JOB, matcher=matcher(), thresholds=THRESHOLDS, name="empty")
        self.assertIn("UNSCORABLE", format_result(unscorable))


if __name__ == "__main__":
    unittest.main()
