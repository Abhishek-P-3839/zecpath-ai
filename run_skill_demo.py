"""Day 9 demo: extract skills from every resume in data/raw_resumes and save the result.

    python run_skill_demo.py

Output: data/skills/<resume>.json   (full result: skills, confidence, stacks, summary, warnings)
        data/skills/<resume>.schema_skills.json   (only the `skills` list, ready for resume_schema.json)
"""
import json
from pathlib import Path

from extraction.extractor import SUPPORTED
from parsers.skill_extractor import extract_skills_from_file, to_schema_skills

RAW_DIR = Path("data/raw_resumes")
OUT_DIR = Path("data/skills")
OUT_DIR.mkdir(parents=True, exist_ok=True)

for path in sorted(p for p in RAW_DIR.iterdir() if p.suffix.lower() in SUPPORTED):
    result = extract_skills_from_file(path)
    (OUT_DIR / f"{path.stem}.json").write_text(
        json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8")
    (OUT_DIR / f"{path.stem}.schema_skills.json").write_text(
        json.dumps(to_schema_skills(result), indent=2, ensure_ascii=False), encoding="utf-8")

    summary = result["summary"]
    levels = summary["by_confidence"]
    print(f"{path.name:28} {summary['total']:3} skills  "
          f"high={levels.get('high', 0)} medium={levels.get('medium', 0)} low={levels.get('low', 0)}  "
          f"stacks: {', '.join(s['name'] for s in result['stacks']) or '-'}")
    for warning in result["warnings"]:
        print(f"{'':28} warning: {warning}")
