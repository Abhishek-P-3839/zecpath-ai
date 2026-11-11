import copy
import unittest
from pathlib import Path

from utils.schema_validator import get_errors, load_json

ROOT = Path(__file__).resolve().parent.parent
SAMPLES = ROOT / "data" / "samples"


class TestResumeSchema(unittest.TestCase):
    def setUp(self):
        self.resume = load_json(SAMPLES / "sample_resume.json")

    def test_sample_resume_is_valid(self):
        self.assertEqual(get_errors(self.resume, "resume"), [])

    def test_missing_email_is_invalid(self):
        bad = copy.deepcopy(self.resume)
        del bad["personal"]["email"]
        self.assertTrue(get_errors(bad, "resume"))

    def test_bad_date_format_is_invalid(self):
        bad = copy.deepcopy(self.resume)
        bad["experience"][0]["start_date"] = "October 2024"
        self.assertTrue(get_errors(bad, "resume"))

    def test_confidence_out_of_range_is_invalid(self):
        bad = copy.deepcopy(self.resume)
        bad["skills"][0]["confidence"] = 1.7
        self.assertTrue(get_errors(bad, "resume"))


class TestJobSchema(unittest.TestCase):
    def setUp(self):
        self.job = load_json(SAMPLES / "sample_job.json")

    def test_sample_job_is_valid(self):
        self.assertEqual(get_errors(self.job, "job"), [])

    def test_bad_importance_is_invalid(self):
        bad = copy.deepcopy(self.job)
        bad["requirements"]["skills"][0]["importance"] = "very_important"
        self.assertTrue(get_errors(bad, "job"))

    def test_missing_requirements_is_invalid(self):
        bad = copy.deepcopy(self.job)
        del bad["requirements"]
        self.assertTrue(get_errors(bad, "job"))


if __name__ == "__main__":
    unittest.main()
