"""Validate resume / job JSON against the Day 4 schemas.

Usage (from the project root, venv active):
    python -m utils.schema_validator data/samples/sample_resume.json resume
    python -m utils.schema_validator data/samples/sample_job.json job
"""
import json
import logging
import sys
from pathlib import Path

from jsonschema import Draft7Validator

logger = logging.getLogger(__name__)

SCHEMA_DIR = Path(__file__).resolve().parent.parent / "data" / "schemas"
SCHEMA_FILES = {"resume": "resume_schema.json", "job": "job_schema.json"}


def load_json(path):
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def get_errors(data, kind):
    """Return a list of readable error strings (empty list = valid)."""
    schema = load_json(SCHEMA_DIR / SCHEMA_FILES[kind])
    validator = Draft7Validator(schema)
    errors = []
    for err in sorted(validator.iter_errors(data), key=lambda e: list(e.path)):
        location = ".".join(str(p) for p in err.path) or "(root)"
        errors.append(f"{location}: {err.message}")
    return errors


def validate_file(path, kind):
    errors = get_errors(load_json(path), kind)
    if errors:
        logger.warning("%s INVALID (%d problems)", path, len(errors))
        for e in errors:
            logger.warning("  - %s", e)
    else:
        logger.info("%s is a valid %s", path, kind)
    return not errors


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)s | %(name)s | %(message)s")
    if len(sys.argv) != 3 or sys.argv[2] not in SCHEMA_FILES:
        print("Usage: python -m utils.schema_validator <file.json> <resume|job>")
        sys.exit(2)
    sys.exit(0 if validate_file(sys.argv[1], sys.argv[2]) else 1)
