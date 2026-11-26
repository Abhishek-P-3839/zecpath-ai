"""Day 8 demo: split every resume in data/raw_resumes into sections and save the result.

    python run_section_demo.py

Output: data/segmented/<resume>.json   (sections, blocks, line tags, warnings)
"""
import json
from pathlib import Path

from extraction.extractor import SUPPORTED
from parsers.section_classifier import segment_file

RAW_DIR = Path("data/raw_resumes")
OUT_DIR = Path("data/segmented")
OUT_DIR.mkdir(parents=True, exist_ok=True)

for path in sorted(p for p in RAW_DIR.iterdir() if p.suffix.lower() in SUPPORTED):
    result = segment_file(path)
    (OUT_DIR / f"{path.stem}.json").write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8")
    found = ", ".join(result["sections"]) or "nothing"
    print(f"{path.name:28} sections: {found}")
    for warning in result["warnings"]:
        print(f"{'':28} warning: {warning}")
