"""Lifecycle of AI data from upload to hiring decision.

Stages run in this order; a candidate cannot skip a stage.
Every step is written to data/store/lifecycle/events.jsonl (one JSON line per event),
so we can always answer "where is this candidate now and what happened before?".
"""
import json
from pathlib import Path

from pipeline.metadata import utc_now
from pipeline.storage import STORE_ROOT

STAGES = [
    "uploaded",        # resume file stored
    "parsed",          # parsed profile stored
    "ats_scored",      # ATS score stored
    "screened",        # screening report stored
    "interviewed",     # interview result stored
    "decided",         # final decision stored
]
# Extra end-states that can happen at any time
EXIT_STATUSES = ["rejected", "withdrawn", "deleted"]


def _events_file(root):
    folder = Path(root) / "lifecycle"
    folder.mkdir(parents=True, exist_ok=True)
    return folder / "events.jsonl"


def record_event(candidate_id, job_id, stage, note="", root=STORE_ROOT):
    """Add one line to the event log. Raises ValueError if a stage is skipped."""
    if stage not in STAGES + EXIT_STATUSES:
        raise ValueError(f"Unknown stage '{stage}'")
    current = get_stage(candidate_id, job_id, root)
    if stage in STAGES:
        wanted = STAGES.index(stage)
        have = STAGES.index(current) if current in STAGES else -1
        if wanted > have + 1:
            raise ValueError(f"Cannot go from '{current}' to '{stage}': a stage was skipped")
    event = {"timestamp": utc_now(), "candidate_id": candidate_id, "job_id": job_id,
             "stage": stage, "note": note}
    with open(_events_file(root), "a", encoding="utf-8") as f:
        f.write(json.dumps(event, ensure_ascii=False) + "\n")
    return event


def get_history(candidate_id, job_id, root=STORE_ROOT):
    """All events for this candidate + job, oldest first."""
    path = _events_file(root)
    if not path.exists():
        return []
    events = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
    return [e for e in events if e["candidate_id"] == candidate_id and e["job_id"] == job_id]


def get_stage(candidate_id, job_id, root=STORE_ROOT):
    """The latest stage, or None if the candidate has no events yet."""
    history = get_history(candidate_id, job_id, root)
    return history[-1]["stage"] if history else None
