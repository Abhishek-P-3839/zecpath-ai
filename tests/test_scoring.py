import unittest

from scoring.scoring import combine_scores, get_decision


class TestScoring(unittest.TestCase):
    def test_combine_scores(self):
        scores = {"ats": 80, "hr": 70, "technical": 60, "machine_test": 75}
        self.assertEqual(combine_scores(scores), 69.0)

    def test_decisions(self):
        self.assertEqual(get_decision(85), "selected")
        self.assertEqual(get_decision(55), "hold")
        self.assertEqual(get_decision(20), "rejected")


if __name__ == "__main__":
    unittest.main()
