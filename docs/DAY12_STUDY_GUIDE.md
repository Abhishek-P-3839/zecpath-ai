# Day 12 Study Guide: Resume-JD Similarity Scorer and Matching Accuracy Report

Read this after `docs/Day12_Matching_Accuracy_Report.md`. It explains the new code in reading order.
The semantic engine itself (`matching/semantic_engine.py`, `matching/embedders.py`) was finished earlier and is not changed.

## The big picture

```
resume file --> views (skills / experience / projects text) --\
                                                               +--> SemanticMatcher.match --> 0-100 score
job profile + job doc --> job_views --------------------------/                                  |
                                                                                    label from similarity_thresholds.json
```

- **Embedding**: text turned into a list of numbers so that similar meaning gives similar numbers.
- **Cosine similarity**: how close two such lists are (0 = unrelated, 1 = identical).
- **Threshold**: a cut-off. "Score >= 42 means good" is a threshold. Tuning = picking it from evidence, not by guessing.

## 1. `matching/similarity_scorer.py` (reading order)

| Function | What it does |
|---|---|
| `validate_thresholds(config)` | Checks the JSON: needs `strong`, `good`, `partial`, all numbers 0-100, and `strong > good > partial`. Returns a list of problems (empty = fine). Same idea as `ats_engine/weights.py`. |
| `load_thresholds(path)` | Reads `matching/similarity_thresholds.json`, validates it, caches it. Raises `ValueError` listing every problem. |
| `label_for(score, thresholds)` | Score to label. A score exactly on a cut-off gets the higher label (55 with good=55 is `good`). Below `partial` = `weak`. |
| `_looks_like_path`, `default_name`, `resume_to_views` | Accept a file path, resume text, or ready views. A one-line string ending in `.pdf`/`.docx` is treated as a file name, so a typo raises `FileNotFoundError` instead of being scored as text. A scan or failed extraction returns a *problem* instead of views. |
| `_has_words`, `_has_resume_data`, `_has_job_data` | "Is there anything to compare?" `_has_words` exists because an empty job still builds the text `". ."`. |
| `_unscorable(...)` | The result for something that cannot be scored: status `unscorable`, score `None`, never a fake 0. |
| `_names`, `build_reasons` | Short plain-English sentences (has N of M must-haves, missing ones, related skills, weakest part, parts with no data). |
| `score_resume_to_job(resume, job_profile, job_doc, matcher)` | The main function. Builds views, calls `matcher.match`, converts parts to 0-100, picks the label, lists missing must-haves, builds reasons. |
| `score_many(resumes, job_profile, ...)` | Scores a list (or `{name: resume}`) against one job with ONE matcher, so embeddings are reused. Sorted best first, unscorable last, ties by name. |
| `format_result`, `main` | The command line: `python -m matching.similarity_scorer <resume> <job.profile.json>` (add `--json` for raw output). |

## 2. `matching/evaluation.py` (pure functions, no printing)

| Function | Meaning |
|---|---|
| `confusion_matrix` | Counts `tp` (said match, is match), `fp` (said match, is not), `fn` (said no, is match), `tn`. |
| `precision` | `tp / (tp + fp)`: when we say match, how often are we right? |
| `recall` | `tp / (tp + fn)`: of the real matches, how many did we find? |
| `f1_score` | One number combining both. A metric that cannot be computed is `None`, never 0. |
| `accuracy` | `(tp + tn) / all`. |
| `evaluate_at_threshold`, `threshold_sweep` | Say "match" when score >= T, then measure; repeat for many T. |
| `best_threshold` | Best F1 (accuracy breaks ties). If many tie, take the middle one (the edge of a tie is fragile). |
| `pairwise_auc` | Chance a random real match scores above a random non-match. 1.0 = perfect, 0.5 = guessing. |
| `precision_at_k`, `pairwise_order_accuracy`, `ranking_quality`, `group_stats` | Ranking inside one job and score ranges per label. |
| `leave_one_job_out` | Validation across job types: tune on 3 jobs, test on the 4th, repeat. The held-out job never chooses its own cut-off. |

## 3. `run_matching_eval.py`

`load_ground_truth` / `load_jobs` / `load_views` read inputs. `score_pairs` scores each labeled pair with the new scorer.
`task_analysis` does the sweep, tuning, leave-one-job-out and error list for one yes/no task. The two tasks:

- **Task A**: relevant vs everything else. Its cut-off becomes the `good` label.
- **Task B**: at least partly relevant vs not relevant. Its cut-off becomes the `partial` label.

`skill_threshold_study` re-scores everything with different `SKILL_SEMANTIC_THRESHOLD` values (the engine file is not edited;
the value is changed temporarily in memory). `build_report` writes the Markdown from the numbers of this run.
`--write-thresholds` saves the chosen cut-offs to the JSON file.

## 4. Worked example: Maya vs the MERN developer job

Run: `python -m matching.similarity_scorer data/raw_resumes/Maya.pdf data/parsed_jobs/jd_mern_developer.profile.json`

**Skills part.** The job has 9 must-have skills and 4 good-to-have skills.
- Maya matches 4 must-haves exactly (node.js, react, javascript, git): 4/9 = 0.444.
- She matches all 4 good-to-haves (aws, docker, ci/cd, typescript): 4/4 = 1.0.
- Coverage = 0.75 x 0.444 + 0.25 x 1.0 = **0.583**.
- Cosine of her whole skill list against the job's skill list = 0.538. Calibrated: (0.538 - 0.05) / (0.60 - 0.05) = 0.887.
- Skills score = 0.6 x 0.583 + 0.4 x 0.887 = **0.705** (printed as 70; Python rounds 70.5 down).

**Experience part.** Cosine of her experience text against the job text = 0.201. Calibrated: (0.201 - 0.05) / 0.55 = **0.274**.

**Projects part.** Maya has no projects section, so it is skipped and its weight is shared.
Weights are skills 0.45 and experience 0.35, re-scaled to 0.5625 and 0.4375.

**Overall** = 100 x (0.705 x 0.5625 + 0.274 x 0.4375) = 51.65, shown as **52/100**.
With the tuned cut-offs (partial 16, good 42, strong 75) that is **good**.
Missing must-haves: rest api, express, redux, mongodb, communication.

## 5. How to read the report honestly

- 24 pairs and only 3 "relevant" ones: **indicative, not proof**.
- The labels are Claude's judgments. Review `data/samples/matching_ground_truth.json`.
- "Tuned" numbers are measured on the data they were tuned on, so they are optimistic. The leave-one-job-out table is the fairer one.
