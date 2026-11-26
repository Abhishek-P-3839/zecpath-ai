# Day 7 - Metadata Standards

Every stored AI record carries the same metadata, so any file can be traced back to **who, which job, which model, and when**.

## 1. Required fields (the 4 from the task)

| Field | Format | Example | Rule |
|---|---|---|---|
| `candidate_id` | `cand_` + 4 or more digits | `cand_0001` | never use name or email as an ID |
| `job_id` | `job_` + lowercase letters/digits/underscore | `job_python_developer` | `null` for resume and parsed_profile (they belong to the candidate, not a job) |
| `model_version` | `name-MAJOR.MINOR.PATCH` or `none` | `ats-rules-1.0.0` | `none` for raw resume files |
| `timestamp` | UTC ISO 8601 | `2026-11-26T10:30:00Z` | always UTC, always ends with `Z` |

## 2. Fields added automatically

| Field | Example | Meaning |
|---|---|---|
| `record_id` | `rec_568954dab50f` | unique ID of this one record |
| `record_type` | `ats_score` | one of: resume, parsed_profile, ats_score, screening_report, interview_result, hiring_decision |
| `schema_version` | `1.0` | version of this metadata standard |
| `data_version` | `2` | version number of this record (v001, v002 ...) |
| `checksum_sha256` | `4fcbd3...` | fingerprint of `data` to detect edits |
| `source_file` (optional) | `alex.pdf` | original file name, when relevant |

## 3. Model version rules

- Format: `<model-name>-<major>.<minor>.<patch>`.
- **patch** = bug fix, same results expected. **minor** = better logic, results may change a little. **major** = new approach, results not comparable with the old one.
- Change the version in `MODEL_VERSIONS` in `pipeline/metadata.py` whenever the logic of that module changes.
- Current versions: resume-parser-1.0.0, ats-rules-1.0.0, screening-1.0.0, interview-1.0.0, scoring-1.0.0.

## 4. Complete example

```json
{
  "record_id": "rec_568954dab50f",
  "record_type": "ats_score",
  "candidate_id": "cand_0001",
  "job_id": "job_python_developer",
  "model_version": "ats-rules-1.0.0",
  "timestamp": "2026-11-26T07:22:30Z",
  "schema_version": "1.0",
  "data_version": 1,
  "checksum_sha256": "4fcbd3c2a5bfec05c55ec263398fda58ee5b8d7afd598eb23e9834bb67c2618c"
}
```

## 5. Validation

`pipeline/metadata.py -> validate_metadata(meta)` returns a list of problems (empty list = valid). `save_record()` calls it and **refuses to save** bad metadata.

## 6. Why these fields

- `candidate_id` + `job_id`: join ATS, screening, interview and decision for the same application.
- `model_version`: when a model is improved we can compare old and new scores and know which model made each result.
- `timestamp`: shows the order of events and supports audit and data-retention rules.
