# Day 10: Experience Parsing & Relevance Engine: Study Guide

## 1. What problem are we solving?

A resume says things like:

```
Software Engineer II - Bluebonnet Cloud Systems, Austin, TX   March 2023 - Present
- Architected a microservices billing pipeline using Python and FastAPI...
Junior Web Developer - Lone Star Digital Agency, Austin, TX   June 2021 - February 2023
```

A computer sees only text. Day 10 turns that text into **data a program can reason about**, then answers:

1. **Parse**: Who did this person work for, as what, and for how long?
2. **Summarise**: How many years in total? Any gaps? Any overlapping jobs?
3. **Score**: How useful is that experience for *this particular job*?

| Task from the brief | Where it lives |
|---|---|
| Extract company names, job titles, durations | `parsers/experience_parser.py` -> `parse_experience()` |
| Calculate total experience | `compute_total_months()` |
| Detect gaps and overlapping roles | `find_gaps()`, `find_overlaps()` |
| Analyse relevance of roles to job requirements | `parsers/experience_relevance.py` -> `score_experience()` |
| Build role-to-role similarity logic | `role_similarity()` |
| **Deliverable:** Experience parser | `experience_parser.py` |
| **Deliverable:** Relevance scoring module | `experience_relevance.py` |
| **Deliverable:** Structured experience object | the dict returned by `parse_experience()` (+ `to_schema_experience()`) |

## 2. Where Day 10 fits in the pipeline you already built

```
resume.pdf
  -> Day 5  extraction/extractor.py        PDF -> clean text
  -> Day 8  parsers/section_classifier.py  text -> {header, skills, experience, education...}
  -> Day 10 parsers/experience_parser.py   experience text -> structured jobs      <- NEW
  -> Day 10 parsers/experience_relevance   jobs + job description -> score         <- NEW
        ^
        |  Day 6  jd_parser.build_ai_profile()  (the job's must-have skills, min_years, title)
        |  Day 9  skill dictionary             (so skill names match: "ReactJS" -> "react")
```

Day 10 reuses your earlier work instead of repeating it. That is good engineering.

## 3. The parser, step by step

### Step 1: Turn dates into numbers
Computers can't subtract "March 2023" from "June 2021", but they can subtract numbers. So every month becomes one number:

```python
month_index(2021, 6)  # 2021*12 + 5 = 24257
month_index(2023, 3)  # 24277   ->  24277 - 24257 = 20 months apart
```

`parse_date()` understands `Jan 2020`, `January, 2020`, `03/2020`, `2020` and `Present/Current/Till date`.
`parse_date_range()` finds `Jan 2020 - Mar 2021` (also with an en-dash, or `to`) using a regular expression (`DATE_RANGE_RE`).

**Design choices worth remembering**
- *Inclusive counting*: Jan 2020 -> Jan 2020 is **1** month of work, so `duration = end - start + 1`.
- *"Present"* becomes today's month. Tests pass a fixed `today` so results never change from day to day.
- *Year-only dates* ("2019 - 2021") are accepted but flagged "approximate".
- *Future end dates* are capped at today, and *end before start* produces a warning rather than a crash.

### Step 2: Find where each job starts
`split_into_entries()` uses one simple rule: **a job begins on a line that contains a date range.** Everything after it (until the next such line) belongs to that job. If the dates sit on their own line (table-style resumes), the 1-2 lines above are used as the header. If there are no dates at all (like `Intern at Demo Corp`), it still returns one undated job so nothing is silently lost.

### Step 3: Split the header into title, company, location
`split_header("Software Engineer II - Bluebonnet Cloud, Austin, TX")` returns `("Software Engineer II", "Bluebonnet Cloud", "Austin, TX")`.

It tries the separators ` | `, ` @ `, ` at `, ` - `, then a comma. Then comes the clever part, **deciding which side is the title**, because resumes write it both ways ("Google - Software Engineer" vs "Software Engineer - Google"). We check which side contains a title word (`engineer`, `manager`, `analyst`...). It also keeps `Acme, Inc.` together instead of treating `Inc.` as a city.

### Step 4: Build one structured entry
`_build_entry()` fills the fields your `resume_schema.json` expects: `company`, `designation`, `start_date` (`YYYY-MM`), `end_date`, `is_current`, `duration_months`, `responsibilities` (the bullets), `achievements` (bullets with numbers such as `reduced cost by 18%`), and `skills_used` (found with your Day 9 skill dictionary). It adds a `confidence` value and `notes` so weak parses are visible.

### Step 5: Total experience, without double counting
If someone had two jobs at the same time, adding durations would overstate their experience. `merge_periods()` merges overlapping date ranges first:

```
Job A:  |==========|            Jan 2020 - Dec 2020  (12 months)
Job B:        |==========|      Jul 2020 - Jun 2021  (12 months)
Merged: |================|      Jan 2020 - Jun 2021  (18 months, not 24)
```

### Step 6: Gaps and overlaps
**Gaps** (`find_gaps`): the number of *empty* months between one job ending and the next starting. Under 3 months is ignored (notice periods and holidays are normal). 3-5 months is `minor`, 6+ is `major`. If the person isn't currently employed, we also report the gap *since the last job*.

**Overlaps** (`find_overlaps`) are classified so we don't blame honest people:
| Kind | Meaning |
|---|---|
| `handover` | 1 month overlap: joining the new job before leaving the old one is normal |
| `concurrent` | one job is an internship, part-time, freelance or contract: legitimate |
| `review` | 2+ months of two full-time jobs: a recruiter should take a look |

## 4. The structured experience object (deliverable 3)

For `Maya.pdf` the parser returns (trimmed):

```json
{
  "entries": [
    {
      "company": "Lone Star Digital Agency",
      "designation": "Junior Web Developer",
      "location": "Austin, TX",
      "start_date": "2021-06",
      "end_date": "2023-02",
      "is_current": false,
      "duration_months": 21,
      "skills_used": ["javascript", "html", "css", "node.js", "docker"],
      "confidence": 1.0
    }
  ],
  "total_experience_months": 66,
  "total_experience_years": 5.5,
  "current_designation": "Software Engineer II",
  "is_currently_employed": true,
  "gaps": [],
  "overlaps": [],
  "warnings": []
}
```

`to_schema_experience(result)` returns just the job list in exactly the shape `resume_schema.json` allows (that schema has `additionalProperties: false`, so extra fields like `confidence` must be removed). The demo validates this for every resume.

## 5. The relevance engine, step by step

### Step 1: Role-to-role similarity: `role_similarity(a, b)` -> 0.0 to 1.0
Is "Python Developer" similar to "Software Engineer"? We check three things and keep the best:

1. **Same canonical role** (reusing your Day 6 `normalize_role`): "MERN Stack Developer" = "Full Stack Engineer" -> **1.0**
2. **Listed as close** in the `CLOSE_ROLES` table: Software Engineer <-> Full Stack Developer = 0.85
3. **Same family** (software, data, hr, sales...): 0.6
4. Otherwise **word overlap**, where shared domain words (`software`) count fully but generic words (`engineer`) only 0.4. That is why "Mechanical Engineer" vs "Software Engineer" scores 0.17 and not 0.5.

```
                      Full Stack Dev   Software Eng   Python Dev   Data Analyst   HR Exec
Full Stack Developer      1.0             0.85           0.6          0.0           0.0
Data Analyst              0.0             0.0            0.0          1.0           0.0
```

To teach it a new role, add it to `ROLE_FAMILY` or `CLOSE_ROLES`. No logic changes needed.

### Step 2: Score one past job against the target job (0-1)
```
relevance = 0.5 * title_similarity + 0.5 * skill_score
skill_score = 0.75 * (must-have skills used / must-have skills) + 0.25 * (good-to-have used / good-to-have)
```
Soft skills like "communication" are excluded, because bullets rarely contain that word and it would unfairly punish people.

### Step 3: Combine the whole career into one score (0-100)
For every calendar month we keep the **most relevant** job covering it (so overlaps are never double counted), then weight each month by recency. Work that ended 5 years ago counts half (`RECENCY_HALF_LIFE_YEARS = 5`).

```
score = 100 * ( 0.5 * years_fit + 0.3 * best_relevance + 0.2 * recent_relevance )
years_fit = min(1, recency-weighted relevant years / years the job requires)
```

Worked example: Maya vs the MERN Developer job (needs 3+ years):

| Job | title sim | skill score | relevance | recency weight |
|---|---|---|---|---|
| Software Engineer II (current) | 0.85 | 0.16 | 0.51 | 1.0 |
| Junior Web Developer (ended 2023) | 0.60 | 0.31 | 0.45 | 0.6 |

Relevant years = 2.7, recency-weighted = 1.9, so `years_fit = 1.9 / 3 = 0.63`.
`score = 100 * (0.5*0.63 + 0.3*0.51 + 0.2*0.51) = 57` -> label **good**.
Notes tell the recruiter: *"Must-have skills not seen in experience: rest api, express, redux, mongodb, git."*

Labels: 75+ strong, 50+ good, 25+ partial, below 25 weak.

## 6. How to run and test it

```bash
python run_experience_demo.py                # parses every resume, scores against every job, saves data/experience/
python -m unittest tests.test_experience -v  # 38 new tests
python -m unittest discover -s tests -t .    # the whole project (199 tests)
python -m parsers.experience_parser data/raw_resumes/Maya.pdf   # one resume, full JSON
```

Using it in your own code:

```python
import json
from parsers.experience_parser import parse_experience_from_file
from parsers.experience_relevance import score_experience

experience = parse_experience_from_file("data/raw_resumes/Maya.pdf")
job = json.load(open("data/parsed_jobs/jd_mern_developer.profile.json"))
report = score_experience(experience, job)
print(report["score"], report["label"], report["notes"])
```

## 7. Known limits (good to mention in interviews or reviews)

- **Scanned/image resumes** have no text, so nothing is parsed (the Day 5 OCR flag already warns about it).
- **Unusual layouts** (e.g. a job whose dates are missing) still produce an entry, but with low `confidence` and a warning, and it is excluded from total years.
- **Skills come from the job's own bullets only.** A skill listed just in the Skills section does not prove it was used in that job. This is deliberate: it rewards evidence.
- **Role similarity is rule-based**: transparent and easy to explain, but it only knows the roles in your tables. A future upgrade could use embeddings (Day 11+).
- **Weights are judgement calls.** They sit at the top of `experience_relevance.py` so they can be tuned against real hiring outcomes.

## 8. Self-check questions

1. Why do we use `end - start + 1` for a job's duration?
2. Two jobs: Jan-Dec 2020 and Jul 2020-Jun 2021. What is the total experience, and why is it not 24 months?
3. What is the difference between a `handover`, `concurrent` and `review` overlap?
4. Why do shared words like "engineer" count only 0.4 in title similarity?
5. Why is work from 10 years ago given less weight?
6. Why does `to_schema_experience()` remove fields such as `confidence`?
7. Try it: add `"scrum master"` as a new role family and check `role_similarity` with a test.

*Answers: (1) a job running Jan to Jan is still one month of work; (2) 18 months, because the overlapping months are counted once; (3) see section 3, step 6; (4) otherwise any two "engineers" would look related; (5) old skills go stale and recent work is a better predictor; (6) the schema forbids extra properties.*
