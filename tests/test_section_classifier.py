"""Automated tests for the Day 8 resume section classifier.

Run:  python -m unittest tests.test_section_classifier -v
"""
import tempfile
import unittest
from pathlib import Path

from parsers.section_classifier import (classify_lines, detect_heading, score_line,
                                        segment_file, segment_resume)
from parsers.section_eval import evaluate, load_labeled, load_manifest
from tests import sample_builder as sb
from tests.labeled_sample_builder import OUT_DIR as LABELED_DIR
from tests.labeled_sample_builder import build_all


def sections_of(text, mode="hybrid"):
    """Helper: {line_text: section} for a small resume text."""
    return {tag.text: tag.section for tag in classify_lines(text, mode)}


class HeadingDetectionTests(unittest.TestCase):
    def test_plain_heading(self):
        self.assertEqual(detect_heading("Experience").labels, ["experience"])

    def test_heading_variations(self):
        for line, expected in [("WORK EXPERIENCE", "experience"), ("Technical Skills:", "skills"),
                               ("Academic Background", "education"), ("PROFESSIONAL SUMMARY", "summary"),
                               ("Licenses & Certifications", "certifications"),
                               ("Academic Projects", "projects"), ("3. Core Competencies", "skills")]:
            with self.subTest(line=line):
                self.assertEqual(detect_heading(line).labels, [expected])

    def test_typos_are_tolerated(self):
        self.assertEqual(detect_heading("Experiance").labels, ["experience"])
        self.assertEqual(detect_heading("Educaton").labels, ["education"])

    def test_combined_heading_gives_two_labels(self):
        self.assertEqual(detect_heading("CERTIFICATIONS & SKILLS").labels, ["certifications", "skills"])
        self.assertEqual(detect_heading("Skills Education").labels, ["skills", "education"])

    def test_inline_heading_keeps_its_content(self):
        heading = detect_heading("Skills: Python, SQL, Git")
        self.assertEqual(heading.labels, ["skills"])
        self.assertEqual(heading.inline, "Python, SQL, Git")
        self.assertEqual(detect_heading("Skills | Python, SQL").labels, ["skills"])

    def test_inline_sub_labels_are_not_headings(self):
        self.assertIsNone(detect_heading("Tech stack: React, Node.js, MongoDB"))
        self.assertIsNone(detect_heading("Languages: Python, JavaScript, SQL"))
        self.assertIsNone(detect_heading("Experience: 5 years in marketing"))

    def test_normal_lines_are_not_headings(self):
        for line in ["- Built REST APIs with Flask", "Project Management: Agile, Scrum",
                     "Senior Project Analyst | Apex Digital January 2023 - Present",
                     "Python, SQL, Git", "Degree | University", "", "Skilled in many things."]:
            with self.subTest(line=line):
                self.assertIsNone(detect_heading(line))


class ScoreLineTests(unittest.TestCase):
    def best(self, text):
        scores = score_line(text)
        return max(scores, key=scores.get)

    def test_contact_line_is_header(self):
        self.assertEqual(self.best("Pune | +91 91234 56780 | rahul@example.com"), "header")

    def test_skill_list_is_skills(self):
        self.assertEqual(self.best("Python, NumPy, Pandas, scikit-learn, SQL, Git"), "skills")

    def test_date_range_job_line_is_experience(self):
        self.assertEqual(self.best("Software Engineer at Acme Pvt Ltd  Jan 2022 - Present"), "experience")

    def test_action_verb_bullet_is_experience(self):
        self.assertEqual(self.best("- Led a team of 5 engineers and cut costs by 20%"), "experience")

    def test_degree_line_is_education(self):
        self.assertEqual(self.best("B.Tech Computer Science, Anna University, 2025"), "education")

    def test_education_with_dates_is_not_a_job(self):
        self.assertEqual(self.best("JNTU Hyderabad, 2021 - 2025, CGPA 8.9"), "education")

    def test_certificate_line_is_certifications(self):
        self.assertEqual(self.best("Google Data Analytics Professional Certificate"), "certifications")

    def test_tech_stack_line_is_projects(self):
        self.assertEqual(self.best("Tech stack: Python, TensorFlow, Flask"), "projects")

    def test_objective_sentence_is_summary(self):
        self.assertEqual(self.best("Motivated fresher seeking a role to apply my Python skills."), "summary")

    def test_hobbies_is_other(self):
        self.assertEqual(self.best("Hobbies: chess, hiking"), "other")

    def test_short_be_is_not_a_degree(self):
        self.assertEqual(score_line("This will be great")["education"], 0.0)


class ClassifyLinesTests(unittest.TestCase):
    def test_headings_decide_the_section(self):
        text = "Priya Nair\nExperience\n- Built REST APIs\nEducation\nB.Sc Computer Science"
        result = sections_of(text)
        self.assertEqual(result["- Built REST APIs"], "experience")
        self.assertEqual(result["B.Sc Computer Science"], "education")
        self.assertEqual(result["Priya Nair"], "header")

    def test_missing_headings_use_content(self):
        text = ("Ananya Rao\nananya@example.com | +91 90000 11122\n"
                "Python, NumPy, Pandas, SQL, Git\nB.Tech Computer Science\nJNTU Hyderabad, 2021 - 2025, CGPA 8.9")
        result = sections_of(text)
        self.assertEqual(result["Python, NumPy, Pandas, SQL, Git"], "skills")
        self.assertEqual(result["JNTU Hyderabad, 2021 - 2025, CGPA 8.9"], "education")

    def test_combined_heading_splits_by_content(self):
        text = ("Education\nB.A. in Marketing, DePaul University 2018\n"
                "CERTIFICATIONS & SKILLS\nCertifications: HubSpot Certified\n"
                "Platforms: Salesforce, HubSpot, Marketo, Tableau, Google Ads")
        result = sections_of(text)
        self.assertEqual(result["Certifications: HubSpot Certified"], "certifications")
        self.assertEqual(result["Platforms: Salesforce, HubSpot, Marketo, Tableau, Google Ads"], "skills")

    def test_wrapped_line_stays_with_previous_line(self):
        text = ("Meera Iyer\nmeera@example.com\n"
                "Web Development Intern at Marina Softech Pvt Ltd  Jan 2025 - Jun 2025\n"
                "- Built reusable React components for a dashboard that\nreduced page load time by 30%")
        result = sections_of(text)
        self.assertEqual(result["reduced page load time by 30%"], "experience")

    def test_blank_lines_are_skipped(self):
        tags = classify_lines("Skills\n\nPython, SQL\n\n")
        self.assertEqual([t.line_no for t in tags], [1, 3])

    def test_rules_mode_labels_unheaded_top_as_header(self):
        result = sections_of("Python, SQL, Git\nExperience\n- Built things", mode="rules")
        self.assertEqual(result["Python, SQL, Git"], "header")      # the known weakness of rules only

    def test_invalid_mode_raises(self):
        with self.assertRaises(ValueError):
            classify_lines("Skills\nPython", mode="magic")

    def test_empty_text_returns_nothing(self):
        self.assertEqual(classify_lines(""), [])
        self.assertEqual(classify_lines(None), [])


class SegmentResumeTests(unittest.TestCase):
    TEXT = ("Rahul Kumar\nrahul@example.com | 99999 00000\nSummary\nFresher Python developer.\n"
            "Skills\nPython, SQL, Git\nExperience\nIntern at Demo Corp\n- Built small REST APIs")

    def test_result_has_all_parts(self):
        result = segment_resume(self.TEXT)
        for key in ("sections", "blocks", "line_tags", "headings", "warnings"):
            self.assertIn(key, result)

    def test_section_text_excludes_heading_lines(self):
        result = segment_resume(self.TEXT)
        self.assertEqual(result["sections"]["skills"], "Python, SQL, Git")
        self.assertNotIn("Skills", result["sections"]["skills"])

    def test_blocks_cover_line_ranges(self):
        blocks = segment_resume(self.TEXT)["blocks"]
        self.assertEqual(blocks[0]["section"], "header")
        self.assertEqual((blocks[0]["start_line"], blocks[0]["end_line"]), (1, 2))
        self.assertEqual([b["section"] for b in blocks], ["header", "summary", "skills", "experience"])

    def test_missing_section_gives_warning(self):
        warnings = segment_resume(self.TEXT)["warnings"]
        self.assertTrue(any("education" in w for w in warnings))

    def test_no_headings_gives_warning(self):
        result = segment_resume("Ananya Rao\nPython, NumPy, Pandas, SQL, Git")
        self.assertTrue(any("No headings" in w for w in result["warnings"]))

    def test_empty_text_gives_warning(self):
        self.assertTrue(any("Empty" in w for w in segment_resume("")["warnings"]))

    def test_segment_file_reads_a_pdf(self):
        with tempfile.TemporaryDirectory() as tmp:
            sb.build_all(tmp)
            result = segment_file(Path(tmp) / "sample_simple.pdf")
        self.assertEqual(result["source_file"], "sample_simple.pdf")
        self.assertIn("skills", result["sections"])
        self.assertIn("experience", result["sections"])


class LabeledDataAndAccuracyTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        build_all()

    def test_labeled_files_match_manifest(self):
        for item in load_manifest(LABELED_DIR):
            text, gold = load_labeled(LABELED_DIR / f"{item['name']}.labeled.txt")
            self.assertTrue(gold, item["name"])
            self.assertEqual(len([ln for ln in text.split("\n") if ln.strip()]), len(gold), item["name"])

    def test_at_least_ten_labeled_samples_with_a_holdout_set(self):
        manifest = load_manifest(LABELED_DIR)
        self.assertGreaterEqual(len(manifest), 10)
        self.assertTrue(any(item["split"] == "holdout" for item in manifest))

    def test_hybrid_accuracy_is_high_on_holdout(self):
        result = evaluate("hybrid", ("holdout",), LABELED_DIR)
        self.assertGreaterEqual(result["accuracy"], 0.90)

    def test_hybrid_beats_rules_only(self):
        hybrid = evaluate("hybrid", labeled_dir=LABELED_DIR)["accuracy"]
        rules = evaluate("rules", labeled_dir=LABELED_DIR)["accuracy"]
        self.assertGreater(hybrid, rules)

    def test_evaluation_result_has_per_section_scores(self):
        result = evaluate("hybrid", labeled_dir=LABELED_DIR)
        self.assertIn("experience", result["per_section"])
        self.assertGreater(result["macro_f1"], 0.8)


if __name__ == "__main__":
    unittest.main()
