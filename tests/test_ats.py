import unittest

from ats_engine.ats_scorer import calculate_ats_score


class TestATS(unittest.TestCase):
    def setUp(self):
        self.resume = {"email": None, "skills": ["python", "react", "git"], "experience_years": 2}

    def test_full_match(self):
        self.assertEqual(calculate_ats_score(self.resume, ["Python", "React"]), 100.0)

    def test_half_match(self):
        self.assertEqual(calculate_ats_score(self.resume, ["python", "java"]), 50.0)

    def test_not_enough_experience(self):
        self.assertEqual(calculate_ats_score(self.resume, ["python"], min_experience=5), 0.0)


if __name__ == "__main__":
    unittest.main()
