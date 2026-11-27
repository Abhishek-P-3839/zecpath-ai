"""Day 11 tests: education parser, academic profile and education relevance.

Run:  python -m unittest tests.test_education -v

`TODAY` is fixed so the tests give the same answer every day.
The resume lines used below are real examples from data/labeled_resumes/.
"""

import json
import unittest
from datetime import date
from pathlib import Path

from jsonschema import Draft7Validator

from ats_engine.weights import load_config
from parsers.academic_profile import build_academic_profile, find_highest_degree
from parsers.education_parser import (
    parse_certifications,
    parse_education,
    parse_from_resume_text,
    tag_certification,
    to_schema_certifications,
    to_schema_education,
)
from parsers.education_relevance import (
    CERT_BONUS_MAX,
    DEFAULT_CONFIG,
    field_relation,
    merged_config,
    rate_certification,
    job_cert_view,
    required_level,
    score_certifications,
    score_education,
    score_education_with_certifications,
)
from utils.schema_validator import SCHEMA_DIR, load_json

TODAY = date(2026, 6, 15)
LABELED_DIR = Path("data/labeled_resumes")

JOB = {
    "title": "MERN Stack Developer",
    "normalized_title": "full stack developer",
    "role_category": "technical",
    "must_have_skills": ["react", "node.js", "mongodb"],
    "good_to_have_skills": ["aws", "docker"],
    "education_min_level": "bachelor",
    "preferred_fields": ["Computer Science", "Information Technology"],
}


def entry(level="bachelor", field="Computer Science", in_progress=False, degree="B.Tech"):
    return {
        "degree": degree,
        "level": level,
        "field_of_study": field,
        "field_category": None,
        "institution": "X College",
        "start_year": None,
        "end_year": 2021,
        "in_progress": in_progress,
        "grade": None,
    }


def parse_one(text):
    entries, _warnings = parse_education(text, TODAY)
    return entries


def labeled_text(name):
    """Plain resume text of a labeled sample (the section label in front of each line is removed)."""
    lines = (LABELED_DIR / name).read_text(encoding="utf-8").splitlines()
    return "\n".join(line.split("\t", 1)[1] for line in lines if "\t" in line)


# =========================================================================== parser: education
class EducationParserTests(unittest.TestCase):
    def test_simple_us_format(self):
        e = parse_one("B.S. in Computer Science - University of Texas at Dallas 2021")[0]
        self.assertEqual((e["degree"], e["level"]), ("B.Sc", "bachelor"))
        self.assertEqual(e["field_of_study"], "Computer Science")
        self.assertEqual(e["institution"], "University of Texas at Dallas")
        self.assertEqual(e["end_year"], 2021)

    def test_degree_name_repeated_in_brackets_keeps_the_field(self):
        """Real bug found on Day 11: '(BBA) in Operations Management' used to lose the field."""
        e = parse_one(
            "Bachelor of Business Administration (BBA) in Operations Management Graduated May 2020\n"
            "University of Mumbai"
        )[0]
        self.assertEqual(e["degree"], "BBA")
        self.assertEqual(e["field_of_study"], "Operations Management")
        self.assertEqual((e["institution"], e["end_year"]), ("University of Mumbai", 2020))

    def test_year_range_cgpa_and_school_entry(self):
        entries = parse_one(
            "B.Tech in Computer Science, Savitribai Phule Pune University\n"
            "CGPA: 8.4/10 | 2021 - 2025\n"
            "Higher Secondary (HSC), Fergusson College, 2021, 88%"
        )
        self.assertEqual(len(entries), 2)
        btech, hsc = entries
        self.assertEqual((btech["start_year"], btech["end_year"]), (2021, 2025))
        self.assertEqual(btech["grade"]["value"], 8.4)
        self.assertFalse(btech["in_progress"])
        self.assertEqual(
            (hsc["level"], hsc["institution"]), ("higher_secondary", "Fergusson College")
        )

    def test_degree_forms_are_normalized(self):
        cases = {
            "B.E. Computer Science, Anna University, 2021": ("B.E", "bachelor"),
            "M.Sc Statistics, University of Delhi, 2019": ("M.Sc", "master"),
            "MBA Marketing, Calcutta University, 2021": ("MBA", "master"),
            "B.Com, St. Xavier's College, 2019": ("B.Com", "bachelor"),
            "B.Eng. Computer Engineering, University of Waterloo, 2018": ("B.E", "bachelor"),
            "B.F.A. Graphic Design, California College of the Arts, 2017": ("B.F.A", "bachelor"),
            "PhD Physics, IISc Bangalore, 2015": ("PhD", "doctorate"),
        }
        for text, expected in cases.items():
            e = parse_one(text)[0]
            self.assertEqual((e["degree"], e["level"]), expected, text)

    def test_field_names_are_normalized(self):
        self.assertEqual(
            parse_one("B.Tech CSE, ABC University, 2020")[0]["field_of_study"], "Computer Science"
        )
        self.assertEqual(
            parse_one(
                "B.Tech Computer Science and Engineering\nJNTU Hyderabad, 2021 - 2025, CGPA 8.9"
            )[0]["field_of_study"],
            "Computer Science",
        )

    def test_institution_without_a_keyword_word(self):
        e = parse_one(
            "B.Tech Computer Science and Engineering\nJNTU Hyderabad, 2021 - 2025, CGPA 8.9"
        )[0]
        self.assertEqual(e["institution"], "JNTU Hyderabad")

    def test_in_progress_degrees(self):
        for text in (
            "B.Tech Computer Science, ABC University, Expected 2027",
            "B.Tech Computer Science, ABC University, 2023 - Present",
            "B.Tech Computer Science, ABC University, pursuing",
        ):
            self.assertTrue(parse_one(text)[0]["in_progress"], text)

    def test_future_end_year_in_the_past_is_finished(self):
        self.assertFalse(
            parse_one("B.Tech Computer Science, ABC University, 2021 - 2025")[0]["in_progress"]
        )

    def test_table_rows_with_header_line(self):
        entries = parse_one(
            "Degree | University\nM.Sc Data Science | Kerala University\n"
            "B.Sc Statistics | Mahatma Gandhi University"
        )
        self.assertEqual(
            [(e["degree"], e["field_of_study"]) for e in entries],
            [("M.Sc", "Data Science"), ("B.Sc", "Statistics")],
        )
        self.assertEqual(entries[0]["institution"], "Kerala University")

    def test_missing_parts_give_warnings_not_errors(self):
        entries, warnings = parse_education("B.Com, St. Xavier's College, 2019", TODAY)
        self.assertIsNone(entries[0]["field_of_study"])
        self.assertTrue(any("field of study" in w for w in warnings))

    def test_empty_and_nonsense_text(self):
        self.assertEqual(parse_education("", TODAY), ([], []))
        entries, warnings = parse_education("I love long walks on the beach", TODAY)
        self.assertEqual(entries, [])
        self.assertTrue(warnings)


# =========================================================================== parser: certifications
class CertificationParserTests(unittest.TestCase):
    def test_catalog_certifications_are_normalized(self):
        certs = parse_certifications(
            "AWS Certified Solutions Architect - Associate\n"
            "HashiCorp Certified: Terraform Associate\n"
            "Certified ScrumMaster (CSM) - Scrum Alliance"
        )
        names = [c["name"] for c in certs]
        self.assertEqual(
            names,
            [
                "AWS Certified Solutions Architect – Associate",
                "HashiCorp Certified: Terraform Associate",
                "Certified ScrumMaster (CSM)",
            ],
        )
        self.assertEqual(certs[0]["issuer"], "Amazon Web Services")
        self.assertEqual(certs[0]["categories"], ["cloud"])
        self.assertEqual(certs[2]["categories"], ["project_management"])

    def test_course_from_a_learning_platform(self):
        c = parse_certifications("Python for Everybody - Coursera")[0]
        self.assertEqual(
            (c["name"], c["issuer"], c["kind"]), ("Python for Everybody", "Coursera", "course")
        )

    def test_year_and_certified_in_brackets(self):
        c = parse_certifications("AWS Cloud Practitioner (Certified), 2024")[0]
        self.assertEqual(c["name"], "AWS Certified Cloud Practitioner")
        self.assertEqual(c["level"], "foundational")
        self.assertEqual(c["issue_date"], "2024-01")

    def test_several_certifications_on_one_labelled_line(self):
        certs = parse_certifications(
            "Certifications: Oracle Certified Associate Java SE 8, "
            "AWS Solutions Architect Associate (SAA-C03)"
        )
        self.assertEqual(len(certs), 2)
        self.assertEqual(
            certs[0]["name"], "Oracle Certified Associate Java SE 8"
        )  # NOT renamed to Professional
        self.assertEqual(certs[0]["level"], "associate")
        self.assertEqual(certs[1]["issuer"], "Amazon Web Services")

    def test_comma_inside_one_certification_is_not_split(self):
        self.assertEqual(len(parse_certifications("AWS Cloud Practitioner (Certified), 2024")), 1)

    def test_expiry_marks_a_certification_as_expired(self):
        c = parse_certifications(
            "CompTIA Security+ - CompTIA, issued Jan 2020, expires Jan 2023", TODAY
        )[0]
        self.assertEqual(c["expiry_date"], "2023-01")
        self.assertTrue(c["expired"])

    def test_duplicates_are_removed_and_empty_text_is_fine(self):
        self.assertEqual(len(parse_certifications("PMP\nProject Management Professional (PMP)")), 1)
        self.assertEqual(parse_certifications(""), [])

    def test_tagging_with_relevance_categories(self):
        self.assertEqual(
            tag_certification("Google Data Analytics Professional Certificate")["primary_category"],
            "data_ai",
        )
        self.assertEqual(tag_certification("CISSP")["categories"], ["cybersecurity"])
        self.assertEqual(tag_certification("Basket Weaving")["categories"], ["other"])

    def test_marketing_software_is_not_software_development(self):
        self.assertEqual(
            tag_certification("HubSpot Marketing Software Certified")["primary_category"],
            "business",
        )


# =========================================================================== whole resumes
class ResumeTextTests(unittest.TestCase):
    def test_labeled_resumes_end_to_end(self):
        r = parse_from_resume_text(labeled_text("alex.labeled.txt"), TODAY)
        self.assertEqual(r["education"][0]["field_of_study"], "Operations Management")
        self.assertEqual(r["highest_level"], "bachelor")
        self.assertEqual(len(r["certifications"]), 2)

    def test_inline_education_heading(self):
        r = parse_from_resume_text(labeled_text("dev_inline_headings.labeled.txt"), TODAY)
        e = r["education"][0]
        self.assertEqual(
            (e["degree"], e["field_of_study"], e["institution"]),
            ("B.E", "Information Technology", "VIT Vellore"),
        )
        self.assertNotIn("No 'education' section detected.", r["warnings"])

    def test_certifications_hidden_under_a_mixed_heading(self):
        r = parse_from_resume_text(labeled_text("marcus.labeled.txt"), TODAY)
        self.assertEqual(len(r["certifications"]), 2)

    def test_resume_without_education(self):
        r = parse_from_resume_text(labeled_text("sample_simple.labeled.txt"), TODAY)
        self.assertEqual(r["education"], [])
        self.assertIsNone(r["highest_level"])
        self.assertTrue(r["warnings"])


# =========================================================================== academic profile
class AcademicProfileTests(unittest.TestCase):
    def setUp(self):
        text = (
            "Education\nM.Sc Data Science, ABC University, 2023\nB.Tech Computer Science, XYZ College, 2021\n"
            "PhD Statistics, Some University, Expected 2028\nHigher Secondary (HSC), Delhi School, 2017\n"
            "Certifications\nAWS Certified Cloud Practitioner\nPython for Everybody - Coursera\n"
            "CompTIA Security+ - CompTIA, expires Jan 2023\n"
        )
        self.result = parse_from_resume_text(text, TODAY)
        self.profile = build_academic_profile(self.result)

    def test_highest_degree_is_the_highest_finished_one(self):
        top = self.profile["highest_degree"]
        self.assertEqual((top["degree"], top["level"]), ("M.Sc", "master"))
        self.assertEqual(self.profile["highest_completed_level"], "master")
        self.assertEqual(
            self.profile["highest_level"], "doctorate"
        )  # parser value includes in-progress

    def test_primary_field_and_graduation_year(self):
        self.assertEqual(self.profile["primary_field"], "Data Science")
        self.assertEqual(self.profile["primary_field_category"], "computer_it")
        self.assertEqual(self.profile["latest_graduation_year"], 2023)  # the PhD is not finished

    def test_in_progress_degrees(self):
        self.assertEqual([d["degree"] for d in self.profile["in_progress_degrees"]], ["PhD"])

    def test_certifications_and_counts(self):
        self.assertEqual(
            self.profile["certification_categories"],
            ["cloud", "cybersecurity", "software_development"],
        )
        self.assertEqual(
            self.profile["counts"],
            {
                "education_entries": 4,
                "degrees": 3,
                "in_progress": 1,
                "certifications": 2,
                "courses": 1,
                "expired_certifications": 1,
            },
        )

    def test_schema_lists_use_the_existing_converters(self):
        self.assertEqual(self.profile["schema_education"], to_schema_education(self.result))
        self.assertEqual(
            self.profile["schema_certifications"], to_schema_certifications(self.result)
        )
        self.assertNotIn("field_category", self.profile["schema_education"][0])

    def test_profile_is_json_ready(self):
        self.assertEqual(json.loads(json.dumps(self.profile))["primary_field"], "Data Science")

    def test_finished_beats_in_progress_even_if_lower(self):
        entries = [entry("bachelor"), entry("master", in_progress=True)]
        self.assertEqual(find_highest_degree(entries)["level"], "bachelor")

    def test_empty_result_gives_an_empty_but_complete_profile(self):
        p = build_academic_profile(
            {"education": [], "certifications": [], "highest_level": None, "warnings": ["x"]}
        )
        self.assertIsNone(p["highest_degree"])
        self.assertIsNone(p["primary_field"])
        self.assertIsNone(p["latest_graduation_year"])
        self.assertEqual(p["counts"]["education_entries"], 0)
        self.assertEqual(p["warnings"], ["x"])

    def test_field_falls_back_to_a_lower_degree(self):
        e1, e2 = entry("master", field=None), entry("bachelor", field="Mathematics")
        e1["field_category"], e2["field_category"] = None, "science"
        p = build_academic_profile(
            {"education": [e1, e2], "certifications": [], "highest_level": "master"}
        )
        self.assertEqual(
            (p["primary_field"], p["primary_field_category"]), ("Mathematics", "science")
        )


# =========================================================================== relevance: education
class EducationScoreTests(unittest.TestCase):
    def score(self, entries, job=JOB):
        return score_education(entries, job, load_config()["education"])

    def test_config_defaults_match_ats_weights_json(self):
        self.assertEqual(merged_config(load_config()["education"]), DEFAULT_CONFIG)

    def test_perfect_match_is_100(self):
        r = self.score([entry()])
        self.assertEqual((r["status"], r["score"]), ("scored", 100.0))
        self.assertTrue(all(r["reasons"]))

    def test_level_boundaries(self):
        """Equal or higher = full credit; one level below = 0.5; two or more = 0.2 (60% weight)."""
        self.assertEqual(self.score([entry("master")])["score"], 100.0)
        self.assertEqual(self.score([entry("diploma")])["score"], 70.0)  # 0.5*60 + 1.0*40
        self.assertEqual(self.score([entry("higher_secondary")])["score"], 52.0)  # 0.2*60 + 1.0*40
        self.assertEqual(self.score([entry("secondary")])["score"], 52.0)

    def test_master_required_bachelor_is_one_level_below(self):
        job = {**JOB, "education_min_level": "master"}
        self.assertEqual(self.score([entry("bachelor")], job)["score"], 70.0)

    def test_field_tiers(self):
        self.assertEqual(
            self.score([entry(field="Computer Science")])["score"], 100.0
        )  # same field
        self.assertEqual(
            self.score([entry(field="Data Science")])["score"], 88.0
        )  # same category 0.7
        self.assertEqual(self.score([entry(field="Electronics")])["score"], 80.0)  # related 0.5
        self.assertEqual(self.score([entry(field="Commerce")])["score"], 72.0)  # unrelated 0.3

    def test_field_relation(self):
        self.assertEqual(field_relation("CSE", "Computer Science"), "exact")
        self.assertEqual(field_relation("Data Science", "Computer Science"), "same_category")
        self.assertEqual(field_relation("Electronics", "Computer Science"), "related_category")
        self.assertEqual(field_relation("Commerce", "Computer Science"), "different")

    def test_degree_in_progress_counts_less(self):
        done = self.score([entry()])["score"]
        ongoing = self.score([entry(in_progress=True)])
        self.assertEqual(ongoing["score"], 80.0)  # level 0.8*60 + field 1.0*0.8*40
        self.assertLess(ongoing["score"], done)
        self.assertGreater(ongoing["score"], self.score([entry("diploma")])["score"])
        self.assertTrue(any("in progress" in r for r in ongoing["reasons"]))

    def test_finished_lower_degree_plus_ongoing_higher_degree(self):
        job = {**JOB, "education_min_level": "master"}
        r = self.score([entry("bachelor"), entry("master", in_progress=True)], job)
        self.assertEqual(r["details"]["highest_level"], "bachelor")
        self.assertTrue(any("in progress" in x for x in r["reasons"]))

    def test_any_degree_job_scores_the_level_only(self):
        job = {
            "title": "HR Executive",
            "role_category": "non_technical",
            "education_min_level": "bachelor",
            "preferred_fields": [],
        }
        r = self.score([entry(field="Commerce")], job)
        self.assertEqual(r["score"], 100.0)
        self.assertTrue(any("any field" in x for x in r["reasons"]))
        self.assertEqual(self.score([entry("diploma", field="Commerce")], job)["score"], 50.0)

    def test_any_degree_wording_means_bachelor(self):
        self.assertEqual(required_level({"education_min_level": "any degree"}), "bachelor")

    def test_technical_job_without_fields_uses_default_fields(self):
        job = {
            "title": "Developer",
            "role_category": "technical",
            "education_min_level": "bachelor",
        }
        good = self.score([entry(field="Computer Science")], job)
        bad = self.score([entry(field="Commerce")], job)
        self.assertEqual(good["score"], 100.0)
        self.assertEqual(bad["score"], 72.0)
        self.assertEqual(good["details"]["fields_source"], "default")

    def test_missing_job_requirement(self):
        r = self.score([entry()], {"title": "Anything", "role_category": "technical"})
        self.assertEqual((r["status"], r["score"]), ("missing_job", None))

    def test_missing_candidate_education(self):
        for source in (None, [], {"education": []}, "nonsense"):
            r = self.score(source)
            self.assertEqual((r["status"], r["score"]), ("missing_candidate", None), source)

    def test_missing_field_is_skipped_not_penalised(self):
        r = self.score([entry(field=None)])
        self.assertEqual(r["score"], 100.0)
        self.assertTrue(any("Field of study not found" in x for x in r["reasons"]))

    def test_school_stream_does_not_decide_the_field(self):
        """A school 'Science' stream must not beat the real degree field."""
        school = entry("higher_secondary", field="Computer Science")
        degree = entry("bachelor", field="Commerce")
        self.assertEqual(self.score([school, degree])["score"], 72.0)

    def test_accepts_profile_parse_result_and_plain_list(self):
        entries = [entry()]
        for source in (
            entries,
            {"education": entries},
            {"education": entries, "certifications": []},
        ):
            self.assertEqual(self.score(source)["score"], 100.0)

    def test_unknown_level_does_not_crash(self):
        r = self.score([entry(level="weird")])
        self.assertEqual(r["status"], "scored")
        self.assertEqual(r["score"], 52.0)  # no recognised degree = two or more levels below


# =========================================================================== relevance: certifications
def cert(name, categories, level="associate", kind="certification", expired=False, issuer=None):
    return {
        "name": name,
        "issuer": issuer,
        "categories": categories,
        "level": level,
        "kind": kind,
        "expired": expired,
    }


class CertificationScoreTests(unittest.TestCase):
    def test_relevance_levels(self):
        view = job_cert_view(JOB)
        high = rate_certification(
            cert("AWS Certified Developer – Associate", ["cloud", "software_development"]), view
        )
        medium = rate_certification(cert("AWS Certified Solutions Architect", ["cloud"]), view)
        low = rate_certification(cert("Six Sigma Green Belt", ["business"]), view)
        self.assertEqual(
            (high["relevance"], medium["relevance"], low["relevance"]), ("high", "medium", "low")
        )
        self.assertEqual(medium["matched_good_to_have"], ["aws"])
        self.assertTrue(high["reasons"] and medium["reasons"] and low["reasons"])

    def test_must_have_skill_in_the_name_is_high(self):
        r = rate_certification(
            cert("React Developer Certificate", ["software_development"], kind="course"),
            job_cert_view(JOB),
        )
        self.assertEqual(r["relevance"], "high")
        self.assertEqual(r["matched_must_have"], ["react"])

    def test_java_is_not_found_inside_javascript(self):
        job = {**JOB, "must_have_skills": ["java"], "good_to_have_skills": []}
        r = rate_certification(cert("JavaScript Algorithms", ["other"]), job_cert_view(job))
        self.assertEqual(r["matched_must_have"], [])

    def test_points_are_reduced_for_foundational_course_and_expired(self):
        view = job_cert_view(JOB)
        full = rate_certification(
            cert("AWS Certified Developer", ["cloud", "software_development"]), view
        )["points"]
        foundational = rate_certification(
            cert(
                "AWS Certified Developer", ["cloud", "software_development"], level="foundational"
            ),
            view,
        )["points"]
        expired = rate_certification(
            cert("AWS Certified Developer", ["cloud", "software_development"], expired=True), view
        )["points"]
        self.assertEqual((full, foundational, expired), (1.0, 0.7, 0.5))

    def test_role_decides_what_is_relevant(self):
        cissp = cert("CISSP", ["cybersecurity"], level="professional")
        devops = {
            "title": "DevOps Engineer",
            "normalized_title": "devops engineer",
            "must_have_skills": ["docker"],
        }
        data = {
            "title": "Data Analyst",
            "normalized_title": "data analyst",
            "must_have_skills": ["sql"],
        }
        self.assertEqual(rate_certification(cissp, job_cert_view(data))["relevance"], "low")
        cka = cert(
            "Certified Kubernetes Administrator (CKA)", ["devops", "cloud"], level="professional"
        )
        self.assertEqual(rate_certification(cka, job_cert_view(devops))["relevance"], "high")

    def test_overall_score_best_counts_most(self):
        one = score_certifications(
            [cert("React Developer Certificate", ["software_development"])], JOB
        )
        two = score_certifications(
            [
                cert("React Developer Certificate", ["software_development"]),
                cert("Six Sigma Green Belt", ["business"]),
            ],
            JOB,
        )
        self.assertEqual(one["score"], 100.0)
        self.assertEqual(one["counts"], {"high": 1, "medium": 0, "low": 0})
        self.assertEqual(two["score"], 100.0)
        weak = score_certifications([cert("Six Sigma Green Belt", ["business"])], JOB)
        self.assertEqual(weak["score"], 15.0)

    def test_items_are_sorted_best_first(self):
        r = score_certifications(
            [
                cert("Six Sigma Green Belt", ["business"]),
                cert("AWS Certified Developer", ["cloud", "software_development"]),
            ],
            JOB,
        )
        self.assertEqual([i["relevance"] for i in r["items"]], ["high", "low"])

    def test_missing_data(self):
        self.assertEqual(score_certifications([], JOB)["status"], "missing_candidate")
        self.assertIsNone(score_certifications([], JOB)["score"])
        nothing = score_certifications(
            [cert("X", ["cloud"])], {"title": "", "normalized_title": ""}
        )
        self.assertEqual(nothing["status"], "missing_job")


# =========================================================================== relevance: combined
class CombinedScoreTests(unittest.TestCase):
    STRONG = cert("React Developer Certificate", ["software_development"])

    def combined(self, entries, certs, job=JOB):
        return score_education_with_certifications(
            {"education": entries, "certifications": certs}, job, load_config()["education"]
        )

    def test_bonus_is_added_and_capped(self):
        r = self.combined([entry("diploma")], [self.STRONG])  # education 70 + full 10-point bonus
        self.assertEqual(
            (r["education_score"], r["bonus"], r["score"]), (70.0, 5.0, 75.0)
        )  # halved: level not met
        r = self.combined([entry("master", field="Commerce")], [self.STRONG])
        self.assertEqual((r["education_score"], r["bonus"], r["score"]), (72.0, 10.0, 82.0))
        r = self.combined([entry()], [self.STRONG])
        self.assertEqual(r["score"], 100.0)  # never above 100
        self.assertLessEqual(r["bonus"], CERT_BONUS_MAX)

    def test_certifications_never_replace_a_missing_degree(self):
        r = self.combined(
            [], [self.STRONG, cert("AWS Certified Developer", ["cloud", "software_development"])]
        )
        self.assertEqual(r["status"], "missing_candidate")
        self.assertLessEqual(r["score"], CERT_BONUS_MAX)
        self.assertTrue(any("cannot replace" in x for x in r["reasons"]))

    def test_certifications_cannot_lift_a_very_low_degree_to_full_marks(self):
        r = self.combined([entry("secondary", field="Commerce")], [self.STRONG])
        self.assertLess(r["score"], 50)

    def test_no_education_requirement_gives_no_score(self):
        r = self.combined([entry()], [self.STRONG], {"title": "X", "role_category": "technical"})
        self.assertEqual((r["status"], r["score"]), ("missing_job", None))

    def test_no_certifications_means_no_bonus(self):
        r = self.combined([entry()], [])
        self.assertEqual((r["score"], r["bonus"]), (100.0, 0.0))

    def test_formula_text_shows_the_numbers(self):
        r = self.combined([entry("master", field="Commerce")], [self.STRONG])
        self.assertEqual(
            r["formula"], "82.0 = 72.0 (education) + 10.0 (certification bonus, max 10)"
        )


# =========================================================================== the engine uses this module
class EngineDelegationTests(unittest.TestCase):
    def test_engine_education_part_equals_score_education(self):
        from ats_engine.scoring_engine import ATSScoringEngine

        engine = ATSScoringEngine(today=TODAY)
        resume = {"education": {"education": [entry("diploma")], "certifications": []}}
        part = engine._education(resume, JOB)
        direct = score_education(resume["education"], JOB, engine.config["education"])
        self.assertEqual(
            (part["status"], part["score"], part["reasons"]),
            (direct["status"], direct["score"], direct["reasons"]),
        )
        self.assertEqual(
            set(part["details"]), {"required_level", "preferred_fields", "highest_level"}
        )


# =========================================================================== sample resumes validate
class SchemaValidationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.schema = load_json(SCHEMA_DIR / "resume_schema.json")

    def errors(self, items, definition):
        validator = Draft7Validator(
            {"$ref": f"#/definitions/{definition}", "definitions": self.schema["definitions"]}
        )
        return [e.message for item in items for e in validator.iter_errors(item)]

    def test_every_labeled_resume_validates(self):
        files = sorted(LABELED_DIR.glob("*.labeled.txt"))
        self.assertGreaterEqual(len(files), 15)
        for path in files:
            profile = build_academic_profile(parse_from_resume_text(labeled_text(path.name), TODAY))
            self.assertEqual(self.errors(profile["schema_education"], "education"), [], path.name)
            self.assertEqual(
                self.errors(profile["schema_certifications"], "certification"), [], path.name
            )

    def test_every_raw_resume_validates(self):
        from extraction.extractor import SUPPORTED
        from parsers.academic_profile import profile_from_file

        raw = sorted(p for p in Path("data/raw_resumes").iterdir() if p.suffix.lower() in SUPPORTED)
        self.assertTrue(raw)
        for path in raw:
            profile = profile_from_file(path, TODAY)
            self.assertEqual(self.errors(profile["schema_education"], "education"), [], path.name)
            self.assertEqual(
                self.errors(profile["schema_certifications"], "certification"), [], path.name
            )

    def test_extra_fields_would_be_rejected_by_the_schema(self):
        """Why the profile keeps categories out of the schema lists: the schema does not allow them."""
        self.assertTrue(
            self.errors(
                [{**to_schema_education({"education": [entry()]})[0], "field_category": "x"}],
                "education",
            )
        )


if __name__ == "__main__":
    unittest.main()
