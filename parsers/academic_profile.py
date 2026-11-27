"""Day 11: Structured academic profile.

One clean object that answers "what is this candidate's academic background?" in a single place.
It is built from the parse result of parsers.education_parser (nothing is parsed again here):

    result = parse_from_file("data/raw_resumes/Maya.pdf")
    profile = build_academic_profile(result)

The profile has two kinds of content (the same pattern as Day 10):
    * the RICH part: normalized entries, highest degree, primary field, categories, counts, warnings
    * the SCHEMA part: `schema_education` and `schema_certifications`, made by the existing
      to_schema_* functions. resume_schema.json does not allow extra fields, so categories and counts
      stay out of those two lists.

Run it:
    python -m parsers.academic_profile data/raw_resumes/Maya.pdf
"""

import json
import sys

from parsers.education_parser import (
    LEVEL_ORDER,
    parse_from_file,
    to_schema_certifications,
    to_schema_education,
)
from utils.logger import get_logger

log = get_logger(__name__)

PROFILE_VERSION = "1.0.0"
DIPLOMA = LEVEL_ORDER.index(
    "diploma"
)  # diploma and above count as a "degree" (school marks do not)
_DEGREE_KEYS = (
    "degree",
    "degree_full",
    "level",
    "field_of_study",
    "field_category",
    "institution",
    "start_year",
    "end_year",
    "in_progress",
    "grade",
)


def _is_degree(entry):
    return entry["level"] in LEVEL_ORDER and LEVEL_ORDER.index(entry["level"]) >= DIPLOMA


def _rank(entry):
    """Sort key: higher level first, then the most recent finish year (entries without a year last)."""
    return (LEVEL_ORDER.index(entry["level"]), entry["end_year"] or 0)


def _summary(entry):
    """The short version of an entry that is shown in the profile ('highest_degree' etc.)."""
    return {k: entry.get(k) for k in _DEGREE_KEYS}


def find_highest_degree(entries):
    """The highest FINISHED degree; if nothing is finished, the highest one in progress; else None.

    A finished master's beats a bachelor's that is "in progress", because the candidate really holds it.
    """
    known = [e for e in entries if e["level"] in LEVEL_ORDER]
    for pool in (
        [e for e in known if not e["in_progress"]],
        [e for e in known if e["in_progress"]],
    ):
        if pool:
            return max(pool, key=_rank)
    return None


def find_primary_field(entries, highest):
    """(field, category) of the candidate's main subject.

    Taken from the highest degree if it names a field. Otherwise from the highest degree-level entry that
    does, and only then from any entry (a school "Science" stream is the weakest evidence).
    """
    if highest and highest["field_of_study"]:
        return highest["field_of_study"], highest["field_category"]
    named = [e for e in entries if e["field_of_study"]]
    for pool in ([e for e in named if _is_degree(e)], named):
        if pool:
            best = max(pool, key=_rank)
            return best["field_of_study"], best["field_category"]
    return None, None


def certification_summary(certifications):
    """{'categories': sorted unique categories, 'by_category': {category: how many}}."""
    by_category = {}
    for cert in certifications:
        for category in cert["categories"]:
            by_category[category] = by_category.get(category, 0) + 1
    return {"categories": sorted(by_category), "by_category": dict(sorted(by_category.items()))}


def build_academic_profile(result):
    """Main entry point: parse result -> one structured academic profile (a plain, JSON-ready dict)."""
    entries = result["education"]
    certs = result["certifications"]
    highest = find_highest_degree(entries)
    field, category = find_primary_field(entries, highest)
    completed = [e for e in entries if e["level"] in LEVEL_ORDER and not e["in_progress"]]
    finished_years = [e["end_year"] for e in entries if e["end_year"] and not e["in_progress"]]
    in_progress = [_summary(e) for e in entries if e["in_progress"]]
    cert_info = certification_summary(certs)

    profile = {
        "profile_version": PROFILE_VERSION,
        "source_file": result.get("source_file"),
        "education": entries,
        "highest_level": result.get("highest_level"),  # may be a degree still in progress
        "highest_completed_level": max(completed, key=_rank)["level"] if completed else None,
        "highest_degree": _summary(highest) if highest else None,
        "primary_field": field,
        "primary_field_category": category,
        "latest_graduation_year": max(finished_years) if finished_years else None,
        "in_progress_degrees": in_progress,
        "certifications": certs,
        "certification_categories": cert_info["categories"],
        "certifications_by_category": cert_info["by_category"],
        "counts": {
            "education_entries": len(entries),
            "degrees": sum(1 for e in entries if _is_degree(e)),
            "in_progress": len(in_progress),
            "certifications": sum(1 for c in certs if c["kind"] == "certification"),
            "courses": sum(1 for c in certs if c["kind"] == "course"),
            "expired_certifications": sum(1 for c in certs if c["expired"]),
        },
        "warnings": list(result.get("warnings", [])),
        "schema_education": to_schema_education(result),
        "schema_certifications": to_schema_certifications(result),
    }
    log.info(
        "Academic profile: highest=%s field=%s, %d certification(s)",
        profile["highest_degree"] and profile["highest_degree"]["degree"],
        field,
        len(certs),
    )
    return profile


def profile_from_file(path, today=None):
    """PDF / DOCX file -> academic profile (extract -> segment -> parse -> profile)."""
    return build_academic_profile(parse_from_file(path, today))


def main(argv=None):
    args = argv if argv is not None else sys.argv[1:]
    if not args:
        print("usage: python -m parsers.academic_profile <resume.pdf|resume.docx>")
        return 1
    print(json.dumps(profile_from_file(args[0]), indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
