# Day 12 - Matching Accuracy Report

Embedder evaluated: `hashing-offline`. Every number below was produced by `python run_matching_eval.py` (raw numbers: `data/matching/matching_eval.json`).

> **Read this first.** There are only 24 labeled pairs (6 resumes x 4 jobs) and the labels are my judgments, not a recruiter's. The numbers are **indicative, not statistically strong**. Cut-offs tuned on 24 pairs will move when more data is added.

## 1. Purpose

Day 12 asks for a semantic matcher, a resume-to-job similarity scorer, and evidence of how accurate it is. This report gives that evidence and turns the guessed label cut-offs (35 / 55 / 75) into tested ones.

## 2. Method

1. Every readable sample resume is parsed (Day 5 to 10 code) and scored against every parsed job with `matching/similarity_scorer.py`, which gives a similarity score from 0 to 100.
2. Each pair has a label from `data/samples/matching_ground_truth.json`: relevant / partly relevant / not relevant.
3. Two yes/no questions are measured: **Task A** 'is it relevant?' and **Task B** 'is it at least partly relevant?'. A pair is called a match when its score >= the cut-off. Task A decides the `good` label, task B the `partial` label.
4. Metrics: precision, recall, F1, accuracy, a threshold sweep, and ranking quality inside each job (`matching/evaluation.py`).
5. Validation across job types: **leave-one-job-out** (tune on 3 jobs, test on the 4th, repeat).

## 3. Dataset

- **Resumes in `data/raw_resumes`:** 9. **Scored:** 6 (`Maya.pdf`, `alex.pdf`, `marcus.pdf`, `sample_bullets_table.docx`, `sample_simple.pdf`, `sample_two_column.pdf`).
- **Unreadable (scans, listed separately, not counted as errors):** `img.pdf`, `sample_scanned.pdf`. The scorer returns status `unscorable` for them.
- **Not a resume:** `m.pdf` is the Day 2 architecture document, so it has no label and is reported separately (section 9).
- **Jobs:** 4 (data_analyst_intern, hr_executive, mern_developer, senior_python_messy).
- **Labeled pairs:** 24 = relevant 3, partly relevant 10, not relevant 11. 7 of them are marked *doubtful* (close calls).

**How the labels were made.** The labels are **judgments by Claude (an AI), not by a human recruiter**. Claude read each resume's extracted text and each job's profile and wrote one label and one reason per pair (`data/samples/matching_ground_truth.json`). The labels were written **before** the matcher was run on these pairs, so they were not adjusted to fit its scores. A person should review them, especially the doubtful ones listed in the file. Scale used:

- **relevant**: A recruiter would shortlist this person: most must-have skills and the right kind of work.
- **partly relevant**: Worth a look but with clear gaps: some must-have skills or a nearby role, or a seniority mismatch.
- **not relevant**: Wrong field or almost no overlap with the must-have skills.

Labels per job:

| Job | not relevant | partly relevant | relevant |
|---|---|---|---|
| mern_developer | 3 | 2 | 1 |
| senior_python_messy | 2 | 3 | 1 |
| hr_executive | 5 | 1 | 0 |
| data_analyst_intern | 1 | 4 | 1 |

## 4. Results

### 4.1 Do the scores separate the groups?

Similarity score (0-100) of the pairs, grouped by the label I gave them:

| Gold label | Pairs | Lowest | Average | Highest |
|---|---|---|---|---|
| relevant | 3 | 50 | 52.3 | 55 |
| not relevant | 11 | 0 | 4.0 | 13 |
| partly relevant | 10 | 7 | 22.7 | 33 |

### 4.2 Accuracy at the old (guessed) cut-offs vs the tuned cut-offs

Columns tp/fp/fn/tn = true positives / false positives / false negatives / true negatives. **Tuned = measured on the same 24 pairs it was tuned on, so it is optimistic** (see 6 for the honest test).

| Setting | Cut-off | tp/fp/fn/tn | Precision | Recall | F1 | Accuracy |
|---|---|---|---|---|---|---|
| relevant: old cut-off | 55 | 1/0/2/21 | 1 | 0.333 | 0.5 | 0.917 |
| relevant: tuned (in-sample) | 42 | 3/0/0/21 | 1 | 1 | 1 | 1 |
| at_least_partly: old cut-off | 35 | 3/0/10/11 | 1 | 0.231 | 0.375 | 0.583 |
| at_least_partly: tuned (in-sample) | 16 | 12/0/1/11 | 1 | 0.923 | 0.96 | 0.958 |

Ranking quality over all pairs (area under the curve, 1.0 = perfect, 0.5 = guessing): task A 1, task B 0.972.

### 4.3 Per job type (at the tuned cut-offs)

**Task A: relevant vs everything else (label 'good' cut-off)**, cut-off 42

| Job | tp/fp/fn/tn | Precision | Recall | F1 | Accuracy |
|---|---|---|---|---|---|
| mern_developer | 1/0/0/5 | 1 | 1 | 1 | 1 |
| senior_python_messy | 1/0/0/5 | 1 | 1 | 1 | 1 |
| hr_executive | 0/0/0/6 | n/a | n/a | n/a | 1 |
| data_analyst_intern | 1/0/0/5 | 1 | 1 | 1 | 1 |

**Task B: at least partly relevant vs not relevant (label 'partial' cut-off)**, cut-off 16

| Job | tp/fp/fn/tn | Precision | Recall | F1 | Accuracy |
|---|---|---|---|---|---|
| mern_developer | 3/0/0/3 | 1 | 1 | 1 | 1 |
| senior_python_messy | 3/0/1/2 | 1 | 0.75 | 0.857 | 0.833 |
| hr_executive | 1/0/0/5 | 1 | 1 | 1 | 1 |
| data_analyst_intern | 5/0/0/1 | 1 | 1 | 1 | 1 |

### 4.4 Ranking inside each job

Does the matcher put the better candidates higher? (`k` = number of at-least-partly relevant candidates)

| Job | All relevant above all not-relevant? | AUC (at least partly) | Precision@k | k | Order accuracy (all 3 levels) |
|---|---|---|---|---|---|
| mern_developer | yes | 1 | 1 | 3 | 1 |
| senior_python_messy | yes | 0.875 | 0.75 | 4 | 0.909 |
| hr_executive | n/a | 1 | 1 | 1 | 1 |
| data_analyst_intern | yes | 1 | 1 | 5 | 1 |

### 4.5 Which part carries the signal?

AUC of each part score alone for task B (higher = separates better):

| Part | Pairs with data | AUC |
|---|---|---|
| skills | 24 | 0.962 |
| experience | 24 | 0.86 |
| projects | 4 | 0.5 |

## 5. Threshold sweep and the chosen thresholds

For each cut-off T, a pair is called a match when its score is >= T. Step 5 shown here; the tuning used every whole number 0-100.

| T | A precision | A recall | A F1 | B precision | B recall | B F1 | B accuracy |
|---|---|---|---|---|---|---|---|
| 0 | 0.125 | 1 | 0.222 | 0.542 | 1 | 0.703 | 0.542 |
| 5 | 0.176 | 1 | 0.299 | 0.765 | 1 | 0.867 | 0.833 |
| 10 | 0.214 | 1 | 0.353 | 0.857 | 0.923 | 0.889 | 0.875 |
| 15 | 0.25 | 1 | 0.4 | 1 | 0.923 | 0.96 | 0.958 |
| 20 | 0.3 | 1 | 0.462 | 1 | 0.769 | 0.869 | 0.875 |
| 25 | 0.429 | 1 | 0.6 | 1 | 0.538 | 0.7 | 0.75 |
| 30 | 0.6 | 1 | 0.75 | 1 | 0.385 | 0.556 | 0.667 |
| 35 | 1 | 1 | 1 | 1 | 0.231 | 0.375 | 0.583 |
| 40 | 1 | 1 | 1 | 1 | 0.231 | 0.375 | 0.583 |
| 45 | 1 | 1 | 1 | 1 | 0.231 | 0.375 | 0.583 |
| 50 | 1 | 1 | 1 | 1 | 0.231 | 0.375 | 0.583 |
| 55 | 1 | 0.333 | 0.5 | 1 | 0.077 | 0.143 | 0.5 |
| 60 | n/a | 0 | n/a | n/a | 0 | n/a | 0.458 |
| 65 | n/a | 0 | n/a | n/a | 0 | n/a | 0.458 |
| 70 | n/a | 0 | n/a | n/a | 0 | n/a | 0.458 |
| 75 | n/a | 0 | n/a | n/a | 0 | n/a | 0.458 |
| 80 | n/a | 0 | n/a | n/a | 0 | n/a | 0.458 |
| 85 | n/a | 0 | n/a | n/a | 0 | n/a | 0.458 |
| 90 | n/a | 0 | n/a | n/a | 0 | n/a | 0.458 |
| 95 | n/a | 0 | n/a | n/a | 0 | n/a | 0.458 |
| 100 | n/a | 0 | n/a | n/a | 0 | n/a | 0.458 |

**Chosen thresholds** (saved in `matching/similarity_thresholds.json`):

- `good` = **42** (best F1 for task A; when several cut-offs tie, the middle one is used because the edge of a tie is fragile).
- `partial` = **16** (best F1 for task B, same tie rule).
- `strong` = **75** (NOT tuned: it is the old value. No pair in this data set can tell 'strong' from 'good'; the highest score seen is 55).
- Scores below `partial` are labeled `weak`.

- Task A gap: highest non-match score 33, lowest match score 50; the cut-off 42 sits in that 17-point gap.
- Task B gap: highest non-match score 13, lowest match score 7; the two groups OVERLAP by 6 point(s), so no cut-off is error-free and 16 trades the errors listed in section 8.

## 6. Leave-one-job-out validation

For each job: pick the cut-off using only the OTHER three jobs, then test it on the held-out job. This is the closest thing to 'would it work on a job type it has not seen'.

**Task A: relevant vs everything else (label 'good' cut-off)**

| Held-out job | Cut-off tuned on other 3 | tp/fp/fn/tn | Precision | Recall | F1 | Accuracy |
|---|---|---|---|---|---|---|
| mern_developer | 39 | 1/0/0/5 | 1 | 1 | 1 | 1 |
| senior_python_messy | 42 | 1/0/0/5 | 1 | 1 | 1 | 1 |
| hr_executive | 42 | 0/0/0/6 | n/a | n/a | n/a | 1 |
| data_analyst_intern | 43 | 1/0/0/5 | 1 | 1 | 1 | 1 |

Pooled over the 4 held-out jobs: precision 1, recall 1, F1 1, accuracy 1 (3/0/0/21). In-sample F1 with all jobs was 1.
The tuned cut-off ranged from 39 to 43 (spread 4). That is a small change between folds.
Folds with mistakes: none.

**Task B: at least partly relevant vs not relevant (label 'partial' cut-off)**

| Held-out job | Cut-off tuned on other 3 | tp/fp/fn/tn | Precision | Recall | F1 | Accuracy |
|---|---|---|---|---|---|---|
| mern_developer | 16 | 3/0/0/3 | 1 | 1 | 1 | 1 |
| senior_python_messy | 16 | 3/0/1/2 | 1 | 0.75 | 0.857 | 0.833 |
| hr_executive | 13 | 1/1/0/4 | 0.5 | 1 | 0.667 | 0.833 |
| data_analyst_intern | 16 | 5/0/0/1 | 1 | 1 | 1 | 1 |

Pooled over the 4 held-out jobs: precision 0.923, recall 0.923, F1 0.923, accuracy 0.917 (12/1/1/10). In-sample F1 with all jobs was 0.96.
The tuned cut-off ranged from 13 to 16 (spread 3). That is a small change between folds.
Folds with mistakes: senior_python_messy (false positives 0, false negatives 1), hr_executive (false positives 1, false negatives 0).

## 7. Testing SKILL_SEMANTIC_THRESHOLD (currently 0.70)

Every pair was re-scored with each value (the engine file was not changed). 'Related matches' = how many times a job skill was matched to a *different* resume skill.

| Value | Related matches | AUC task A | AUC task B | Order accuracy | Best F1 A | Best F1 B |
|---|---|---|---|---|---|---|
| 0.5 | 1 | 1 | 0.972 | 0.977 | 1 | 0.96 |
| 0.6 | 1 | 1 | 0.972 | 0.977 | 1 | 0.96 |
| 0.7 | 1 | 1 | 0.972 | 0.977 | 1 | 0.96 |
| 0.8 | 1 | 1 | 0.972 | 0.977 | 1 | 0.96 |
| 0.9 | 0 | 1 | 0.976 | 0.98 | 1 | 0.96 |

Related-skill pairs found at a low cut-off of 0.5 (so you can judge by eye which look sensible):

| Job skill | Resume skill | Similarity | First seen in |
|---|---|---|---|
| kubernetes | excel | 0.83 | alex.pdf vs jd_senior_python_messy |

**Reading.** Across all 24 pairs the offline embedder found only 1 related-skill pair(s) even at 0.5. Values 0.5 to 0.8 give identical results, so the data cannot tell them apart. Real neighbours such as react/vue or python/django score near 0 with this embedder, so the pair(s) above are not genuine skill relations. A single-word text becomes a vector with one to three features, and with 2048 hash buckets two unrelated words can land in the same bucket. That is what a similarity as high as 0.83 between unrelated skills means here. **Verdict: this threshold cannot be validated with the offline embedder on this data.** Recommendation (not applied; the engine file is unchanged): keep 0.70 for now, re-test with the neural embedder, and if the offline embedder stays, use 0.9 or more or a larger `dims` in `HashingEmbedder`.

## 8. Error analysis (every false positive and false negative at the chosen cut-offs)

**Task A: relevant vs everything else (label 'good' cut-off)**, cut-off 42

No errors on these 24 pairs (in-sample; see section 6 for unseen-job behaviour).

**Task B: at least partly relevant vs not relevant (label 'partial' cut-off)**, cut-off 16

| Error | Pair | My label | Score | Parts | Likely cause |
|---|---|---|---|---|---|
| false negative | sample_simple.pdf vs senior_python_messy | partly relevant | 7 | skills 12, experience 0, projects - | The resume is 132 characters: only Python of the 12 must-have skills is present and the experience line ('Intern at Demo Corp') shares no words with the job, so experience scores 0. The matcher sees too little text. It is a thin resume, and my 'partly relevant' label is a judgment about the skills, not about the text. |

**Extra mistakes in leave-one-job-out folds** (the cut-off was tuned without that job):

| Task | Held-out job | Fold cut-off | Resume | My label | Score | Error | Likely cause |
|---|---|---|---|---|---|---|---|
| at_least_partly | senior_python_messy | 16 | sample_simple.pdf | partly relevant | 7 | false negative | The resume is 132 characters: only Python of the 12 must-have skills is present and the experience line ('Intern at Demo Corp') shares no words with the job, so experience scores 0. The matcher sees too little text. It is a thin resume, and my 'partly relevant' label is a judgment about the skills, not about the text. |
| at_least_partly | hr_executive | 13 | Maya.pdf | not relevant | 13 | false positive | Only one skill is shared: 'crm' (she integrated CRM tools as an engineer). One of the four must-have skills gives a skills score of 15, which is just enough to reach the fold cut-off of 13. The skill overlap is real but the role overlap is not. |

## 9. Special cases

- **Scanned resumes** (`img.pdf`, `sample_scanned.pdf`): the scorer returns `status: unscorable` with a reason and no score. They are not counted as errors. OCR would be needed to read them.
- **`m.pdf` (not a resume)** scored against each job: data_analyst_intern 7, hr_executive 10, mern_developer 23, senior_python_messy 14. The scorer has no way to know a document is not a resume. A document-type check belongs earlier in the pipeline.

## 10. Offline vs neural embedder

### Neural comparison

| Embedder | Cut-off A | AUC A | Cut-off B | AUC B |
|---|---|---|---|---|
| hashing-offline | 42 | 1 | 16 | 0.972 |
| all-MiniLM-L6-v2 | 42 | 1 | 17 | 0.92 |

## 11. Limits

- **Small data.** 24 pairs; only 3 are 'relevant'. Task A was tuned on 3 positives, so its perfect scores prove very little. The cut-offs will move with more data.
- **Labels are one AI's judgment**, not a recruiter's. The close calls are: Maya.pdf vs senior_python_messy; alex.pdf vs hr_executive; marcus.pdf vs hr_executive; marcus.pdf vs data_analyst_intern; sample_simple.pdf vs mern_developer; sample_simple.pdf vs data_analyst_intern; sample_two_column.pdf vs data_analyst_intern.
- **Tiny resumes.** `sample_simple`, `sample_two_column` and `sample_bullets_table` have only about 130-250 characters of text each, so their scores rest on very little evidence.
- **Tuned and tested on the same people.** Leave-one-job-out leaves a *job* out, but the same six resumes appear in every fold, so it does not test unseen resumes. Task B cut-off spread across folds: 3 points.
- **`strong` (75) is untested**: the highest score seen is 55, so with this embedder no sample pair is ever labeled `strong`.
- **Hash collisions** in the offline embedder (section 7) can create a false 'related skill'.
- **Skill gaps may come from skill extraction**, not matching: a must-have the resume implies but never names (for example `communication`) is reported as missing.
- Neural and offline embedders were both evaluated.

## 12. Recommendations

1. Have a recruiter review `data/samples/matching_ground_truth.json` (start with the doubtful pairs), then re-run `python run_matching_eval.py`.
2. Add more labeled resumes per job (at least 10 relevant and 10 not relevant per job) before trusting the cut-offs; include longer, more realistic resumes.
3. Install `sentence-transformers` and re-run: the report then compares both embedders and re-tests `SKILL_SEMANTIC_THRESHOLD` with real semantic neighbours.
4. Do not change `SKILL_SEMANTIC_THRESHOLD` yet (section 7). Consider a larger `dims` in `HashingEmbedder` or comparing skills by taxonomy before hashing.
5. Add a document-type check so non-resumes such as `m.pdf` are rejected before scoring, and OCR for scans.
6. Use the `good` and `partial` cut-offs from `matching/similarity_thresholds.json` for shortlisting decisions only together with a human review for now.

