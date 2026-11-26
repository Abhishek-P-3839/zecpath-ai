"""Metadata standard: every stored AI record carries the same 4 core fields.

Core fields (required):  candidate_id, job_id, model_version, timestamp
Extra fields added automatically: record_id, record_type, schema_version, data_version, checksum
"""
import re
import uuid
from datetime import datetime, timezone

SCHEMA_VERSION = "1.0"

# One entry per kind of AI data we store.
RECORD_TYPES = [
    "resume",            # the original uploaded file
    "parsed_profile",    # structured data pulled from the resume
    "ats_score",         # resume vs job match score
    "screening_report",  # screening answers summary
    "interview_result",  # HR / technical interview scores
    "hiring_decision",   # final score and decision
]

# Which record types belong to ONE candidate only (no job needed)
CANDIDATE_ONLY = {"resume", "parsed_profile"}

# Model version that produced each record type (change these when a model changes).
MODEL_VERSIONS = {
    "resume": "none",                       # raw file, no model involved
    "parsed_profile": "resume-parser-1.0.0",
    "ats_score": "ats-rules-1.0.0",
    "screening_report": "screening-1.0.0",
    "interview_result": "interview-1.0.0",
    "hiring_decision": "scoring-1.0.0",
}

CANDIDATE_ID_PATTERN = re.compile(r"^cand_[0-9]{4,}$")   # cand_0001
JOB_ID_PATTERN = re.compile(r"^job_[a-z0-9_]+$")          # job_hr_executive
MODEL_VERSION_PATTERN = re.compile(r"^(none|[a-z0-9-]+-[0-9]+\.[0-9]+\.[0-9]+)$")  # name-1.0.0
REQUIRED_FIELDS = ["candidate_id", "job_id", "model_version", "timestamp"]


def utc_now():
    """Return the current time as an ISO string in UTC, e.g. 2026-11-26T10:30:00Z."""
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def make_metadata(record_type, candidate_id, job_id=None, model_version=None, **extra):
    """Build the metadata dict for one record. job_id can be None for candidate-only records."""
    if record_type not in RECORD_TYPES:
        raise ValueError(f"Unknown record_type '{record_type}'. Use one of {RECORD_TYPES}")
    meta = {
        "record_id": "rec_" + uuid.uuid4().hex[:12],
        "record_type": record_type,
        "candidate_id": candidate_id,
        "job_id": job_id,
        "model_version": model_version or MODEL_VERSIONS[record_type],
        "timestamp": utc_now(),
        "schema_version": SCHEMA_VERSION,
    }
    meta.update(extra)   # e.g. source_file="alex.pdf"
    return meta


def validate_metadata(meta):
    """Return a list of problems (empty list = metadata is valid)."""
    errors = []
    for field in REQUIRED_FIELDS:
        if field not in meta:
            errors.append(f"missing field: {field}")
    if errors:
        return errors

    if not CANDIDATE_ID_PATTERN.match(str(meta["candidate_id"])):
        errors.append("candidate_id must look like cand_0001")
    record_type = meta.get("record_type")
    if record_type not in RECORD_TYPES:
        errors.append(f"record_type must be one of {RECORD_TYPES}")
    if record_type in CANDIDATE_ONLY:
        if meta["job_id"] is not None:
            errors.append(f"{record_type} must not have a job_id (set it to null)")
    elif not JOB_ID_PATTERN.match(str(meta["job_id"])):
        errors.append("job_id must look like job_hr_executive")
    if not MODEL_VERSION_PATTERN.match(str(meta["model_version"])):
        errors.append("model_version must look like name-1.0.0 (or 'none')")
    try:
        datetime.strptime(meta["timestamp"], "%Y-%m-%dT%H:%M:%SZ")
    except (TypeError, ValueError):
        errors.append("timestamp must look like 2026-11-26T10:30:00Z (UTC)")
    return errors
