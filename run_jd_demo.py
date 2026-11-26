"""Day 6 demo: parse every sample job description, validate it and save the JSON output.

Run from the project root:
    python run_jd_demo.py

For each data/job_descriptions/<name>.txt it writes
    data/parsed_jobs/<name>.json          structured job (follows data/schemas/job_schema.json)
    data/parsed_jobs/<name>.profile.json  flat AI-friendly profile
"""
import json
from pathlib import Path

from parsers.jd_parser import build_ai_profile, parse_job_description
from utils.schema_validator import get_errors

ROOT = Path(__file__).resolve().parent
INPUT_DIR = ROOT / "data" / "job_descriptions"
OUTPUT_DIR = ROOT / "data" / "parsed_jobs"


def save_json(path, data):
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def main():
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    for path in sorted(INPUT_DIR.glob("*.txt")):
        job_id = "job_" + path.stem.removeprefix("jd_")
        text = path.read_text(encoding="utf-8")
        job = parse_job_description(text, job_id=job_id, company_id="comp_0001")
        profile = build_ai_profile(job)
        errors = get_errors(job, "job")

        save_json(OUTPUT_DIR / f"{path.stem}.json", job)
        save_json(OUTPUT_DIR / f"{path.stem}.profile.json", profile)
        print(f"{path.name:32} schema: {'VALID' if not errors else 'INVALID'}")
        print(f"   {profile['summary']}")
        for error in errors:
            print("   -", error)


if __name__ == "__main__":
    main()
