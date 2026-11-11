"""Automated tests for the Day 5 resume extraction engine.

Run:  python -m unittest discover -s tests -t . -v
"""
import json
import tempfile
import unittest
from pathlib import Path

from extraction.cleaner import clean_text
from extraction.docx_reader import read_docx
from extraction.extractor import UnsupportedFileError, extract_resume
from extraction.normalizer import (detect_heading, normalize,
                                   normalize_bullets, split_sections)
from extraction.pdf_reader import read_pdf
from tests import sample_builder as sb


class ExtractionTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self._tmp.name)
        self.out = self.dir / "out"
        sb.build_all(self.dir)

    def tearDown(self):
        self._tmp.cleanup()

    # --- readers ---
    def test_pdf_is_read(self):
        text = read_pdf(self.dir / "sample_simple.pdf")
        self.assertTrue(text.strip())
        self.assertIn("Rahul Kumar", text)

    def test_docx_is_read_including_table(self):
        text = read_docx(self.dir / "sample_bullets_table.docx")
        self.assertIn("Built REST APIs", text)
        self.assertIn("Kerala University", text)
        self.assertIn("Degree | University", text)

    def test_two_column_pdf_read_column_by_column(self):
        r = extract_resume(self.dir / "sample_two_column.pdf", self.out)
        text = r["clean_text"]
        self.assertNotIn("Skills Experience", text)   # columns not mixed
        self.assertLess(text.index("Demo University"), text.index("Built small REST APIs"))
        self.assertTrue(any("two-column" in w for w in r["warnings"]))

    # --- cleaner ---
    def test_cleaner_removes_odd_symbols_and_blank_lines(self):
        raw = "Hello\u200b  World\x07\n\n\n\n\nPage 1 of 2\nSecond\u00a0line\ndevelop-\nment"
        cleaned = clean_text(raw)
        self.assertNotIn("\u200b", cleaned)
        self.assertNotIn("\x07", cleaned)
        self.assertNotIn("Page 1 of 2", cleaned)
        self.assertNotIn("\n\n\n", cleaned)
        self.assertIn("Hello World", cleaned)
        self.assertIn("development", cleaned)

    def test_cleaner_handles_empty_input(self):
        self.assertEqual(clean_text(""), "")
        self.assertEqual(clean_text(None), "")

    # --- normalizer ---
    def test_all_bullet_styles_become_dash(self):
        raw = "\u2022 one\n\u25cf two\n\u25aa three\n- four\n* five"
        self.assertEqual(normalize_bullets(raw).split("\n"),
                         ["- one", "- two", "- three", "- four", "- five"])

    def test_headings_detected(self):
        self.assertEqual(detect_heading("EXPERIENCE"), "experience")
        self.assertEqual(detect_heading("Work Experience:"), "experience")
        self.assertEqual(detect_heading("Technical Skills"), "skills")
        self.assertEqual(detect_heading("Objective"), "summary")
        self.assertIsNone(detect_heading("I have work experience in Python"))

    def test_headings_standardized_and_sections_split(self):
        text, sections = normalize("Name\nWORK EXPERIENCE:\n\u2022 Did X\nEDUCATION\nB.Sc")
        self.assertIn("\nExperience\n", text)
        self.assertEqual(sections["experience"], "- Did X")
        self.assertEqual(sections["education"], "B.Sc")
        self.assertEqual(sections["header"], "Name")

    # --- extractor ---
    def test_unsupported_file_raises_clear_error(self):
        bad = self.dir / "photo.jpg"
        bad.write_bytes(b"not a resume")
        with self.assertRaises(UnsupportedFileError) as ctx:
            extract_resume(bad, self.out)
        self.assertIn(".jpg", str(ctx.exception))

    def test_missing_file_raises(self):
        with self.assertRaises(FileNotFoundError):
            extract_resume(self.dir / "nope.pdf", self.out)

    def test_corrupt_and_empty_files_do_not_crash(self):
        corrupt = self.dir / "corrupt.pdf"
        corrupt.write_bytes(b"this is not a real pdf")
        empty = self.dir / "empty.docx"
        empty.write_bytes(b"")
        for f in (corrupt, empty):
            r = extract_resume(f, self.out)
            self.assertEqual(r["status"], "failed")
            self.assertTrue(r["warnings"])
            self.assertEqual(r["clean_text"], "")

    def test_scanned_pdf_sets_needs_ocr_flag(self):
        r = extract_resume(self.dir / "sample_scanned.pdf", self.out)
        self.assertTrue(r["needs_ocr"])
        self.assertTrue(r["warnings"])

    def test_output_files_are_created(self):
        r = extract_resume(self.dir / "sample_simple.pdf", self.out)
        txt = self.out / "sample_simple.txt"
        js = self.out / "sample_simple.json"
        self.assertTrue(txt.exists())
        self.assertTrue(js.exists())
        data = json.loads(js.read_text(encoding="utf-8"))
        for key in ("source_file", "file_type", "page_count", "char_count",
                    "needs_ocr", "warnings", "sections", "clean_text"):
            self.assertIn(key, data)
        self.assertEqual(data["file_type"], "pdf")
        self.assertFalse(data["needs_ocr"])
        self.assertIn("skills", data["sections"])
        self.assertNotIn("Page 1 of 1", data["clean_text"])
        self.assertEqual(txt.read_text(encoding="utf-8"), r["clean_text"])


if __name__ == "__main__":
    unittest.main()
