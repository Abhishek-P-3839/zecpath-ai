import json
import tempfile
import unittest
from pathlib import Path

from pipeline.lifecycle import get_stage, record_event
from pipeline.metadata import make_metadata, validate_metadata
from pipeline.storage import list_versions, load_record, save_record, verify_record
from pipeline.versioning import build_training_snapshot, remove_personal_data


class TestMetadata(unittest.TestCase):
    def test_valid_metadata(self):
        meta = make_metadata("ats_score", "cand_0001", "job_python_developer")
        self.assertEqual(validate_metadata(meta), [])

    def test_bad_candidate_id(self):
        meta = make_metadata("ats_score", "bad_id", "job_python_developer")
        self.assertIn("candidate_id must look like cand_0001", validate_metadata(meta))

    def test_job_id_missing_for_job_record(self):
        meta = make_metadata("ats_score", "cand_0001", None)
        self.assertTrue(any("job_id" in e for e in validate_metadata(meta)))

    def test_unknown_record_type(self):
        with self.assertRaises(ValueError):
            make_metadata("banana", "cand_0001")


class TestStorage(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def test_versions_increase_and_nothing_is_overwritten(self):
        save_record("ats_score", {"score": 50}, "cand_0001", "job_x", root=self.root)
        save_record("ats_score", {"score": 80}, "cand_0001", "job_x", root=self.root)
        self.assertEqual(list_versions("ats_score", "cand_0001", "job_x", self.root), [1, 2])
        self.assertEqual(load_record("ats_score", "cand_0001", "job_x", 1, self.root)["data"]["score"], 50)
        self.assertEqual(load_record("ats_score", "cand_0001", "job_x", root=self.root)["data"]["score"], 80)

    def test_checksum_detects_manual_edit(self):
        path = save_record("parsed_profile", {"skills": ["python"]}, "cand_0001", root=self.root)
        record = json.loads(path.read_text())
        self.assertTrue(verify_record(record))
        record["data"]["skills"].append("hacked")
        self.assertFalse(verify_record(record))

    def test_load_missing_raises(self):
        with self.assertRaises(FileNotFoundError):
            load_record("ats_score", "cand_0009", "job_x", root=self.root)


class TestLifecycle(unittest.TestCase):
    def test_cannot_skip_a_stage(self):
        with tempfile.TemporaryDirectory() as tmp:
            record_event("cand_0001", "job_x", "uploaded", root=tmp)
            with self.assertRaises(ValueError):
                record_event("cand_0001", "job_x", "interviewed", root=tmp)
            record_event("cand_0001", "job_x", "parsed", root=tmp)
            self.assertEqual(get_stage("cand_0001", "job_x", tmp), "parsed")


class TestVersioning(unittest.TestCase):
    def test_personal_data_removed(self):
        cleaned = remove_personal_data({"email": "a@b.com", "skills": ["python"], "x": {"phone": "123", "y": 1}})
        self.assertEqual(cleaned, {"skills": ["python"], "x": {"y": 1}})

    def test_snapshot_versions_are_new_each_time(self):
        with tempfile.TemporaryDirectory() as tmp:
            for kind, data, job in [("parsed_profile", {"email": "a@b.com", "skills": ["python"]}, None),
                                    ("ats_score", {"score": 90}, "job_x"),
                                    ("hiring_decision", {"final_score": 85, "decision": "selected"}, "job_x")]:
                save_record(kind, data, "cand_0001", job, root=tmp)
            _, m1 = build_training_snapshot(root=tmp)
            _, m2 = build_training_snapshot(root=tmp)
            self.assertEqual((m1["dataset_version"], m2["dataset_version"]), (1, 2))
            self.assertEqual(m1["record_count"], 1)


if __name__ == "__main__":
    unittest.main()
