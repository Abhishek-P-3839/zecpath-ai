"""Day 10 demo: parse the experience of every resume and score it against every parsed job.

    python run_experience_demo.py

Output (in data/experience/):
    <resume>.json                    full experience object (jobs, total years, gaps, overlaps, warnings)
    <resume>.schema_experience.json  only the `experience` list, ready for resume_schema.json
    <resume>.relevance.json          relevance report for each job in data/parsed_jobs/*.profile.json
"""
import json
from pathlib import Path

from extraction.extractor import SUPPORTED
from parsers.experience_parser import parse_experience_from_file, to_schema_experience
from parsers.experience_relevance import score_experience, similarity_matrix
from utils.schema_validator import SCHEMA_DIR, load_json
from jsonschema import Draft7Validator

RAW_DIR = Path("data/raw_resumes")
JOB_DIR = Path("data/parsed_jobs")
OUT_DIR = Path("data/experience")
OUT_DIR.mkdir(parents=True, exist_ok=True)


def save(path, data):
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def schema_errors(entries):
    """Check every entry against the `experience` definition in resume_schema.json."""
    schema = load_json(SCHEMA_DIR / "resume_schema.json")
    validator = Draft7Validator({"$ref": "#/definitions/experience", "definitions": schema["definitions"]})
    return [e.message for entry in entries for e in validator.iter_errors(entry)]


def main():
    jobs = {p.name.removesuffix(".profile.json"): json.loads(p.read_text(encoding="utf-8"))
            for p in sorted(JOB_DIR.glob("*.profile.json"))}

    for path in sorted(p for p in RAW_DIR.iterdir() if p.suffix.lower() in SUPPORTED):
        experience = parse_experience_from_file(path)
        schema_entries = to_schema_experience(experience)
        errors = schema_errors(schema_entries)
        save(OUT_DIR / f"{path.stem}.json", experience)
        save(OUT_DIR / f"{path.stem}.schema_experience.json", schema_entries)

        print(f"\n{path.name}: {len(experience['entries'])} job(s), "
              f"{experience['total_experience_years']} years, schema: {'VALID' if not errors else 'INVALID'}")
        for e in experience["entries"]:
            end = "Present" if e["is_current"] else (e["end_date"] or "?")
            print(f"   {e['designation']} @ {e['company']}  [{e['start_date'] or '?'} -> {end}, "
                  f"{e['duration_months'] or '?'} months]")
        for gap in experience["gaps"]:
            print(f"   GAP: {gap['months']} month(s) {gap['from']} -> {gap['to']} ({gap['severity']})")
        for ov in experience["overlaps"]:
            if ov["kind"] != "handover":
                print(f"   OVERLAP ({ov['kind']}): {ov['companies'][0]} / {ov['companies'][1]}, {ov['months']} month(s)")
        for error in errors:
            print("   schema error:", error)

        report = {name: score_experience(experience, job) for name, job in jobs.items()}
        save(OUT_DIR / f"{path.stem}.relevance.json", report)
        for name, r in report.items():
            print(f"   vs {name:28} score {r['score']:3}  {r['label']:8} relevant {r['relevant_years']} yrs")

    print("\nRole-to-role similarity (0 = unrelated, 1 = same role):")
    titles = ["Full Stack Developer", "Software Engineer", "Python Developer", "Data Analyst", "HR Executive"]
    matrix = similarity_matrix(titles)
    print(" " * 22 + "".join(f"{t[:12]:>14}" for t in titles))
    for a in titles:
        print(f"{a:22}" + "".join(f"{matrix[a][b]:>14}" for b in titles))


if __name__ == "__main__":
    main()
