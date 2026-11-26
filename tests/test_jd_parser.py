import unittest
from pathlib import Path

from parsers.jd_parser import (
    build_ai_profile,
    detect_jd_heading,
    extract_education,
    extract_skills,
    find_years,
    normalize_jd_text,
    normalize_role,
    normalize_skill,
    parse_job_description,
    split_jd_sections,
)
from utils.schema_validator import get_errors

JD_DIR = Path(__file__).resolve().parent.parent / "data" / "job_descriptions"


def read_jd(name):
    return (JD_DIR / name).read_text(encoding="utf-8")


def skills_of(text):
    """{normalized_name: importance} for a piece of JD text."""
    sections = split_jd_sections(normalize_jd_text(text))
    return {s["normalized_name"]: s["importance"] for s in extract_skills(sections)}


class TestNormalizeText(unittest.TestCase):
    def test_html_and_bullets_are_cleaned(self):
        raw = "<ul><li>Build APIs &amp; tools</li></ul>\n\u2022 Write tests\n1. Review code"
        out = normalize_jd_text(raw)
        self.assertIn("- Build APIs & tools", out)
        self.assertIn("- Write tests", out)
        self.assertIn("- Review code", out)
        self.assertNotIn("<", out)

    def test_smart_punctuation_and_spaces(self):
        out = normalize_jd_text("3\u20135   years   of   \u201cexperience\u201d")
        self.assertEqual(out, '3-5 years of "experience"')

    def test_empty_text(self):
        self.assertEqual(normalize_jd_text(None), "")


class TestSections(unittest.TestCase):
    def test_detect_heading(self):
        self.assertEqual(detect_jd_heading("Key Responsibilities:"), "responsibilities")
        self.assertEqual(detect_jd_heading("NICE TO HAVE"), "preferred")
        self.assertIsNone(detect_jd_heading("- Requirements gathering"))
        self.assertIsNone(detect_jd_heading("We need a developer"))

    def test_inline_heading(self):
        sections = split_jd_sections("Title\nRequired Skills: Python, Java")
        self.assertEqual(sections["requirements"], "Python, Java")


class TestSynonyms(unittest.TestCase):
    def test_skill_synonyms(self):
        self.assertEqual(normalize_skill("ReactJS"), "react")
        self.assertEqual(normalize_skill("k8s"), "kubernetes")
        self.assertEqual(normalize_skill("Amazon Web Services"), "aws")
        self.assertEqual(normalize_skill("Postgres"), "postgresql")
        self.assertIsNone(normalize_skill("underwater basket weaving"))

    def test_role_variations(self):
        self.assertEqual(normalize_role("MERN Stack Developer"), "full stack developer")
        self.assertEqual(normalize_role("Front-End Engineer"), "frontend developer")
        self.assertEqual(normalize_role("Customer Care Executive"), "customer support executive")
        self.assertIsNone(normalize_role("Chief Happiness Officer"))

    def test_java_is_not_javascript(self):
        self.assertEqual(list(skills_of("We use JavaScript and React")), ["javascript", "react"])

    def test_sql_is_not_found_inside_other_words(self):
        found = skills_of("Experience with MySQL and NoSQL stores")
        self.assertIn("mysql", found)
        self.assertNotIn("sql", found)

    def test_special_character_skills(self):
        found = skills_of("Skills: C++, C#, .NET and Node.js.")
        for name in ("c++", "c#", ".net", "node.js"):
            self.assertIn(name, found)

    def test_react_native_is_not_react(self):
        found = skills_of("Build apps with React Native")
        self.assertIn("react native", found)
        self.assertNotIn("react", found)


class TestSkillImportance(unittest.TestCase):
    def test_preferred_section(self):
        found = skills_of("Requirements:\n- Python\nNice to Have:\n- Docker")
        self.assertEqual(found, {"python": "must_have", "docker": "good_to_have"})

    def test_inline_cue(self):
        found = skills_of("Requirements:\n- Python\n- AWS is a plus")
        self.assertEqual(found["aws"], "good_to_have")

    def test_must_have_wins_over_preferred(self):
        found = skills_of("Requirements:\n- Python\nPreferred:\n- Python")
        self.assertEqual(found["python"], "must_have")

    def test_years_and_proficiency_for_one_skill(self):
        sections = split_jd_sections("Requirements:\n- 3+ years of strong experience in Django")
        skill = extract_skills(sections)[0]
        self.assertEqual((skill["min_years"], skill["proficiency"]), (3, "advanced"))


class TestYears(unittest.TestCase):
    def test_find_years(self):
        self.assertEqual(find_years("3-5 years of experience"), (3, 5))
        self.assertEqual(find_years("3 to 5 yrs"), (3, 5))
        self.assertEqual(find_years("5+ years"), (5, None))
        self.assertEqual(find_years("at least 2 years"), (2, None))
        self.assertEqual(find_years("up to 1 year of experience"), (0, 1))
        self.assertIsNone(find_years("great team"))


class TestEducation(unittest.TestCase):
    def test_lowest_level_is_used(self):
        self.assertEqual(extract_education("Bachelor's or Master's degree")["min_level"], "bachelor")

    def test_masters_degree_is_not_bachelor(self):
        self.assertEqual(extract_education("Master's degree in Computer Science")["min_level"], "master")

    def test_any_degree_means_bachelor(self):
        self.assertEqual(extract_education("MBA or any degree")["min_level"], "bachelor")

    def test_scrum_master_is_not_education(self):
        self.assertIsNone(extract_education("Certified Scrum Master")["min_level"])

    def test_preferred_fields(self):
        text = "B.Tech in Computer Science or Information Technology"
        fields = extract_education(text)["preferred_fields"]
        self.assertEqual(fields, ["Computer Science", "Information Technology"])


class TestParseJobDescription(unittest.TestCase):
    def test_mern_job(self):
        job = parse_job_description(
            read_jd("jd_mern_developer.txt"), job_id="job_0002", company_id="comp_0001")
        self.assertEqual(job["job_id"], "job_0002")
        self.assertEqual(job["normalized_title"], "full stack developer")
        self.assertEqual(job["role_category"], "technical")
        self.assertEqual(job["employment_type"], "full_time")
        self.assertEqual(job["work_mode"], "hybrid")
        self.assertEqual(job["location"], {"city": "Kochi", "state": "Kerala", "country": "India"})
        self.assertEqual(job["openings"], 2)
        exp = job["requirements"]["experience"]
        self.assertEqual((exp["min_years"], exp["max_years"], exp["level"]), (3, 5, "mid"))
        self.assertEqual(job["requirements"]["education"]["min_level"], "bachelor")
        found = {s["normalized_name"]: s["importance"] for s in job["requirements"]["skills"]}
        self.assertEqual(found["react"], "must_have")
        self.assertEqual(found["aws"], "good_to_have")

    def test_messy_html_job(self):
        job = parse_job_description(read_jd("jd_senior_python_messy.txt"))
        self.assertEqual(job["title"], "Sr. Python Developer")
        self.assertEqual(job["employment_type"], "contract")
        self.assertEqual(job["requirements"]["experience"]["level"], "senior")
        self.assertEqual(len(job["responsibilities"]), 3)
        cert = job["requirements"]["certifications"][0]
        self.assertEqual((cert["name"], cert["required"]), ("AWS Certified Solutions Architect", False))

    def test_non_technical_job(self):
        job = parse_job_description(read_jd("jd_hr_executive.txt"))
        self.assertEqual(job["role_category"], "non_technical")
        self.assertEqual(job["requirements"]["languages"], ["English", "Malayalam"])
        exp = job["requirements"]["experience"]
        self.assertEqual((exp["min_years"], exp["max_years"], exp["level"]), (0, 1, "fresher"))

    def test_internship_job(self):
        job = parse_job_description(read_jd("jd_data_analyst_intern.txt"))
        self.assertEqual(job["employment_type"], "internship")
        self.assertEqual(job["requirements"]["experience"]["level"], "intern")
        self.assertEqual(job["work_mode"], "remote")

    def test_lead_generation_is_not_a_lead_level(self):
        text = "Lead Generation Executive\nRequirements:\n- 1 year of experience in sales"
        job = parse_job_description(text)
        self.assertNotEqual(job["requirements"]["experience"]["level"], "lead")

    def test_missing_ids_get_defaults(self):
        job = parse_job_description("Python Developer\nRequirements:\n- Python")
        self.assertTrue(job["job_id"].startswith("job_"))
        self.assertEqual(job["company_id"], "comp_unknown")

    def test_same_text_gives_same_job_id(self):
        text = "Python Developer\nRequirements:\n- Python"
        self.assertEqual(parse_job_description(text)["job_id"], parse_job_description(text)["job_id"])

    def test_empty_text_raises(self):
        with self.assertRaises(ValueError):
            parse_job_description("   ")

    def test_all_sample_jds_match_the_job_schema(self):
        files = sorted(JD_DIR.glob("*.txt"))
        self.assertGreaterEqual(len(files), 4)
        for path in files:
            job = parse_job_description(path.read_text(encoding="utf-8"))
            self.assertEqual(get_errors(job, "job"), [], path.name)


class TestAiProfile(unittest.TestCase):
    def test_profile_content(self):
        job = parse_job_description(read_jd("jd_mern_developer.txt"), job_id="job_0002")
        profile = build_ai_profile(job)
        self.assertEqual(profile["job_id"], "job_0002")
        self.assertIn("react", profile["must_have_skills"])
        self.assertIn("aws", profile["good_to_have_skills"])
        self.assertEqual(profile["keywords"][0], "full stack developer")
        self.assertIn("Must have:", profile["summary"])
        self.assertIn("3-5 years", profile["summary"])
        self.assertEqual(len(profile["keywords"]), len(set(profile["keywords"])))


if __name__ == "__main__":
    unittest.main()
