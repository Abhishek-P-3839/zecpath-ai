"""Automated tests for the Day 9 skill extraction engine.

Run:  python -m unittest tests.test_skill_extractor -v
"""
import json
import unittest
from collections import defaultdict
from pathlib import Path

from parsers import skill_confidence as conf
from parsers import skill_taxonomy as tx
from parsers.skill_extractor import (_key, extract_skills, extract_skills_from_file,
                                     to_schema_skills)

ROOT = Path(__file__).resolve().parent.parent
RESUME_SCHEMA = json.loads((ROOT / "data" / "schemas" / "resume_schema.json").read_text(encoding="utf-8"))
SKILL_SCHEMA = RESUME_SCHEMA["definitions"]["skill"]["properties"]


def skills_section(*lines):
    """Helper: a tiny resume whose only content is a Skills section."""
    return "Skills\n" + "\n".join(lines)


def names(result):
    return {s["normalized_name"] for s in result["skills"]}


def get(result, name):
    return next(s for s in result["skills"] if s["normalized_name"] == name)


def mention(**kwargs):
    """Helper: a mention dict for the confidence tests."""
    base = {"section": "skills", "match_type": "exact", "unit_id": 0, "action": False,
            "learning": False, "ambiguous": False, "proficiency": None, "years": None}
    base.update(kwargs)
    return base


# ------------------------------------------------------------------ the dictionary itself

class DictionaryTests(unittest.TestCase):
    def test_every_category_is_allowed_by_the_resume_schema(self):
        allowed = set(SKILL_SCHEMA["category"]["enum"])
        self.assertEqual(set(tx.ALLOWED_CATEGORIES), allowed)
        for name, (category, _) in tx.SKILLS.items():
            self.assertIn(category, allowed, name)

    def test_no_alias_points_at_two_different_skills(self):
        owners = defaultdict(set)
        for name, (_, aliases) in tx.SKILLS.items():
            for alias in [name, *aliases]:
                owners[_key(alias)].add(name)
        for name, wrong in tx.MISSPELLINGS.items():
            for alias in wrong:
                owners[_key(alias)].add(name)
        self.assertEqual({k: v for k, v in owners.items() if len(v) > 1}, {})

    def test_stack_components_and_misspelling_targets_exist(self):
        for stack, info in tx.STACKS.items():
            for component in info["components"]:
                self.assertIn(component, tx.SKILLS, f"{stack} -> {component}")
        for name in tx.MISSPELLINGS:
            self.assertIn(name, tx.SKILLS)
        for info in tx.AMBIGUOUS.values():
            self.assertIn(info["skill"], tx.SKILLS)

    def test_all_three_areas_are_covered(self):
        domains = {tx.domain_of(name) for name in tx.SKILLS}
        self.assertEqual(domains, set(tx.DOMAINS))


# ------------------------------------------------------------------ synonyms and normalization

class SynonymTests(unittest.TestCase):
    def test_synonyms_become_one_canonical_name(self):
        text = skills_section("ReactJS, Node JS, Amazon Web Services, Postgres, K8s, scikit learn")
        self.assertEqual(names(extract_skills(text)),
                         {"react", "node.js", "aws", "postgresql", "kubernetes", "scikit-learn"})

    def test_longest_name_wins(self):
        result = extract_skills(skills_section("React Native, Spring Boot, Power BI"))
        self.assertEqual(names(result), {"react native", "spring boot", "power bi"})

    def test_special_characters_in_names(self):
        result = extract_skills(skills_section("C++, C#, .NET, Node.js, CI/CD"))
        self.assertEqual(names(result), {"c++", "c#", ".net", "node.js", "ci/cd"})

    def test_name_keeps_the_original_spelling_and_normalized_name_is_canonical(self):
        skill = get(extract_skills(skills_section("ReactJS, Python, Java")), "react")
        self.assertEqual((skill["name"], skill["normalized_name"]), ("ReactJS", "react"))

    def test_business_and_creative_skills(self):
        result = extract_skills(skills_section("Lead Generation, Salesforce, Adobe Illustrator, Copywriting"))
        self.assertEqual({get(result, n)["domain"] for n in names(result)}, {"business", "creative"})


# ------------------------------------------------------------------ spelling variations

class SpellingTests(unittest.TestCase):
    def test_known_misspellings(self):
        result = extract_skills(skills_section("Pyhton, Javascipt, Kubernates, Comunication"))
        self.assertEqual(names(result), {"python", "javascript", "kubernetes", "communication"})
        self.assertEqual(get(result, "python")["match_type"], "misspelling")

    def test_spaces_and_hyphens_are_equal(self):
        result = extract_skills(skills_section("Power-BI, Mongo DB, Problem solving, Team-work"))
        self.assertEqual(names(result), {"power bi", "mongodb", "problem solving", "teamwork"})

    def test_unknown_typo_is_caught_by_fuzzy_match_and_flagged(self):
        skill = get(extract_skills(skills_section("Python, SQL, Postgresq1, Git")), "postgresql")
        self.assertEqual(skill["match_type"], "fuzzy")
        self.assertTrue(skill["needs_review"])

    def test_fuzzy_match_is_not_used_inside_normal_sentences(self):
        text = "Experience\n- Worked with Postgresq1 databases for the finance team.\n"
        self.assertNotIn("postgresql", names(extract_skills(text)))

    def test_normal_words_are_not_turned_into_skills(self):
        text = skills_section("Leadership, Managing teams, Software testing, Marketing analysis")
        self.assertEqual(names(extract_skills(text)), {"leadership"})


# ------------------------------------------------------------------ stacks

class StackTests(unittest.TestCase):
    def test_mern_gives_its_four_skills_with_low_confidence(self):
        result = extract_skills(skills_section("MERN stack"))
        self.assertEqual(names(result), {"mongodb", "express", "react", "node.js"})
        for skill in result["skills"]:
            self.assertEqual(skill["match_type"], "stack")
            self.assertEqual(skill["source"], "inferred")
            self.assertEqual(skill["confidence_label"], "low")
        self.assertEqual(result["stacks"][0]["name"], "MERN")
        self.assertFalse(result["stacks"][0]["inferred_from_components"])

    def test_mean_needs_capitals_but_mean_stack_does_not(self):
        self.assertEqual(names(extract_skills(skills_section("MEAN"))),
                         {"mongodb", "express", "angular", "node.js"})
        self.assertEqual(names(extract_skills(skills_section("mean stack developer"))),
                         {"mongodb", "express", "angular", "node.js"})
        text = "Experience\n- Reduced the mean response time by 20%.\n"
        self.assertEqual(extract_skills(text)["stacks"], [])

    def test_an_explicitly_written_skill_beats_the_stack_guess(self):
        result = extract_skills(skills_section("MERN stack, React"))
        react = get(result, "react")
        self.assertEqual(react["match_type"], "exact")
        self.assertGreaterEqual(react["confidence"], 0.65)
        self.assertEqual(get(result, "mongodb")["match_type"], "stack")

    def test_stack_is_recognised_from_its_parts(self):
        result = extract_skills(skills_section("MongoDB, Express, React, Node.js"))
        stack = result["stacks"][0]
        self.assertEqual(stack["name"], "MERN")
        self.assertTrue(stack["inferred_from_components"])

    def test_lamp_stack(self):
        self.assertEqual(names(extract_skills(skills_section("LAMP"))), {"linux", "apache", "mysql", "php"})


# ------------------------------------------------------------------ risky short words

class AmbiguousWordTests(unittest.TestCase):
    def test_short_words_accepted_in_a_skills_list(self):
        result = extract_skills(skills_section("Python, C, Go, R, Excel, Swift"))
        self.assertTrue({"c", "go", "r", "excel", "swift"} <= names(result))

    def test_short_words_rejected_in_normal_sentences(self):
        text = ("Experience\n- Helped the team excel in delivery and go to market faster.\n"
                "- The spring release shipped. Express delivery was used. Got a grade C in art.\n")
        self.assertEqual(names(extract_skills(text)), set())

    def test_cue_words_prove_the_skill(self):
        text = "Experience\n- Wrote analysis scripts in R programming and built services in Golang.\n"
        self.assertEqual(names(extract_skills(text)), {"r", "go"})

    def test_capitalised_word_next_to_a_sure_skill(self):
        text = "Experience\n- Designed dashboards in Excel and Tableau for the finance team.\n"
        self.assertEqual(names(extract_skills(text)), {"excel", "tableau"})

    def test_ambiguous_skill_gets_a_small_penalty(self):
        result = extract_skills(skills_section("Go", "Python"))
        self.assertLess(get(result, "go")["confidence"], get(result, "python")["confidence"])

    def test_sql_inside_sales_qualified_lead_is_not_the_database_language(self):
        text = "Experience\n- Increased sales-qualified lead (SQL) conversion rates by 40%.\n"
        self.assertNotIn("sql", names(extract_skills(text)))


# ------------------------------------------------------------------ context: negation, learning, levels

class ContextTests(unittest.TestCase):
    def test_negated_skills_are_ignored(self):
        text = ("Experience\n- No experience with Java in production.\n- Did not use Angular.\n"
                "- Never used Docker. Not familiar with Kafka.\n")
        self.assertEqual(names(extract_skills(text)), set())

    def test_learning_lowers_the_score(self):
        learning = extract_skills("Summary\nCurrently learning Kubernetes.\n")
        self.assertEqual(get(learning, "kubernetes")["confidence_label"], "low")
        self.assertTrue(any("learning" in r for r in get(learning, "kubernetes")["reasons"]))

    def test_years_and_level_after_a_skill(self):
        result = extract_skills(skills_section("Python (3 years), Tableau (advanced), SQL - 5+ years"))
        self.assertEqual(get(result, "python")["years_used"], 3)
        self.assertEqual(get(result, "tableau")["proficiency"], "advanced")
        self.assertEqual(get(result, "sql")["years_used"], 5)

    def test_contact_details_are_never_read_as_skills(self):
        text = ("Rahul Menon\nrahul.python.dev@gmail.com | github.com/rahul-react | +91 98765 43210\n"
                "Skills\nJava\n")
        self.assertEqual(names(extract_skills(text)), {"java"})

    def test_wrapped_skill_list_lines_are_joined(self):
        text = "Core Skills\nProject Management: Agile, Risk Management, Stakeholder\nCommunication\n"
        self.assertIn("stakeholder management", names(extract_skills(text)))


# ------------------------------------------------------------------ deduplication

class DeduplicationTests(unittest.TestCase):
    def test_one_record_per_skill_with_all_spellings_merged(self):
        text = ("Summary\nSkilled in Python and React.\n"
                "Skills\nPyhton, ReactJS, React.js\n"
                "Experience\n- Built an API in Python.\n")
        result = extract_skills(text)
        self.assertEqual([s["normalized_name"] for s in result["skills"]].count("python"), 1)
        python = get(result, "python")
        self.assertEqual(python["aliases_found"], ["Pyhton", "Python"])
        self.assertEqual(python["mentions"], 3)
        self.assertEqual(set(python["sections"]), {"summary", "skills", "experience"})
        self.assertEqual(len(get(result, "react")["aliases_found"]), 3)

    def test_empty_and_skill_free_text(self):
        self.assertEqual(extract_skills("")["skills"], [])
        self.assertIn("Empty text", extract_skills("   ")["warnings"][0])
        self.assertTrue(extract_skills("Summary\nA friendly person.\n")["warnings"])
        self.assertEqual(extract_skills(None)["skills"], [])


# ------------------------------------------------------------------ confidence scoring (pure maths)

class ConfidenceTests(unittest.TestCase):
    def test_listed_only_is_medium(self):
        score, _ = conf.score_skill([mention()])
        self.assertEqual(score, 0.75)
        self.assertEqual(conf.confidence_label(score), "medium")

    def test_listed_and_used_at_work_is_high(self):
        score, reasons = conf.score_skill([mention(), mention(section="experience", unit_id=1, action=True)])
        self.assertGreaterEqual(score, conf.HIGH)
        self.assertTrue(any("work sentence" in r for r in reasons))

    def test_match_quality_order(self):
        scores = [conf.score_skill([mention(match_type=t)])[0]
                  for t in ("exact", "synonym", "misspelling", "fuzzy")]
        self.assertEqual(scores, sorted(scores, reverse=True))
        self.assertEqual(len(set(scores)), 4)

    def test_more_evidence_never_lowers_the_score(self):
        base = [mention(section="summary")]
        more = base + [mention(section="skills", unit_id=1)]
        most = more + [mention(section="experience", unit_id=2, action=True)]
        s1, s2, s3 = (conf.score_skill(m)[0] for m in (base, more, most))
        self.assertTrue(s1 < s2 < s3)

    def test_penalties(self):
        normal = conf.score_skill([mention()])[0]
        self.assertLess(conf.score_skill([mention(learning=True)])[0], normal)
        self.assertLess(conf.score_skill([mention(ambiguous=True)])[0], normal)

    def test_stack_only_is_low_and_explicit_mention_wins(self):
        stack_only, _ = conf.score_skill([mention(match_type="stack")])
        self.assertEqual(conf.confidence_label(stack_only), "low")
        both, _ = conf.score_skill([mention(match_type="stack"), mention(unit_id=1)])
        self.assertEqual(both, 0.75)

    def test_score_stays_between_floor_and_ceiling(self):
        many = [mention(section=s, unit_id=i, action=True, proficiency="expert", years=5)
                for i, s in enumerate(["skills", "experience", "projects", "summary", "certifications"])]
        self.assertEqual(conf.score_skill(many)[0], conf.MAX_SCORE)
        worst, _ = conf.score_skill([mention(section="other", match_type="fuzzy", learning=True, ambiguous=True)])
        self.assertGreaterEqual(worst, conf.MIN_SCORE)

    def test_label_thresholds(self):
        self.assertEqual([conf.confidence_label(s) for s in (0.9, 0.85, 0.84, 0.65, 0.64, 0.1)],
                         ["high", "high", "medium", "medium", "low", "low"])


# ------------------------------------------------------------------ output format

class OutputTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.result = extract_skills("Summary\nBuilt apps with Python and React.\n"
                                    "Skills\nPython, React, MERN stack, Excel, Communication\n"
                                    "Experience\n- Built an API in Python and deployed it to AWS.\n")

    def test_top_level_keys(self):
        self.assertEqual(set(self.result), {"schema_version", "skills", "stacks", "summary", "warnings"})

    def test_every_skill_has_the_agreed_fields(self):
        expected = {"name", "normalized_name", "category", "domain", "proficiency", "years_used", "source",
                    "confidence", "confidence_label", "match_type", "mentions", "sections",
                    "aliases_found", "evidence", "reasons", "needs_review"}
        for skill in self.result["skills"]:
            self.assertEqual(set(skill), expected)
            self.assertTrue(skill["reasons"])
            self.assertTrue(0 < skill["confidence"] < 1)

    def test_sorted_by_confidence_high_to_low(self):
        scores = [s["confidence"] for s in self.result["skills"]]
        self.assertEqual(scores, sorted(scores, reverse=True))

    def test_summary_counts_add_up(self):
        summary = self.result["summary"]
        self.assertEqual(summary["total"], len(self.result["skills"]))
        self.assertEqual(sum(summary["by_domain"].values()), summary["total"])
        self.assertEqual(sum(summary["by_confidence"].values()), summary["total"])

    def test_output_is_json_serialisable(self):
        self.assertEqual(json.loads(json.dumps(self.result)), self.result)

    def test_schema_skills_match_resume_schema(self):
        schema_skills = to_schema_skills(self.result)
        self.assertEqual(len(schema_skills), len(self.result["skills"]))
        for skill in schema_skills:
            self.assertTrue(set(skill) <= set(SKILL_SCHEMA), skill)          # no extra keys allowed
            self.assertIn(skill["category"], SKILL_SCHEMA["category"]["enum"])
            self.assertIn(skill["source"], SKILL_SCHEMA["source"]["enum"])
            self.assertIn(skill["proficiency"], SKILL_SCHEMA["proficiency"]["enum"])
            self.assertTrue(0 <= skill["confidence"] <= 1)

    def test_schema_skills_validate_with_jsonschema_when_installed(self):
        try:
            from utils.schema_validator import get_errors
        except ImportError:
            self.skipTest("jsonschema is not installed")
        doc = {"schema_version": "1.0", "candidate_id": "cand_test",
               "personal": {"full_name": "Test", "email": "t@example.com"},
               "skills": to_schema_skills(self.result), "experience": [], "education": []}
        self.assertEqual(get_errors(doc, "resume"), [])

    def test_min_confidence_filter(self):
        high_only = to_schema_skills(self.result, min_confidence=0.85)
        self.assertTrue(all(s["confidence"] >= 0.85 for s in high_only))
        self.assertLess(len(high_only), len(self.result["skills"]))


# ------------------------------------------------------------------ real sample resumes

class SampleResumeTests(unittest.TestCase):
    def extract(self, name):
        path = ROOT / "data" / "extracted" / f"{name}.txt"
        if not path.exists():
            self.skipTest(f"{path.name} not found")
        return extract_skills_from_file(path)

    def test_maya_software_engineer(self):
        result = self.extract("Maya")
        self.assertTrue({"python", "react", "aws", "docker", "fastapi", "typescript", "ci/cd"} <= names(result))
        self.assertEqual(get(result, "python")["confidence_label"], "high")

    def test_alex_project_manager(self):
        result = self.extract("alex")
        self.assertTrue({"agile", "jira", "power bi", "excel", "sql", "stakeholder management"} <= names(result))

    def test_marcus_marketing_manager(self):
        result = self.extract("marcus")
        self.assertTrue({"salesforce", "hubspot", "tableau", "google ads"} <= names(result))
        self.assertNotIn("sql", names(result))          # "(SQL)" there means sales qualified lead

    def test_scanned_file_gives_a_warning_and_no_crash(self):
        path = ROOT / "data" / "raw_resumes" / "sample_scanned.pdf"
        if not path.exists():
            self.skipTest("sample_scanned.pdf not found")
        result = extract_skills_from_file(path)
        self.assertEqual(result["skills"], [])
        self.assertTrue(result["warnings"])


if __name__ == "__main__":
    unittest.main()
