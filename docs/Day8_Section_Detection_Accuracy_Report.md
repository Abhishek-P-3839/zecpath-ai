# Day 8 - Section Detection Accuracy Report

How well does the Resume Section Classifier (`parsers/section_classifier.py`) put each line of a resume into the right section? Every number below is **per line**, measured against answer keys labeled by hand (`data/labeled_resumes/`).

## 1. Headline results

| Test set | Resumes | Lines | Rules only | Hybrid (rules + NLP) |
|---|---|---|---|---|
| All samples | 20 | 306 | 84.3% | **98.4%** |
| Real resumes (Day 5 output) | 6 | 114 | 99.1% | **100.0%** |
| Hand-written, dev (used for tuning) | 6 | 78 | 74.4% | **100.0%** |
| Hand-written, holdout (never tuned on) | 8 | 114 | 76.3% | **95.6%** |

**Read the holdout row as the honest estimate.** The dev and real rows are the samples the rules were tuned on, so they are optimistic. The holdout resumes were written before tuning and were not used to adjust any weight.

On the holdout set, content lines only (lines that are *not* headings) are 94.3% correct, because heading lines are easy and push the plain accuracy up. Over all samples the content-line accuracy is 97.9%; the macro-F1 (average of the per-section F1 scores) is 0.971.

## 2. Accuracy by resume layout (hybrid, all samples)

| Layout | Correct / Lines | Accuracy | Rules only |
|---|---|---|---|
| alt_headings | 20 / 20 | 100.0% | 100.0% |
| caps_headings | 19 / 19 | 100.0% | 100.0% |
| combined_heading | 36 / 37 | 97.3% | 91.9% |
| inline_headings | 11 / 11 | 100.0% | 100.0% |
| no_headings | 45 / 49 | 91.8% | 16.3% |
| numbered_headings | 15 / 15 | 100.0% | 100.0% |
| other_sections | 18 / 18 | 100.0% | 100.0% |
| partial_headings | 11 / 11 | 100.0% | 81.8% |
| standard | 68 / 68 | 100.0% | 100.0% |
| table | 19 / 19 | 100.0% | 100.0% |
| two_column | 25 / 25 | 100.0% | 92.0% |
| typo_headings | 14 / 14 | 100.0% | 100.0% |

The rules-only column is the baseline (headings found, everything before the first heading is called *header*). It collapses on resumes with no headings, which is exactly what the NLP layer is for.

## 3. Per-section quality (hybrid, all samples)

| Section | Precision | Recall | F1 | Lines |
|---|---|---|---|---|
| header | 1.0 | 1.0 | 1.0 | 36 |
| summary | 1.0 | 1.0 | 1.0 | 32 |
| skills | 0.915 | 1.0 | 0.956 | 43 |
| experience | 0.991 | 1.0 | 0.995 | 106 |
| education | 1.0 | 1.0 | 1.0 | 44 |
| certifications | 1.0 | 0.895 | 0.944 | 19 |
| projects | 1.0 | 0.889 | 0.941 | 18 |
| other | 1.0 | 0.875 | 0.933 | 8 |

## 4. Confusion matrix (hybrid, all samples)

Rows = the correct section, columns = what the classifier said. Only the off-diagonal cells are mistakes.

| correct \ predicted | header | summary | skills | experience | education | certifications | projects | other |
|---|---|---|---|---|---|---|---|---|
| **header** | 36 | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
| **summary** | 0 | 32 | 0 | 0 | 0 | 0 | 0 | 0 |
| **skills** | 0 | 0 | 43 | 0 | 0 | 0 | 0 | 0 |
| **experience** | 0 | 0 | 0 | 106 | 0 | 0 | 0 | 0 |
| **education** | 0 | 0 | 0 | 0 | 44 | 0 | 0 | 0 |
| **certifications** | 0 | 0 | 2 | 0 | 0 | 17 | 0 | 0 |
| **projects** | 0 | 0 | 1 | 1 | 0 | 0 | 16 | 0 |
| **other** | 0 | 0 | 1 | 0 | 0 | 0 | 0 | 7 |

## 5. Every mistake (hybrid, all samples)

| Sample | Line | Correct | Predicted | Why (method, confidence) | Text |
|---|---|---|---|---|---|
| hold_combined_heading | 11 | certifications | skills | heading+nlp, 0.55 | AWS Certified Developer - Associate |
| hold_no_headings_wrapped | 9 | projects | experience | content, 0.47 | Online Quiz Portal - developed with React, Express and MongoDB |
| hold_no_headings_wrapped | 10 | projects | skills | content, 0.47 | Weather Dashboard app using public APIs, deployed on Netlify |
| hold_no_headings_extras | 11 | certifications | skills | content, 0.35 | ACCA Qualification, 2017 |
| hold_no_headings_extras | 13 | other | skills | content, 0.57 | Languages: Arabic, English, French |

## 6. What the mistakes teach us

- **Context can override a clear line.** An obvious certification line sitting between two skills lines can be pulled into *skills* by the smoothing step. A stronger fix is a sequence model (Viterbi / CRF) that also learns typical section order.
- **Missing vocabulary.** `ACCA Qualification` and `Languages: Arabic, English, French` fail because the keyword lists in `parsers/section_taxonomy.py` do not know them. Adding words fixes this without touching code.
- **Project titles are ambiguous without a heading.** `Online Quiz Portal - developed with React...` looks like a job line (verb + tools). With no heading, only neighbours can help.
- **Small test set.** About 190 lines in 20 resumes. Treat the percentages as a guide, not a guarantee; add more labeled resumes (real, anonymised) before trusting them.
- **Not covered yet:** two-column PDFs whose columns interleave line by line, headings embedded inside images, and non-English resumes.

## 7. How the labeled samples were made

- `real` resumes: the Day 5 extractor output, labeled by hand using line ranges (`tests/labeled_sample_builder.py`).
- `dev` / `holdout`: short hand-written resumes covering caps, numbered, inline, typo, combined, table, two-column and no-heading layouts.
- Convention: a heading line belongs to its own section; a combined heading such as `Skills & Certifications` is labeled with the first section named.
- One answer-key typo (two certification lines labeled *skills* in `hold_combined_heading`) was corrected after the first holdout run; no classifier change was made for it.
- Regenerate this report: `python run_section_eval.py`
