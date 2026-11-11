import os
import unittest

from interview_ai.interview import get_hr_questions, get_technical_level
from screening_ai.screening import build_screening_report
from utils.logger import LOG_FILE, get_logger


class TestOtherModules(unittest.TestCase):
    def test_screening_report(self):
        report = build_screening_report({"education": "B.Tech", "notice_period": "30 days"})
        self.assertEqual(report["answered"], 2)
        self.assertIn("expected_salary", report["missing"])

    def test_interview_level(self):
        self.assertEqual(get_technical_level(1), "basic")
        self.assertEqual(get_technical_level(3), "intermediate")
        self.assertEqual(get_technical_level(8), "advanced")
        self.assertTrue(len(get_hr_questions()) > 0)

    def test_logger_writes_file(self):
        log = get_logger("test_logger")
        log.info("test message")
        self.assertTrue(os.path.exists(LOG_FILE))


if __name__ == "__main__":
    unittest.main()
