"""Save and load AI records as versioned JSON files (never overwrite, always add a new version).

Folder layout (inside data/store/):
    resumes/            cand_0001.v001.pdf  +  cand_0001.v001.meta.json
    parsed_profiles/    cand_0001.v001.json
    ats_scores/         cand_0001__job_x.v001.json
    screening_reports/  cand_0001__job_x.v001.json
    interview_results/  cand_0001__job_x.v001.json
    decisions/          cand_0001__job_x.v001.json
    lifecycle/          events.jsonl   (written by lifecycle.py)
    datasets/           training snapshots (written by versioning.py)

Every JSON record has the shape:  {"metadata": {...}, "data": {...}}
"""
import hashlib
import json
import os
import re
import shutil
from pathlib import Path

from pipeline.metadata import CANDIDATE_ONLY, make_metadata, validate_metadata
from utils.logger import get_logger

log = get_logger(__name__)

STORE_ROOT = Path(__file__).resolve().parent.parent / "data" / "store"

FOLDERS = {
    "resume": "resumes",
    "parsed_profile": "parsed_profiles",
    "ats_score": "ats_scores",
    "screening_report": "screening_reports",
    "interview_result": "interview_results",
    "hiring_decision": "decisions",
}


def sha256_of(obj):
    """Fingerprint of any JSON-able data. If the data changes, the fingerprint changes."""
    text = json.dumps(obj, sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _base_name(record_type, candidate_id, job_id):
    if record_type in CANDIDATE_ONLY:
        return candidate_id
    return f"{candidate_id}__{job_id}"


def _folder(record_type, root):
    folder = Path(root) / FOLDERS[record_type]
    folder.mkdir(parents=True, exist_ok=True)
    return folder


def list_versions(record_type, candidate_id, job_id=None, root=STORE_ROOT):
    """Return the version numbers that already exist, e.g. [1, 2, 3]."""
    base = _base_name(record_type, candidate_id, job_id)
    pattern = re.compile(re.escape(base) + r"\.v(\d{3})\.(?!meta)")
    numbers = []
    for p in _folder(record_type, root).iterdir():
        match = pattern.match(p.name)
        if match and not p.name.endswith(".meta.json"):
            numbers.append(int(match.group(1)))
    return sorted(set(numbers))


def _write_json_safely(path, obj):
    """Write to a temp file first, then rename, so a crash never leaves a half-written file."""
    tmp = Path(str(path) + ".tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(obj, f, indent=2, ensure_ascii=False)
    os.replace(tmp, path)


def save_record(record_type, data, candidate_id, job_id=None, model_version=None, root=STORE_ROOT, **extra):
    """Save one AI result as the next version. Returns the path of the new file."""
    meta = make_metadata(record_type, candidate_id, job_id, model_version, **extra)
    problems = validate_metadata(meta)
    if problems:
        raise ValueError("Bad metadata: " + "; ".join(problems))

    version = (list_versions(record_type, candidate_id, job_id, root) or [0])[-1] + 1
    meta["data_version"] = version
    meta["checksum_sha256"] = sha256_of(data)

    name = f"{_base_name(record_type, candidate_id, job_id)}.v{version:03d}.json"
    path = _folder(record_type, root) / name
    _write_json_safely(path, {"metadata": meta, "data": data})
    log.info("Saved %s v%03d for %s", record_type, version, candidate_id)  # no personal data in logs
    return path


def save_resume_file(source_path, candidate_id, root=STORE_ROOT):
    """Copy the original resume (PDF/DOCX) into storage with a .meta.json beside it."""
    source_path = Path(source_path)
    version = (list_versions("resume", candidate_id, None, root) or [0])[-1] + 1
    folder = _folder("resume", root)
    stem = f"{candidate_id}.v{version:03d}"
    target = folder / (stem + source_path.suffix.lower())
    shutil.copy2(source_path, target)

    meta = make_metadata("resume", candidate_id, None, None, source_file=source_path.name)
    meta["data_version"] = version
    meta["checksum_sha256"] = hashlib.sha256(target.read_bytes()).hexdigest()
    _write_json_safely(folder / (stem + ".meta.json"), {"metadata": meta})
    log.info("Saved resume file v%03d for %s", version, candidate_id)
    return target


def load_record(record_type, candidate_id, job_id=None, version=None, root=STORE_ROOT):
    """Load one saved record. version=None means the latest version."""
    versions = list_versions(record_type, candidate_id, job_id, root)
    if not versions:
        raise FileNotFoundError(f"No {record_type} found for {candidate_id} {job_id or ''}".strip())
    chosen = version or versions[-1]
    name = f"{_base_name(record_type, candidate_id, job_id)}.v{chosen:03d}.json"
    with open(_folder(record_type, root) / name, "r", encoding="utf-8") as f:
        return json.load(f)


def verify_record(record):
    """True if the saved data still matches its checksum (nobody edited it by hand)."""
    return sha256_of(record["data"]) == record["metadata"]["checksum_sha256"]
