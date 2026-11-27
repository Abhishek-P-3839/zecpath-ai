"""Day 14 tests: shortlisting automation.  Run:  python -m unittest tests.test_shortlisting -v

Fake ranked rows are used, so the tests are instant and need no resume files.
"""
import copy
import csv
import io
import json
import tempfile
import unittest
from pathlib import Path

from ats_engine.shortlisting import (
    ACTIONS, CONFIG_PATH, REJECTED, REVIEW, SHORTLISTED, WAITLIST, build_shortlist, format_shortlist_text,
    load_config, resolve_thresholds, save_shortlist, to_csv, validate_config, zone_for,
)
from ats_engine.weights import CONFIG_PATH as WEIGHTS_PATH

CONFIG = {"default": {"shortlist_score": 60, "reject_score": 50, "max_missing_must_have": 3,
                      "auto_reject": True, "max_shortlist": None}, "roles": {}}
JOB = {"title": "MERN Developer", "normalized_title": "full stack developer"}


def row(cid, score, position=1, rank=None, confidence="high", missing=None):
    """A minimal ranked row, like the ones ranking_engine.build_ranking() makes."""
    return {"position": position, "rank": rank, "tied": False, "candidate_id": cid,
            "overall_score": score, "label": "good", "recommendation": "review", "confidence": confidence,
            "missing_must_have": missing or []}


def ranking(*rows):
    """Wrap rows (best first, positions filled in) like build_ranking() output."""
    rows = list(rows)
    for number, r in enumerate(rows, start=1):
        r["position"] = number
        r["rank"] = r["rank"] or number          # equal scores share a rank when the test says so
    return {"job_id": "job_a", "job_title": "MERN Developer", "ranking": rows, "warnings": []}


def shortlist(rows, overrides=None, config=CONFIG, job=JOB):
    return build_shortlist(ranking(*rows), job, copy.deepcopy(config), overrides)


def decisions(output):
    return {c["candidate_id"]: c["decision"] for c in output["candidates"]}


class ZoneTests(unittest.TestCase):
    def test_boundaries(self):
        t = resolve_thresholds(JOB, CONFIG)
        self.assertEqual(zone_for(60, t), SHORTLISTED)      # exactly on the line is shortlisted
        self.assertEqual(zone_for(59.9, t), REVIEW)
        self.assertEqual(zone_for(50, t), REVIEW)           # exactly on the reject line is still review
        self.assertEqual(zone_for(49.9, t), REJECTED)

    def test_actions_are_recruiter_words(self):
        out = shortlist([row("a", 80), row("b", 55), row("c", 10)])
        self.assertEqual([c["action"] for c in out["candidates"]],
                         [ACTIONS[SHORTLISTED], ACTIONS[REVIEW], ACTIONS[REJECTED]])
        self.assertEqual(out["counts"], {SHORTLISTED: 1, WAITLIST: 0, REVIEW: 1, REJECTED: 1, "total": 3})


class SafetyRuleTests(unittest.TestCase):
    def test_low_confidence_is_never_auto_shortlisted_or_rejected(self):
        out = shortlist([row("high", 90, confidence="low"), row("zero", 0, confidence="low")])
        self.assertEqual(decisions(out), {"high": REVIEW, "zero": REVIEW})
        self.assertIn("low_confidence", out["candidates"][0]["safety_rules"])

    def test_too_many_missing_must_haves_blocks_shortlisting(self):
        out = shortlist([row("a", 90, missing=["x", "y", "z", "w"]), row("b", 90, missing=["x", "y", "z"])])
        self.assertEqual(decisions(out), {"a": REVIEW, "b": SHORTLISTED})        # limit 3: 3 is allowed
        self.assertIn("missing_must_have", out["candidates"][0]["safety_rules"])

    def test_missing_limit_is_configurable(self):
        out = shortlist([row("a", 90, missing=["x"])], {"max_missing_must_have": 0})
        self.assertEqual(decisions(out)["a"], REVIEW)

    def test_auto_reject_off_sends_reject_zone_to_review(self):
        out = shortlist([row("a", 10)], {"auto_reject": False})
        self.assertEqual(decisions(out)["a"], REVIEW)
        self.assertTrue(any("Auto-reject is OFF" in w for w in out["warnings"]))

    def test_capacity_waitlists_extra_candidates(self):
        out = shortlist([row("a", 90), row("b", 80), row("c", 70)], {"max_shortlist": 2})
        self.assertEqual(decisions(out), {"a": SHORTLISTED, "b": SHORTLISTED, "c": WAITLIST})
        self.assertTrue(any("waitlist" in w for w in out["warnings"]))

    def test_capacity_keeps_ties_with_the_last_place_together(self):
        rows = [row("a", 90), row("b", 80, rank=2), row("c", 80, rank=2), row("d", 70, rank=4)]
        out = shortlist(rows, {"max_shortlist": 2})
        self.assertEqual(decisions(out), {"a": SHORTLISTED, "b": SHORTLISTED, "c": SHORTLISTED, "d": WAITLIST})

    def test_capacity_counts_only_shortlisted_not_held_back_candidates(self):
        rows = [row("a", 90, confidence="low"), row("b", 80), row("c", 70)]
        out = shortlist(rows, {"max_shortlist": 1})
        self.assertEqual(decisions(out), {"a": REVIEW, "b": SHORTLISTED, "c": WAITLIST})


class ThresholdTests(unittest.TestCase):
    def test_precedence_default_role_job_cli(self):
        config = copy.deepcopy(CONFIG)
        config["roles"] = {"Full Stack Developer": {"shortlist_score": 65, "reject_score": 55}}
        self.assertEqual(resolve_thresholds({}, config)["shortlist_score"], 60)
        self.assertEqual(resolve_thresholds(JOB, config)["shortlist_score"], 65)            # role beats default
        job = dict(JOB, ats_cutoff_score=70)
        t = resolve_thresholds(job, config)
        self.assertEqual((t["shortlist_score"], t["reject_score"]), (70, 60))               # width 10 is kept
        t = resolve_thresholds(job, config, {"shortlist_score": 80})
        self.assertEqual((t["shortlist_score"], t["reject_score"]), (80, 70))               # command line wins
        t = resolve_thresholds(job, config, {"shortlist_score": 80, "reject_score": 40})
        self.assertEqual((t["shortlist_score"], t["reject_score"]), (80, 40))
        self.assertIn("command line cutoff", t["sources"])

    def test_cutoff_never_makes_reject_line_negative(self):
        self.assertEqual(resolve_thresholds({"ats_cutoff_score": 5}, CONFIG)["reject_score"], 0)

    def test_none_overrides_are_ignored(self):
        t = resolve_thresholds(JOB, CONFIG, {"shortlist_score": None, "max_shortlist": None})
        self.assertEqual(t["shortlist_score"], 60)

    def test_invalid_values_raise_clear_errors(self):
        for bad in ({"shortlist_score": 120}, {"reject_score": 70}, {"max_shortlist": 0},
                    {"max_shortlist": 2.5}, {"auto_reject": "yes"}, {"max_missing_must_have": -1}):
            with self.assertRaises(ValueError, msg=str(bad)):
                resolve_thresholds(JOB, CONFIG, bad)

    def test_invalid_config_is_reported(self):
        bad = copy.deepcopy(CONFIG)
        bad["default"]["reject_score"] = 90
        bad["roles"] = {"x": {"shortlist_score": -5}}
        problems = validate_config(bad)
        self.assertEqual(len(problems), 2)
        self.assertEqual(validate_config({}), ["config: needs a 'default' section."])
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "bad.json"
            path.write_text(json.dumps(bad), encoding="utf-8")
            with self.assertRaises(ValueError):
                load_config(path)

    def test_defaults_agree_with_day13_thresholds(self):
        day13 = json.loads(WEIGHTS_PATH.read_text(encoding="utf-8"))["thresholds"]
        default = load_config(CONFIG_PATH)["default"]
        self.assertEqual(default["shortlist_score"], day13["shortlist_score"])
        self.assertEqual(default["shortlist_score"] - default["reject_score"], day13["review_margin"])


class WarningAndOutputTests(unittest.TestCase):
    def test_nobody_reached_cutoff(self):
        out = shortlist([row("a", 55), row("b", 20)])
        self.assertTrue(any("Nobody reached" in w for w in out["warnings"]))

    def test_safety_rule_warning_differs_from_nobody_reached(self):
        out = shortlist([row("a", 90, confidence="low")])
        self.assertFalse(any("Nobody reached" in w for w in out["warnings"]))
        self.assertTrue(any("safety rule" in w for w in out["warnings"]))

    def test_duplicate_ids_warned(self):
        out = shortlist([row("a", 90), row("a", 80)])
        self.assertTrue(any("Duplicate candidate ids: a" in w for w in out["warnings"]))

    def test_top_list_has_shortlisted_only_and_keeps_ties(self):
        rows = [row("a", 90), row("b", 80, rank=2), row("c", 80, rank=2), row("d", 55), row("e", 10)]
        out = build_shortlist(ranking(*rows), JOB, copy.deepcopy(CONFIG), top_n=2)
        self.assertEqual([t["candidate_id"] for t in out["top_candidates"]], ["a", "b", "c"])

    def test_empty_ranking(self):
        out = build_shortlist({"job_id": None, "ranking": [], "warnings": []}, None, copy.deepcopy(CONFIG))
        self.assertEqual(out["counts"]["total"], 0)
        self.assertIn("No candidates to shortlist.", out["warnings"])

    def test_text_summary_shows_counts_first_then_zones(self):
        text = format_shortlist_text(shortlist([row("a", 80), row("b", 55), row("c", 10)]))
        self.assertLess(text.index("Shortlisted: 1"), text.index("SHORTLISTED (1)"))
        self.assertLess(text.index("SHORTLISTED (1)"), text.index("REVIEW (1)"))
        self.assertLess(text.index("REVIEW (1)"), text.index("REJECTED (1)"))

    def test_csv_and_files(self):
        out = shortlist([row("a", 80), row("b", 55, missing=["sql"])])
        rows = list(csv.DictReader(io.StringIO(to_csv(out))))
        self.assertEqual([r["decision"] for r in rows], [SHORTLISTED, REVIEW])
        self.assertEqual(rows[1]["missing_must_have"], "sql")
        with tempfile.TemporaryDirectory() as folder:
            paths = save_shortlist(out, folder)
            self.assertEqual(sorted(p.name for p in paths.values()),
                             ["job_a.shortlist.csv", "job_a.shortlist.json", "job_a.shortlist.txt"])
            self.assertEqual(json.loads(paths["json"].read_text(encoding="utf-8"))["counts"]["total"], 2)

    def test_job_id_with_a_dot_is_not_cut(self):
        out = shortlist([row("a", 80)])
        out["job_id"] = "job.v2"
        with tempfile.TemporaryDirectory() as folder:
            self.assertEqual(save_shortlist(out, folder)["json"].name, "job.v2.shortlist.json")


if __name__ == "__main__":
    unittest.main()
