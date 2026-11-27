"""Day 11 demo: build the academic profile of every resume and score it against every parsed job.

    python run_education_demo.py

Output (in data/education/):
    <resume>.json                      the structured academic profile (entries, highest degree, field, certifications)
    <resume>.schema_education.json     only the `education` list, ready for resume_schema.json
    <resume>.schema_certifications.json  only the `certifications` list, ready for resume_schema.json
    <resume>.relevance.json            education + certification relevance for each job in data/parsed_jobs/*.profile.json
"""

import json
from pathlib import Path

from jsonschema import Draft7Validator

from extraction.extractor import SUPPORTED
from parsers.academic_profile import profile_from_file
from parsers.education_relevance import score_education_with_certifications
from utils.schema_validator import SCHEMA_DIR, load_json

RAW_DIR = Path("data/raw_resumes")
JOB_DIR = Path("data/parsed_jobs")
OUT_DIR = Path("data/education")
OUT_DIR.mkdir(parents=True, exist_ok=True)


def save(path, data):
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def schema_errors(items, definition):
    """Check every item against one definition ('education' or 'certification') of resume_schema.json."""
    schema = load_json(SCHEMA_DIR / "resume_schema.json")
    validator = Draft7Validator(
        {"$ref": f"#/definitions/{definition}", "definitions": schema["definitions"]}
    )
    return [e.message for item in items for e in validator.iter_errors(item)]


def main():
    jobs = {
        p.name.removesuffix(".profile.json"): json.loads(p.read_text(encoding="utf-8"))
        for p in sorted(JOB_DIR.glob("*.profile.json"))
    }

    for path in sorted(p for p in RAW_DIR.iterdir() if p.suffix.lower() in SUPPORTED):
        profile = profile_from_file(path)
        errors = schema_errors(profile["schema_education"], "education") + schema_errors(
            profile["schema_certifications"], "certification"
        )
        save(OUT_DIR / f"{path.stem}.json", profile)
        save(OUT_DIR / f"{path.stem}.schema_education.json", profile["schema_education"])
        save(OUT_DIR / f"{path.stem}.schema_certifications.json", profile["schema_certifications"])

        top, c = profile["highest_degree"], profile["counts"]
        print(
            f"\n{path.name}: {c['degrees']} degree(s), {c['certifications']} certification(s), "
            f"{c['courses']} course(s), schema: {'VALID' if not errors else 'INVALID'}"
        )
        if top:
            status = "in progress" if top["in_progress"] else f"graduated {top['end_year'] or '?'}"
            print(
                f"   highest: {top['degree']} in {top['field_of_study'] or '?'} "
                f"@ {top['institution'] or '?'} ({status})"
            )
        print(
            f"   primary field: {profile['primary_field'] or '?'} [{profile['primary_field_category'] or '?'}]"
            f"   latest graduation year: {profile['latest_graduation_year'] or '?'}"
        )
        for cert in profile["certifications"]:
            print(f"   cert: {cert['name']} [{', '.join(cert['categories'])}]")
        for warning in profile["warnings"]:
            print("   warning:", warning)
        for error in errors:
            print("   schema error:", error)

        report = {
            name: score_education_with_certifications(profile, job) for name, job in jobs.items()
        }
        save(OUT_DIR / f"{path.stem}.relevance.json", report)
        for name, r in report.items():
            score = "---" if r["score"] is None else f"{r['score']:5.1f}"
            print(f"   vs {name:28} education {score}  [{r['status']}]  cert bonus +{r['bonus']}")


if __name__ == "__main__":
    main()
