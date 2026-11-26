# Day 7 - Data Lifecycle, Versioning and Retraining Plan

Diagram: `docs/pipeline_diagram.png` (source `pipeline_diagram.dot`, also `.svg`).

## 1. Lifecycle: upload to hiring decision

| # | Stage (`events.jsonl`) | What happens | Saved to | Code |
|---|---|---|---|---|
| 1 | `uploaded` | original resume stored untouched | `resumes/` | `save_resume_file()` |
| 2 | `parsed` | text extracted, cleaned, structured | `parsed_profiles/` | `extract_resume()`, `parse_resume_text()` |
| 3 | `ats_scored` | resume compared with job profile | `ats_scores/` | `calculate_ats_score()` |
| 4 | `screened` | screening answers summarised | `screening_reports/` | `build_screening_report()` |
| 5 | `interviewed` | HR + technical scores | `interview_results/` | `interview_ai/` |
| 6 | `decided` | scores combined, decision made | `decisions/` | `combine_scores()`, `get_decision()` |

Extra end states at any time: `rejected`, `withdrawn`, `deleted`.
**A stage cannot be skipped** (`record_event` raises an error). Every stage change is one line in `lifecycle/events.jsonl`, so we can see where a candidate is and what happened before.

## 2. Versioning

**Records:** never overwritten. Re-running ATS after a model upgrade creates `...v002.json` next to `...v001.json`. The latest version is used by default; old versions stay for audit and comparison.

**Models:** `model_version` (see Metadata Standards).

**Schemas:** `schema_version` inside metadata and in the Day 4 schemas. If a field changes, the schema version goes up.

**Datasets:** each training snapshot is a new folder `datasets/<name>_vNNN/` and is never edited afterwards.

## 3. Retraining datasets

`pipeline/versioning.py -> build_training_snapshot()` does the following:

1. Finds every candidate+job that has a final **decision** (the label).
2. Joins the parsed profile, ATS score and decision.
3. Removes personal data (name, email, phone, links, file name).
4. Writes `data.jsonl` (one example per line) and `manifest.json` (dataset version, date, record count, model versions used, checksum).

### Retraining rules

| Rule | Reason |
|---|---|
| Only use records with a final decision | they are the labelled examples |
| Remove personal data before training | privacy |
| Never edit a snapshot; create a new version | experiments stay repeatable |
| Keep train / validation / test split fixed per dataset version | fair comparison between models |
| Record the dataset version in the new `model_version` notes | we know what data trained which model |
| Retrain when: 500+ new decided records, or score drift is noticed, or the job schema changes | simple starting trigger (to be tuned later) |
| Compare new model vs old model on the same test set before release | do not ship a worse model |

## 4. Retention (planned policy)

- Raw resumes and profiles: delete on candidate request or after the agreed retention period.
- Datasets contain no personal data, so they can be kept longer.
- Event log keeps only IDs and stage names.
