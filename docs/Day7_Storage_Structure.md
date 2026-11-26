# Day 7 - Storage Structure Documentation

**Goal:** one clear place and one clear format for every piece of AI data in Zecpath.

## 1. Where data lives

All pipeline data is saved under `data/store/` (created automatically; **not pushed to GitHub** because it can hold real candidate data).

```
data/store/
├── resumes/             original uploaded file + its .meta.json
├── parsed_profiles/     structured resume data (Day 4 resume schema)
├── ats_scores/          resume vs job match score
├── screening_reports/   screening answers summary
├── interview_results/   HR / technical interview scores
├── decisions/           final score and decision
├── lifecycle/           events.jsonl  (log of every stage change)
└── datasets/            frozen training snapshots (ats_training_v001, v002 ...)
```

Job data from Day 6 stays in `data/parsed_jobs/` (job_id based, not candidate based).

## 2. File naming

| Record type | File name | Why |
|---|---|---|
| resume | `cand_0001.v001.pdf` + `cand_0001.v001.meta.json` | one candidate |
| parsed_profile | `cand_0001.v001.json` | one candidate |
| ats_score / screening_report / interview_result / hiring_decision | `cand_0001__job_python_developer.v001.json` | one candidate **applying to one job** |

`v001`, `v002` ... = version number. **We never overwrite a file.** A new result is saved as the next version, so the history is kept.

## 3. Format of every JSON record

Every record has the same two parts: `metadata` (same fields everywhere, see the Metadata Standards document) and `data` (the actual AI result).

```json
{
  "metadata": { "candidate_id": "cand_0001", "job_id": "job_python_developer", "...": "..." },
  "data": { "score": 66.67, "required_skills": ["Python", "SQL", "Git"] }
}
```

## 4. What is inside `data` for each type

| Folder | Format | Main fields in `data` |
|---|---|---|
| resumes | PDF / DOCX (original, untouched) | the file itself; details in `.meta.json` |
| parsed_profiles | JSON | `email`, `skills`, `experience_years`, `extraction` (status, page_count, char_count). Later: full Day 4 resume schema |
| ats_scores | JSON | `score` (0-100), `required_skills`, `matched_skills` |
| screening_reports | JSON | `answered`, `total`, `missing` |
| interview_results | JSON | `hr_questions`, `technical_level`, `scores` (hr, technical, machine_test) |
| decisions | JSON | `final_score`, `decision` (selected / hold / rejected) |

Why JSON? Human-readable, works with every language, and matches the Day 4 schemas. When the data grows large we can move the same structure to a database (see section 6).

## 5. Safety rules

- Files are written to a temporary file first and then renamed, so a crash cannot leave a half-written record.
- Each record stores a `checksum_sha256`. If someone edits the file by hand, `verify_record()` returns `False`.
- Logs never contain names, emails or phone numbers (only IDs).
- `data/store/` is in `.gitignore`. Only fake sample data in `data/samples/pipeline_example/` is pushed.

## 6. Future growth (not built today)

| Today | Later |
|---|---|
| JSON files on disk | PostgreSQL / MongoDB tables with the same fields |
| `resumes/` folder | cloud storage (S3 / Azure Blob) |
| `events.jsonl` | event table or message queue |

Because every record already has `metadata` + `data`, moving them later only means changing `pipeline/storage.py`.
