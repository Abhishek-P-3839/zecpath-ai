"""Day 10 tests: experience parser + relevance scoring.

Run:  python -m unittest tests.test_experience -v
`TODAY` is fixed so the tests give the same answer every day.
"""
import unittest
from datetime import date

from jsonschema import Draft7Validator

from parsers.experience_parser import (
    compute_total_months, find_gaps, find_overlaps, month_index, parse_date, parse_date_range,
    parse_experience, split_header, to_schema_experience,
)
from parsers.experience_relevance import (
    detect_level, role_similarity, score_experience, seniority_fit,
)
from utils.schema_validator import SCHEMA_DIR, load_json

TODAY = date(2026, 6, 15)

SAMPLE = """Senior Developer | Alpha Tech, Austin, TX  Mar 2022 - Present
- Built REST APIs with Node.js and MongoDB, cutting latency by 30%.
Software Engineer - Beta Systems  06/2019 - 12/2021
- Wrote React front ends.
Junior Developer at Gamma Ltd  2017 - 2018
"""

MERN_JOB = {
    "title": "MERN Stack Developer", "normalized_title": "full stack developer", "level": "mid",
    "min_years": 3, "max_years": 5,
    "must_have_skills": ["node.js", "react", "mongodb", "communication"],
    "good_to_have_skills": ["docker"],
}


class DateTests(unittest.TestCase):
    def test_month_year(self):
        self.assertEqual(parse_date("Jan 2020")[:2], (2020, 1))
        self.assertEqual(parse_date("September, 2021")[:2], (2021, 9))
        self.assertEqual(parse_date("03/2019")[:2], (2019, 3))

    def test_year_only_start_and_end(self):
        self.assertEqual(parse_date("2020", is_end=False)[:2], (2020, 1))
        self.assertEqual(parse_date("2020", is_end=True)[:2], (2020, 12))

    def test_present_is_today(self):
        self.assertEqual(parse_date("Present", today=TODAY)[:2], (2026, 6))
        self.assertEqual(parse_date("till date", today=TODAY)[:2], (2026, 6))

    def test_not_a_date(self):
        self.assertIsNone(parse_date("hello"))

    def test_range_variants(self):
        for text in ("Jan 2020 - Mar 2021", "Jan 2020 \u2013 Mar 2021", "January 2020 to March 2021", "01/2020 - 03/2021"):
            r = parse_date_range(text, TODAY)
            self.assertEqual((r["start"], r["end"]), (month_index(2020, 1), month_index(2021, 3)), text)

    def test_future_end_is_capped(self):
        r = parse_date_range("Jan 2026 - Dec 2030", TODAY)
        self.assertEqual(r["end"], month_index(2026, 6))
        self.assertTrue(r["warnings"])

    def test_end_before_start_warns(self):
        r = parse_date_range("Mar 2021 - Jan 2020", TODAY)
        self.assertTrue(any("before" in w for w in r["warnings"]))


class HeaderTests(unittest.TestCase):
    def test_pipe(self):
        self.assertEqual(split_header("Senior Analyst | Apex Digital Solutions"),
                         ("Senior Analyst", "Apex Digital Solutions", None))

    def test_dash_with_location(self):
        self.assertEqual(split_header("Software Engineer II - Bluebonnet Cloud, Austin, TX"),
                         ("Software Engineer II", "Bluebonnet Cloud", "Austin, TX"))

    def test_at(self):
        self.assertEqual(split_header("Intern at Demo Corp")[:2], ("Intern", "Demo Corp"))

    def test_company_first(self):
        self.assertEqual(split_header("Google - Software Engineer")[:2], ("Software Engineer", "Google"))

    def test_comma_inc_stays_together(self):
        self.assertEqual(split_header("Data Analyst | Acme, Inc.")[1], "Acme, Inc.")


class ParseTests(unittest.TestCase):
    def setUp(self):
        self.result = parse_experience(SAMPLE, TODAY)
        self.jobs = {e["company"]: e for e in self.result["entries"]}

    def test_three_jobs_newest_first(self):
        self.assertEqual([e["company"] for e in self.result["entries"]], ["Alpha Tech", "Beta Systems", "Gamma Ltd"])

    def test_fields(self):
        alpha = self.jobs["Alpha Tech"]
        self.assertEqual(alpha["designation"], "Senior Developer")
        self.assertEqual(alpha["location"], "Austin, TX")
        self.assertEqual(alpha["start_date"], "2022-03")
        self.assertIsNone(alpha["end_date"])
        self.assertTrue(alpha["is_current"])
        self.assertEqual(alpha["duration_months"], 52)          # Mar 2022 .. Jun 2026 inclusive
        self.assertIn("node.js", alpha["skills_used"])
        self.assertEqual(len(alpha["achievements"]), 1)

    def test_numeric_dates(self):
        beta = self.jobs["Beta Systems"]
        self.assertEqual((beta["start_date"], beta["end_date"], beta["duration_months"]), ("2019-06", "2021-12", 31))

    def test_total_and_current(self):
        self.assertEqual(self.result["total_experience_months"], 52 + 31 + 24)
        self.assertEqual(self.result["total_experience_years"], 8.9)
        self.assertEqual(self.result["current_designation"], "Senior Developer")
        self.assertTrue(self.result["is_currently_employed"])

    def test_gaps_found(self):
        gaps = self.result["gaps"]
        self.assertEqual(len(gaps), 1)                      # Jan 2019 .. May 2019 (Gamma ended Dec 2018)
        self.assertEqual((gaps[0]["from"], gaps[0]["to"], gaps[0]["months"]), ("2019-01", "2019-05", 5))
        self.assertEqual(gaps[0]["severity"], "minor")

    def test_empty_text(self):
        r = parse_experience("", TODAY)
        self.assertEqual((r["entries"], r["total_experience_years"]), ([], 0.0))
        self.assertTrue(r["warnings"])

    def test_no_dates(self):
        r = parse_experience("Intern at Demo Corp\nBuilt small APIs", TODAY)
        self.assertEqual(r["entries"][0]["company"], "Demo Corp")
        self.assertEqual(r["entries"][0]["employment_type"], "internship")
        self.assertEqual(r["total_experience_months"], 0)
        self.assertEqual(to_schema_experience(r), [])        # schema needs a start_date

    def test_dates_on_own_line(self):
        r = parse_experience("Acme Corp\nBackend Developer\nJan 2018 - Mar 2019\n- Built APIs", TODAY)
        e = r["entries"][0]
        self.assertEqual((e["designation"], e["company"], e["duration_months"]), ("Backend Developer", "Acme Corp", 15))

    def test_schema_valid(self):
        schema = load_json(SCHEMA_DIR / "resume_schema.json")
        validator = Draft7Validator({"$ref": "#/definitions/experience", "definitions": schema["definitions"]})
        for entry in to_schema_experience(self.result):
            self.assertEqual(list(validator.iter_errors(entry)), [])


class TimelineTests(unittest.TestCase):
    def job(self, company, start, end, kind=None):
        return {"company": company, "designation": "Dev", "employment_type": kind, "is_current": False,
                "_start_index": month_index(*start), "_end_index": month_index(*end)}

    def test_overlap_counted_once(self):
        jobs = [self.job("A", (2020, 1), (2020, 12)), self.job("B", (2020, 7), (2021, 6))]
        self.assertEqual(compute_total_months(jobs), 18)     # Jan 2020 .. Jun 2021, not 24
        overlap = find_overlaps(jobs)[0]
        self.assertEqual((overlap["months"], overlap["kind"]), (6, "review"))

    def test_handover_overlap_is_not_a_problem(self):
        jobs = [self.job("A", (2020, 1), (2020, 6)), self.job("B", (2020, 6), (2021, 6))]
        self.assertEqual(find_overlaps(jobs)[0]["kind"], "handover")

    def test_internship_overlap_is_concurrent(self):
        jobs = [self.job("A", (2020, 1), (2020, 12)), self.job("B", (2020, 3), (2020, 8), "internship")]
        self.assertEqual(find_overlaps(jobs)[0]["kind"], "concurrent")

    def test_back_to_back_has_no_gap(self):
        jobs = [self.job("A", (2020, 1), (2020, 12)), self.job("B", (2021, 1), (2021, 6))]
        self.assertEqual([g for g in find_gaps(jobs, TODAY) if g["type"] == "gap"], [])

    def test_short_gap_ignored_long_gap_major(self):
        short = [self.job("A", (2020, 1), (2020, 12)), self.job("B", (2021, 3), (2021, 6))]   # 2 empty months
        long_ = [self.job("A", (2020, 1), (2020, 12)), self.job("B", (2021, 10), (2022, 6))]  # 9 empty months
        self.assertEqual([g for g in find_gaps(short, TODAY) if g["type"] == "gap"], [])
        gap = [g for g in find_gaps(long_, TODAY) if g["type"] == "gap"][0]
        self.assertEqual((gap["months"], gap["severity"]), (9, "major"))

    def test_gap_since_last_job(self):
        jobs = [self.job("A", (2025, 1), (2025, 12))]
        gaps = find_gaps(jobs, TODAY)
        self.assertEqual((gaps[0]["type"], gaps[0]["months"]), ("current_gap", 6))


class SimilarityTests(unittest.TestCase):
    def test_same_role_different_words(self):
        self.assertEqual(role_similarity("MERN Stack Developer", "Full Stack Engineer"), 1.0)

    def test_close_and_related(self):
        self.assertGreaterEqual(role_similarity("Software Engineer", "Full Stack Developer"), 0.8)
        self.assertGreaterEqual(role_similarity("Python Developer", "Software Engineer"), 0.6)

    def test_unrelated(self):
        self.assertLess(role_similarity("HR Executive", "Full Stack Developer"), 0.2)
        self.assertLess(role_similarity("Mechanical Engineer", "Software Engineer"), 0.3)

    def test_symmetric_and_empty(self):
        self.assertEqual(role_similarity("Data Analyst", "Data Scientist"), role_similarity("Data Scientist", "Data Analyst"))
        self.assertEqual(role_similarity("", "Data Analyst"), 0.0)

    def test_seniority(self):
        self.assertEqual(detect_level("Senior Project Analyst"), "senior")
        self.assertEqual(detect_level("Software Engineer"), "mid")
        self.assertEqual(seniority_fit("mid", "mid"), 1.0)
        self.assertEqual(seniority_fit("intern", "senior"), 0.0)


class RelevanceTests(unittest.TestCase):
    def score(self, text, job=MERN_JOB):
        return score_experience(parse_experience(text, TODAY), job, TODAY)

    def test_relevant_candidate_scores_high(self):
        r = self.score("Full Stack Developer | Acme  Jan 2021 - Present\n- Built React apps with Node.js and MongoDB, Docker")
        self.assertGreaterEqual(r["score"], 75)
        self.assertEqual(r["label"], "strong")
        self.assertEqual(r["must_have_missing"], [])     # 'communication' (soft skill) is not required in bullets

    def test_irrelevant_candidate_scores_zero(self):
        r = self.score("HR Executive | Acme  Jan 2018 - Present\n- Recruited staff and ran payroll")
        self.assertEqual(r["score"], 0)
        self.assertEqual(r["relevant_years"], 0.0)

    def test_old_experience_counts_less(self):
        old = self.score("Full Stack Developer | Acme  2008 - 2013\n- Node.js, React, MongoDB")
        new = self.score("Full Stack Developer | Acme  2021 - 2026\n- Node.js, React, MongoDB")
        self.assertLess(old["effective_years"], new["effective_years"])
        self.assertLess(old["score"], new["score"])

    def test_overlap_not_double_counted(self):
        r = self.score("Full Stack Developer | A  Jan 2022 - Dec 2022\n- React, Node.js, MongoDB\n"
                       "Full Stack Developer | B  Jan 2022 - Dec 2022\n- React, Node.js, MongoDB")
        self.assertLessEqual(r["relevant_years"], 1.0)

    def test_fresher_has_no_experience(self):
        r = self.score("")
        self.assertEqual(r["score"], 0)
        self.assertTrue(any("No dated work experience" in n for n in r["notes"]))

    def test_score_in_range(self):
        for text in ("", SAMPLE):
            self.assertTrue(0 <= self.score(text)["score"] <= 100)


if __name__ == "__main__":
    unittest.main()
