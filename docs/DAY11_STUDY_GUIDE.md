# Day 11: Education & Certification Parsing, Academic Profile, Relevance: Study Guide

## 1. What problem are we solving?

A resume says things like:

```
Education
B.Tech Electronics, Amity University, 2022
Higher Secondary (HSC), Delhi Public School, 2018
Certifications
AWS Certified Cloud Practitioner, 2024
Python for Everybody - Coursera
```

Day 11 turns that into data a program can reason about, then answers: **"How well does this education and these certifications fit THIS job?"**

| Day 11 deliverable | Where it lives | State |
|---|---|---|
| Education & certification extraction module | `parsers/education_parser.py` | done earlier (a few small fixes today, see section 6) |
| Structured academic profile | `parsers/academic_profile.py` -> `build_academic_profile()` | **new** |
| Education relevance logic | `parsers/education_relevance.py` -> `score_education()` and friends | **new** |

## 2. Where Day 11 fits in the pipeline

```
resume.pdf
  -> Day 5  extraction/extractor.py          PDF -> clean text
  -> Day 8  parsers/section_classifier.py    text -> sections
  -> Day 11 parsers/education_parser.py      education text -> entries, certifications (rich result)
  -> Day 11 parsers/academic_profile.py      rich result -> ONE academic profile (+ schema lists)   <- NEW
  -> Day 11 parsers/education_relevance.py   profile + job -> score with reasons                     <- NEW
        ^
        |  Day 6 jd_parser.build_ai_profile(): education_min_level, preferred_fields, role, skills
  -> Day 13 ats_engine/scoring_engine.py     calls score_education() (it has no copy of the logic any more)
```

Same pattern as Day 10: a **rich internal result** (categories, counts, reasons) plus a `to_schema_*` converter,
because `resume_schema.json` uses `additionalProperties: false` and would reject the extra fields.

## 3. Read the code in this order

### Step 1: `parsers/academic_profile.py` (the profile, about 130 lines)

1. `find_highest_degree(entries)`: the highest **finished** degree. If nothing is finished, the highest one in
   progress. A finished bachelor's beats a master's still in progress, because the candidate really holds it.
2. `find_primary_field(entries, highest)`: the main subject. It comes from the highest degree; if that names no
   field, from the next degree-level entry; only then from a school entry (weakest evidence).
3. `certification_summary(certs)`: which categories the certifications cover and how many per category.
4. `build_academic_profile(result)`: puts everything in one dict:
   `education`, `highest_level`, `highest_completed_level`, `highest_degree`, `primary_field`,
   `primary_field_category`, `latest_graduation_year`, `in_progress_degrees`, `certifications`,
   `certification_categories`, `counts`, `warnings`, plus `schema_education` / `schema_certifications`
   made by the existing `to_schema_*` functions.
5. `profile_from_file(path)`: PDF/DOCX in, profile out.

Two "highest" fields on purpose: `highest_level` is the parser's value (may be a degree still in progress);
`highest_completed_level` counts only finished degrees.

### Step 2: `parsers/education_relevance.py` (the scoring, read top to bottom)

**Settings.** `DEFAULT_CONFIG` copies the `"education"` section of `ats_engine/ats_weights.json`. The engine always
passes the real file (so the JSON wins) and a test checks the two never drift apart.

**Education score** (`score_education`), 0 to 100:

```
score = 100 * (0.6 * level_fit + 0.4 * field_fit) / (sum of the weights that could be used)
```

| Part | Small function | Credit |
|---|---|---|
| Level | `level_fit()` | equal or higher = 1.0, still in progress = 0.8, one level below = 0.5, two or more below = 0.2 |
| Field | `field_fit()` + `field_relation()` | same field 1.0, same category 0.7, **related category 0.5**, unrelated 0.3; a degree in progress counts 80% of that |

Details worth knowing:
* `required_level()`: "any degree" means a bachelor's in any field.
* `field_targets()`: uses the job's `preferred_fields`. If there are none and the job is technical, the default
  fields (Computer Science, Information Technology) are used. If there are none and the job is not technical
  ("any degree"), the field part is **not scored**: only the level counts.
* Only degree-level entries (diploma and above) decide the field. A school "Science" stream does not.
* Statuses are the same as Day 13: `missing_job`, `missing_candidate`, `scored`.

**Certification score** (`score_certifications`):
* `job_cert_view(job)` works out what the job wants: the role's own certification areas (`ROLE_CERT_CATEGORIES`,
  e.g. DevOps -> devops, cloud) and the areas its skills belong to.
* `rate_certification(cert, view)` gives **high / medium / low**:
  high = names a must-have skill, or is in the role's own area; medium = names a good-to-have skill, or is in
  an area the job's skills belong to; low = no link. Points: 1.0 / 0.6 / 0.15, then x0.7 if foundational or a
  course, x0.5 if expired.
* Overall = `100 * min(1, best_points + 0.25 * points_of_all_the_others)`: one strong certification is enough,
  more of them add only a little.

**Combined** (`score_education_with_certifications`):

```
combined = min(100, education_score + 10 * certification_score / 100)
```
* the bonus is at most 10 points; it is halved when the required degree level is not met;
* with no education at all, certifications give at most the bonus (they never replace a degree);
* if the job states no education requirement, there is nothing to add a bonus to (`missing_job`).

### Step 3: `ats_engine/scoring_engine.py`

`_education()` shrank from about 50 lines to 6: it calls `score_education()` and wraps the answer in the same
part format as before. One source of truth. The report format is unchanged.

### Step 4: `run_education_demo.py` and `tests/test_education.py`

The demo parses every resume in `data/raw_resumes`, writes the files in `data/education/`, validates the schema
lists and prints a summary. The tests use a fixed `TODAY` like Day 10 and real lines from `data/labeled_resumes`.

## 4. Worked example: one candidate, one job

**Candidate** (the resume at the top of this guide, `today` = 2026-06-15):

| Profile field | Value |
|---|---|
| highest_degree | B.Tech, Electronics, Amity University, 2022 (bachelor) |
| primary_field | Electronics, category `engineering` |
| latest_graduation_year | 2022 |
| certifications | AWS Certified Cloud Practitioner (cloud, foundational); Python for Everybody (course, Coursera) |

**Job**: `data/parsed_jobs/jd_mern_developer.profile.json`: bachelor required, preferred fields Computer Science /
Information Technology, good-to-have skills include `aws`.

Education:
* Level: bachelor vs bachelor -> met -> **1.0** ("Highest degree (bachelor) meets the required level (bachelor).")
* Field: Electronics is not Computer Science, but the categories `engineering` and `computer_it` are
  related -> **0.5** ("Field 'Electronics' is a related area to 'Computer Science'.")
* `100 * (0.6 * 1.0 + 0.4 * 0.5) / (0.6 + 0.4)` = **80.0**

Certifications:
* *Python for Everybody*: category `software_development` is the role's own area -> high (1.0), a course -> x0.7
  = **0.70**
* *AWS Cloud Practitioner*: names the good-to-have skill `aws` -> medium (0.6), foundational -> x0.7 = **0.42**
* overall = `100 * min(1, 0.70 + 0.25 * 0.42)` = **80.5**

Combined:
* bonus = `10 * 80.5 / 100` = **8.1** (the degree level is met, so it is not halved)
* `88.1 = 80.0 (education) + 8.1 (certification bonus, max 10)`

(Numbers are rounded to one decimal in the output.)

## 5. How to run it

```
python run_education_demo.py
python -m parsers.academic_profile data/raw_resumes/Maya.pdf
python -m unittest tests.test_education -v
python -m unittest discover -s tests -t .
```

## 6. What changed in the finished parser (small fixes found by reading the real outputs)

| Problem found | Fix |
|---|---|
| `Bachelor of Business Administration (BBA) in Operations Management Graduated May 2020` lost the field | brackets that only repeat the degree name are skipped; "Graduated" ends the field |
| `B.Eng.` and `B.F.A.` were not recognised as degrees | added B.Eng / M.Eng and B.F.A. / M.F.A. |
| Institutions such as `VIT Vellore`, `JNTU Hyderabad` were missing | added JNTU, VIT, BITS, SRM |
| `Oracle Certified Associate Java SE 8` was renamed to the Professional certification | the catalog pattern now requires "professional" / OCP |
| `Certifications: A, B` on ONE line gave one certification | split on commas only when every piece looks like a certification |
| `Certifications: ...` under a mixed heading (`CERTIFICATIONS & SKILLS`) was lost by the segmenter | fallback that reads labelled lines |
| `Education: B.E. IT, VIT, 2020` written inline was not found | same kind of fallback |
| `HubSpot Marketing Software Certified` was tagged `software_development` | the keyword is now "software development / engineer", not bare "software" |

## 7. Limits and doubtful results (be honest about them)

* Institutions with no word like University/College/Institute and not in the small list (JNTU, VIT, BITS, SRM) are
  still missed; those degrees are left out of `schema_education` (the schema needs an institution).
* `B.S.` is normalized to `B.Sc` (the project convention); a US "B.S. in Computer Science" is not wrong, but the label differs.
* Certification lines placed before their heading, or ones without the word "certified" under a mixed heading,
  can still be lost by the Day 8 segmenter (example: `ACCA Qualification, 2017` in one labeled sample).
* A missing field of study is **not penalised** (the field part is skipped, so the score is the level alone). This
  matches Day 13's old behaviour but can make "unknown" look as good as a "match".
* A technical job that says "any degree" cannot be told apart from one that names no field, so it uses the default
  CS/IT fields.
* The engine uses `score_education()` only. The certification bonus (`score_education_with_certifications`) is
  ready but **not** wired into the Day 13 score yet, to keep Day 13 behaviour and weights unchanged.
* Category lists (`ROLE_CERT_CATEGORIES`, `RELATED_CATEGORIES`) are small hand-made tables; extend them as new roles appear.
* Scanned resumes (`img.pdf`, `sample_scanned.pdf`) have no text, so they give no education (OCR is not part of Day 11).
