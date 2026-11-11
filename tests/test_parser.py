import os
import unittest

from parsers.resume_parser import parse_resume_text

SAMPLE = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data", "sample_resume.txt")


class TestResumeParser(unittest.TestCase):
    def test_parse_sample_resume(self):
        with open(SAMPLE) as f:
            result = parse_resume_text(f.read())
        self.assertEqual(result["email"], "rahul.kumar@example.com")
        self.assertIn("python", result["skills"])
        self.assertEqual(result["experience_years"], 2)

    def test_empty_text(self):
        result = parse_resume_text("")
        self.assertIsNone(result["email"])
        self.assertEqual(result["skills"], [])


if __name__ == "__main__":
    unittest.main()
