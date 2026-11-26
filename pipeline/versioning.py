"""Training datasets: freeze a versioned snapshot of stored AI data for retraining.

Rules (also written in docs/Day7_Pipeline_Lifecycle_Versioning.md):
  * A snapshot is NEVER edited after it is created. New data -> new version (v001, v002 ...).
  * Personal data (name, email, phone, links) is removed before it goes into a dataset.
  * Only records that have a final hiring decision are used as labelled examples.
  * manifest.json records what is inside, which model versions made it, and a checksum.
"""
import json
from pathlib import Path

from pipeline.metadata import utc_now
from pipeline.storage import STORE_ROOT, FOLDERS, load_record, sha256_of

PII_KEYS = {"name", "full_name", "email", "phone", "linkedin", "github", "portfolio", "links", "source_file"}


def remove_personal_data(obj):
    """Return a copy of obj with personal fields removed (works on nested dicts/lists)."""
    if isinstance(obj, dict):
        return {k: remove_personal_data(v) for k, v in obj.items() if k not in PII_KEYS}
    if isinstance(obj, list):
        return [remove_personal_data(v) for v in obj]
    return obj


def _decision_files(root):
    folder = Path(root) / FOLDERS["hiring_decision"]
    return sorted(folder.glob("*.v*.json")) if folder.exists() else []


def next_dataset_version(name, root=STORE_ROOT):
    base = Path(root) / "datasets"
    base.mkdir(parents=True, exist_ok=True)
    existing = [int(p.name.rsplit("_v", 1)[1]) for p in base.glob(f"{name}_v*") if p.name.rsplit("_v", 1)[1].isdigit()]
    return (max(existing) if existing else 0) + 1


def build_training_snapshot(name="ats_training", root=STORE_ROOT):
    """Join profile + ATS + decision for each decided candidate and freeze it as a new dataset version."""
    rows, model_versions = [], set()
    for decision_path in _decision_files(root):
        decision = json.loads(decision_path.read_text(encoding="utf-8"))
        meta = decision["metadata"]
        cand, job = meta["candidate_id"], meta["job_id"]
        try:
            profile = load_record("parsed_profile", cand, None, root=root)
            ats = load_record("ats_score", cand, job, root=root)
        except FileNotFoundError:
            continue    # incomplete journey -> not usable as an example
        model_versions.update([profile["metadata"]["model_version"], ats["metadata"]["model_version"],
                               meta["model_version"]])
        rows.append(remove_personal_data({
            "candidate_id": cand, "job_id": job,
            "profile": profile["data"], "ats": ats["data"], "label": decision["data"],
        }))

    version = next_dataset_version(name, root)
    folder = Path(root) / "datasets" / f"{name}_v{version:03d}"
    folder.mkdir(parents=True)
    with open(folder / "data.jsonl", "w", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")
    manifest = {
        "dataset_name": name, "dataset_version": version, "created_at": utc_now(),
        "record_count": len(rows), "model_versions_used": sorted(model_versions),
        "personal_data_removed": True, "checksum_sha256": sha256_of(rows),
        "note": "Frozen snapshot. Do not edit. Create a new version instead.",
    }
    (folder / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    return folder, manifest
