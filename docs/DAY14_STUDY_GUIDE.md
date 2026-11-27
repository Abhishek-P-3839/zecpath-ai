# Day 14 Study Guide: Candidate Ranking and Shortlisting

Task: sort candidates by score, create shortlisting thresholds, auto-reject and review zones, top candidate lists,
recruiter-friendly outputs.

| Deliverable | File |
|---|---|
| Auto-ranking engine | `ats_engine/ranking_engine.py` (already existed and was kept as it is) |
| Shortlisting automation module | `ats_engine/shortlisting.py` + `ats_engine/shortlist_config.json` |
| Ranked candidate output | `data/rankings/` and `data/shortlists/` (made by `python run_ranking_demo.py`) |

## The big picture

```
resumes --Day 13 generate_score()--> one ATS report per candidate
        --ranking_engine.build_ranking()--> sorted list (position, rank, ties, summary)
        --shortlisting.build_shortlist()--> zone + reasons + action for every candidate
        --> JSON / CSV / text files
```

The ranking engine only ORDERS people. The shortlisting module DECIDES the zone. The numbers (60, 50, ...) are in
`shortlist_config.json`, so a recruiter team can change them without touching Python.

## Position and rank (from the ranking engine)

- **position** is 1, 2, 3, 4: always unique, the reading order.
- **rank** is 1, 2, 2, 4: equal overall scores share a rank (shown as `T-2`).
- Sort order: overall score, then skill score, then experience score, then data completeness, then candidate id.
  The last rule makes the order the same every run.

## `ats_engine/shortlisting.py` in reading order

| Function | What it does |
|---|---|
| `check_thresholds(values, where)` | Returns a list of problems: scores must be 0-100, `reject_score` must not be above `shortlist_score`, `max_shortlist` is null or a whole number 1 or more, `max_missing_must_have` is 0 or more, `auto_reject` is true or false. An empty list means fine. |
| `validate_config(config)` | Checks the `default` section and every role override. |
| `load_config(path)` | Reads the JSON, validates it, raises `ValueError` listing every problem. |
| `resolve_thresholds(job, config, overrides)` | Builds the final numbers for one job. Order (later wins): default, role override (the job's `normalized_title`), the job's own `ats_cutoff_score`, command line. A job cutoff or a command-line cutoff moves the shortlist line and keeps the review-zone width (60/50 and cutoff 70 gives 70/60). `sources` says where each number came from. |
| `_n(number)` | Shows 60.0 as 60. |
| `zone_for(score, thresholds)` | The zone from the score alone. Exactly on the shortlist line = shortlisted. Exactly on the reject line = still review. |
| `zone_reason(...)` | One plain sentence about why. |
| `decide(row, thresholds)` | Zone, then safety rules 1 to 3 (below). Returns the decision, the reasons and the rules used. |
| `apply_capacity(candidates, max_shortlist)` | Safety rule 4: the extra shortlisted candidates become WAITLIST. A candidate tied with the last place keeps the place. |
| `make_candidate(row, thresholds)` | One output row: ranking facts + decision + action + reasons. |
| `build_warnings(...)` | Honest warnings (see below). |
| `build_shortlist(ranking, job, config, overrides, top_n)` | The main function. |
| `format_shortlist_text`, `to_csv`, `save_shortlist` | Recruiter outputs: text (counts first, then each zone), CSV for Excel, JSON. File names use f-strings (`job.v2.shortlist.json` keeps its dot). |
| `main` | The command line. |

## The four safety rules (run AFTER the zone)

1. **Low confidence**: too little data (for example a scanned PDF) means a person decides. Never auto-shortlist, never auto-reject.
2. **Too many missing must-have skills**: more than `max_missing_must_have` (default 3) sends a shortlisted candidate to REVIEW. A high score is not enough.
3. **Auto-reject switched off**: the reject zone becomes REVIEW.
4. **Capacity** (`max_shortlist`): extra qualified candidates become WAITLIST; ties with the last place stay together.

## Worked example: five fake candidates (thresholds 60 / 50, limit 3 missing skills)

| Candidate | Score | Confidence | Missing must-haves | Zone | Safety rule | Final |
|---|---|---|---|---|---|---|
| Asha | 82 | high | 0 | SHORTLISTED | none | **SHORTLISTED** |
| Ben | 74 | high | 4 (docker, aws, redis, kafka) | SHORTLISTED | rule 2: 4 is more than 3 | **REVIEW** |
| Chen | 74 | high | 0 | SHORTLISTED | none | **SHORTLISTED** |
| Dina | 58 | low | 0 | REVIEW | rule 1 (already review, noted) | **REVIEW** |
| Evan | 31 | high | 0 | REJECTED | none | **REJECTED** |

- Ben and Chen share rank 2 (same score 74), so the ranking shows `T-2` for both.
- Counts: 2 shortlisted, 2 review, 1 rejected.
- Warnings: "1 candidate(s) reached the shortlist score but a safety rule sent them to review: Ben" and "1 candidate(s) have low confidence: Dina".
- With `max_shortlist = 1`: Asha keeps the place, Chen becomes WAITLIST (rank 2 is after rank 1).
- If Evan had confidence "low" with score 31, he would go to REVIEW, not REJECTED (rule 1).

## Warnings: what they mean

- **Nobody reached the shortlist score**: no score was at or above the line. Check the cutoff or the job.
- **Reached the shortlist score but a safety rule sent them to review**: people qualified by score, but low confidence or missing skills held them back. This is a different problem from the one above, so it has its own message.
- **Waitlist**, **auto-reject OFF**, **low confidence**, **duplicate candidate ids** (the same person may have applied twice).

## How to run

```
python run_ranking_demo.py                      # all 4 jobs, writes data/rankings and data/shortlists
python -m ats_engine.shortlisting data/parsed_jobs/jd_mern_developer.profile.json data/raw_resumes
python -m ats_engine.shortlisting data/parsed_jobs/jd_mern_developer.profile.json --ranking data/rankings/job_mern_developer.ranking.json --cutoff 50 --max-shortlist 3 --top 3
python -m ats_engine.shortlisting <job.profile.json> data/raw_resumes --no-auto-reject
python -m unittest tests.test_shortlisting -v
python -m unittest discover -s tests -t .
```

## Reading the real sample results (honestly)

The sample resumes are tiny dummy files, so **nobody reaches 60 for any of the four jobs** (best scores: MERN 54.4,
Data Analyst Intern 57.3, HR Executive 44.2, Senior Python 43.4). The module reports this with the "Nobody reached" warning
instead of hiding it. The two scans (`img.pdf`, `sample_scanned.pdf`) score 0 but go to REVIEW, not REJECTED, because their
confidence is low.

## Self-check questions

1. Why does a candidate with score 95 and low confidence not get shortlisted? (Rule 1: with too little data a person must decide.)
2. A job has `ats_cutoff_score` 70 and the default width is 10. What are the lines? (Shortlist 70, reject 60.)
3. Three candidates tie for the last place and `max_shortlist` is 2. How many stay shortlisted? (All ties with the last place stay, so the whole tie group.)
4. Why are the thresholds in a JSON file and not in Python? (Change them without code and without new tests.)
5. Why is the "Nobody reached" warning different from the "safety rule" warning? (One is about the scores, the other about the rules; the fix is different.)
