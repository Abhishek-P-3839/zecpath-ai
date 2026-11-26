# Day 9 - Skill Extraction Engine

**Goal:** read a resume and produce a clean list of the candidate's skills (technical, business, creative and soft), each with a **confidence score** that says how sure we are.

This guide is written for a beginner. Read it top to bottom once, then open the code and follow along.

---

## 1. The problem in plain words

A recruiter reads "Pyhton, ReactJS, MERN, AWS (EC2, S3)" and understands it instantly. A computer sees only characters. It must learn that:

- `ReactJS`, `React.js` and `React` are **the same skill** (synonyms),
- `Pyhton` is a **typo** of `Python` (spelling variation),
- `MERN` means **MongoDB + Express + React + Node.js** (a stack),
- `Go` the language is different from "go to market" (ambiguity),
- "No experience with Java" does **not** mean the candidate knows Java (negation),
- a skill listed once is less certain than one the candidate used in three jobs (confidence).

The engine solves each of these with a small, simple, explainable rule. There is **no black box**: for every skill it can tell you why it got its score.

---

## 2. The big picture

```
resume text
   |
   |  1. SEGMENT        (Day 8)  tag every line: skills / experience / education ...
   v
lines with sections
   |
   |  2. MAKE UNITS              glue wrapped lines back into one bullet
   v
units  (one bullet / one line each)
   |
   |  3. FIND MENTIONS           entity recognition: spot skill words
   |       exact + synonyms        ReactJS -> react
   |       known misspellings      Pyhton  -> python
   |       fuzzy matching          Postgresq1 -> postgresql
   |       risky words             Go, R, Excel, Spring   (need proof)
   |       stacks                  MERN -> 4 skills
   v
mentions  (python x3, react x2, ...)
   |
   |  4. MERGE                   deduplicate: one record per skill
   v
one record per skill
   |
   |  5. SCORE                   confidence (parsers/skill_confidence.py)
   v
   |  6. OUTPUT                  sorted list + stacks + summary + warnings
   v
structured skill output (JSON)
```

---

## 3. Words you need to know

| Word | Meaning here | Example |
|---|---|---|
| **Entity** | A "thing" we want to find in text | the skill `python` |
| **Entity recognition (NER)** | Finding entities in text automatically | spotting `Python` in a sentence |
| **Gazetteer / dictionary** | A list of known entities | `skill_taxonomy.py` |
| **Canonical name** | The one official spelling we store | `node.js` |
| **Alias / synonym** | Another way to write the same thing | `nodejs`, `node js`, `node` |
| **Normalize** | Convert any spelling to the canonical name | `ReactJS` -> `react` |
| **Deduplicate** | Keep one record even if mentioned many times | `Python` x3 -> one `python` |
| **Regex** | A pattern that finds text | `\bpython\b` |
| **Fuzzy matching** | Matching words that are *almost* equal | `Postgresq1` ~ `postgresql` |
| **Confidence** | A number 0-1: how sure are we | `0.88` |
| **Mention** | One place where a skill appears | the word `AWS` in one bullet |

> **Honest note about "NLP-based":** the recognizer is **dictionary + rules + context (NLP-style)**, the same family as spaCy's `PhraseMatcher` / `EntityRuler`. It is not a trained machine-learning model. That is a good choice here: it is fast, needs no new libraries, is fully explainable and easy to fix. Section 12 explains how a spaCy model could be added later.

---

## 4. Files added on Day 9

| File | What it does |
|---|---|
| `parsers/skill_taxonomy.py` | **Master skill dictionary**: ~220 skills (technical, business, creative, soft), synonyms, misspellings, risky words, stacks |
| `parsers/skill_extractor.py` | **The engine**: finds, merges and outputs skills |
| `parsers/skill_confidence.py` | **Confidence scoring logic** (only arithmetic, easy to read) |
| `run_skill_demo.py` | Runs the engine on every resume in `data/raw_resumes/` |
| `tests/test_skill_extractor.py` | 52 automated tests |
| `data/samples/sample_skills_output.json` | Example of the structured output (dummy resume) |
| `docs/Day9_Skill_Extraction_Engine.md` | This guide |

Reused from earlier days: Day 5 extractor (PDF/DOCX -> text), Day 6 skill dictionary and helpers (`detect_proficiency`, `find_years`), Day 8 section classifier.

---

## 5. Step-by-step: what the code does

### Step 1 - The master skill dictionary (`skill_taxonomy.py`)

It is just Python data. One entry looks like this:

```python
"react": ("framework", ["react", "reactjs", "react.js", "react js"]),
#   ^canonical   ^category          ^all the ways people write it
```

- It **starts from the Day 6 dictionary** (`jd_taxonomy.py`), so resumes and job descriptions always use the same canonical names. That makes matching a resume to a job easy later.
- We add more skills in the same format: business (`salesforce`, `budgeting`), creative (`adobe illustrator`, `copywriting`), soft (`leadership`), and more tech.
- `category` must be one of the nine values allowed by `resume_schema.json`.
- `domain_of(skill)` turns a skill into `technical`, `business`, `creative` or `soft`. (`excel` is a *tool* but belongs to the *business* domain; that is what `DOMAIN_OVERRIDES` is for.)

Other tables in the same file:

| Table | Purpose |
|---|---|
| `MISSPELLINGS` | `"python": ["pyhton", "phyton"]` |
| `AMBIGUOUS` | words like `Go`, `R`, `Excel`, `Spring` that need proof |
| `CONTEXT_EXCLUSIONS` | `(SQL)` after "sales qualified lead" is not the database language |
| `STACKS` | `"MERN": mongodb + express + react + node.js` |

### Step 2 - Segment the resume (Day 8)

`segment_resume(text)` tags each line with its section. Why do we care? **Where** a skill appears is evidence: a skill used in the *Experience* section is stronger evidence than one in a *Summary* sentence.

### Step 3 - Make "units" (`_make_units`)

PDFs wrap long lines:

```
- Architected a microservices billing pipeline using Python and FastAPI, reducing transaction processing
time by 35%.
```

`_make_units` glues the second line back to the bullet, so one bullet is judged as one sentence. It also joins skills lists broken across lines (`Stakeholder` / `Communication`), and blanks out e-mails, links and phone numbers (so `rahul.python.dev@gmail.com` can never create a "Python" skill).

### Step 4 - Find mentions = entity recognition (`_find_*_mentions`)

**4a. Exact names and synonyms.** All aliases are joined into **one big regex**, longest first:

```
react native | react.js | reactjs | react | ...
```

*Longest first* matters: in "React Native" we want `react native`, not `react`. Boundary checks stop `java` from matching inside `javascript`.

**4b. Known misspellings.** Looked up in the same index, flagged `misspelling`.

**4c. Fuzzy matching** for typos we have never listed. Python's `difflib` gives a similarity score between 0 and 1; we need **>= 0.86**. It is deliberately careful:

- only inside a **skills list** (never in normal sentences),
- only words of **6+ letters** (`panda` must not become `pandas`),
- first letter must match, length can differ by at most 2,
- every fuzzy skill is marked `needs_review`.

**4d. Risky short words** (`Go`, `R`, `C`, `Excel`, `Spring`, `Express`...). They are accepted only with **proof**:

1. a cue word in the same bullet (`R programming`, `Excel ... pivot`), **or**
2. exact capitalization in a skills list (`Skills: Python, Go, R`), **or**
3. exact capitalization in the middle of a sentence right beside a sure skill (`dashboards in Excel and Tableau`).

So `help the team excel` and `Go to market` are correctly ignored. Accepted risky words also lose 0.05 confidence.

**4e. Negation and learning.** Before accepting a mention, the engine looks at the words just before it:

- `No experience with Java`, `Did not use Angular`, `Not familiar with Kafka` -> **ignored**,
- `Currently learning Kubernetes` -> kept, but the score drops by 0.20.

**4f. Stacks.** `MERN`, `MEAN`, `MEVN`, `PERN`, `LAMP`, `LEMP`.

- Found `MERN stack` -> output the stack **and** its four component skills with `match_type: "stack"`, `source: "inferred"` and **low** confidence (the resume never wrote them out).
- `MEAN` and `LAMP` only count when written in capitals, because `mean` is a normal English word.
- Reverse direction: if a resume lists MongoDB, Express, React and Node.js but never says "MERN", the engine reports `MERN` with `inferred_from_components: true`. This helps when a job description asks for "MERN".
- If a component is also written explicitly (`MERN stack, React`), the explicit mention wins.

**4g. Level and years.** `Python (3 years)` -> `years_used: 3`. `Tableau (advanced)` -> `proficiency: "advanced"`. Words like "strong" or "hands-on" in a sentence with one skill are also used (reusing Day 6 code).

### Step 5 - Merge = deduplicate and normalize (`_merge`, `_build_skill`)

All mentions are collected in a dictionary **keyed by canonical name**, so the same skill can never appear twice:

```
Pyhton, Python, python     ->  one record: normalized_name "python"
ReactJS, React.js, React   ->  one record: normalized_name "react"
```

The record keeps `name` (first spelling as written), `aliases_found` (all spellings), `sections` (where), and `mentions` (how many bullets).

### Step 6 - Confidence scoring (`skill_confidence.py`)

The score is **added up from clues**. Every clue also writes a reason, saved in the output.

| Clue | Points |
|---|---|
| Match quality: exact / synonym / misspelling / fuzzy / stack | +0.50 / +0.45 / +0.40 / +0.30 / +0.30 |
| Best section: skills / experience, certifications / projects / summary / others | +0.25 / +0.20 / +0.15 / +0.10 / +0.05 |
| Also found in another section | +0.10 each, max +0.15 |
| Mentioned in more bullets | +0.03 each, max +0.06 |
| Used in a work sentence ("Built ... using Python") in experience/projects | +0.10 |
| Years or level given | +0.05 |
| Only "learning / interested in" wording | -0.20 |
| Risky short word (`Go`, `R`) | -0.05 |

The result is limited to **0.05 - 0.99** (a text parser is never 100% sure) and labelled:

| Label | Score | Meaning |
|---|---|---|
| **high** | >= 0.85 | listed **and** used in real work |
| **medium** | 0.65 - 0.84 | clearly claimed (usually just listed) |
| **low** | < 0.65 | guessed, implied, or weak: review it |

**Worked example** (real output of the engine):

```
Skills
Languages: Pyhton, ReactJS, Go, Postgresq1
Stack: MERN
Experience
- Built an API using Python (3 years) and deployed it on AWS.
```

| Skill | Calculation | Score | Label |
|---|---|---|---|
| `python` | exact 0.50 + skills 0.25 + other section 0.10 + 2 mentions 0.03 + work sentence 0.10 + years 0.05 = 1.03 -> capped | **0.99** | high |
| `aws` | exact 0.50 + experience 0.20 + work sentence 0.10 | **0.80** | medium |
| `react` | synonym 0.45 + skills 0.25 | **0.70** | medium |
| `go` | exact 0.50 + skills 0.25 - risky word 0.05 | **0.70** | medium |
| `postgresql` | fuzzy 0.30 + skills 0.25 (typo guessed) | **0.55** | low, needs review |
| `mongodb` (from MERN) | 0.30 + half of the skills bonus | **0.42** | low, inferred |

Notice that **a skill only listed** (0.75) cannot reach "high". It must be backed up by real work. That is how the engine separates "keyword stuffing" from real experience.

### Step 7 - Structured output

```json
{
  "schema_version": "1.0",
  "skills": [ { ...one record per skill... } ],
  "stacks":  [ { "name": "MERN", "found_as": "MERN stack", "components": [...], "confidence": 0.8,
                 "inferred_from_components": false } ],
  "summary": { "total": 18, "by_domain": {...}, "by_category": {...},
               "by_confidence": {"high": 10, "medium": 7, "low": 1}, "needs_review": 1 },
  "warnings": [ "1 skill(s) need review (low confidence or spelling guessed)." ]
}
```

One skill record:

| Field | Meaning |
|---|---|
| `name` | spelling as written in the resume |
| `normalized_name` | canonical name (use this for matching) |
| `category` | one of the 9 schema categories |
| `domain` | technical / business / creative / soft |
| `proficiency`, `years_used` | beginner...expert, years, or `null` |
| `source` | `skills_section`, `experience`, `project`, `certification` or `inferred` |
| `confidence`, `confidence_label` | the score and its label |
| `match_type` | how it was found: exact, synonym, misspelling, fuzzy, stack |
| `mentions`, `sections` | how many bullets / which sections |
| `aliases_found` | every spelling seen |
| `evidence` | up to 2 short snippets (not logged anywhere) |
| `reasons` | the confidence calculation in words |
| `needs_review` | `true` for low confidence or a guessed spelling |

`to_schema_skills(result)` returns only the fields that `data/schemas/resume_schema.json` allows (`name`, `normalized_name`, `category`, `proficiency`, `years_used`, `source`, `confidence`), so it drops straight into a candidate profile. `source` values come from the schema, so a skill found only in the summary or education is reported as `inferred`.

---

## 6. How to run it

```bash
# one resume (table)
python -m parsers.skill_extractor data/raw_resumes/Maya.pdf

# one resume (full JSON)
python -m parsers.skill_extractor data/raw_resumes/Maya.pdf --json

# every resume in data/raw_resumes  ->  data/skills/*.json
python run_skill_demo.py

# tests
python -m unittest tests.test_skill_extractor -v
```

From Python:

```python
from parsers.skill_extractor import extract_skills, extract_skills_from_file, to_schema_skills

result = extract_skills_from_file("data/raw_resumes/Maya.pdf")   # PDF, DOCX or TXT
result = extract_skills(resume_text)                             # plain text

for skill in result["skills"]:
    print(skill["normalized_name"], skill["confidence"], skill["confidence_label"])

profile_skills = to_schema_skills(result, min_confidence=0.65)   # medium and high only
```

---

## 7. How to teach it something new (no code changes)

Open `parsers/skill_taxonomy.py`:

| I want to... | Do this |
|---|---|
| add a skill | add one line to `_NEW_SKILLS`: `"figma": ("design", ["figma"])` |
| add a synonym | add it to the alias list, e.g. `"typescript": (..., ["typescript", "ts"])` |
| add a misspelling | `MISSPELLINGS["python"].append("pythoon")` |
| stop a word being a false positive | add it to `AMBIGUOUS` (with cue words) or to `CONTEXT_EXCLUSIONS` |
| add a stack | add it to `STACKS` with its component skills |
| change a score | edit the constants at the top of `skill_confidence.py` |

After editing, run the tests: they check that every category is valid, no alias points to two skills, and every stack component exists.

---

## 8. Known limits (be honest about these in a review)

1. **Dictionary-based.** A skill that is not in the dictionary is not found (except fuzzy typos of known ones). Fix: grow the dictionary.
2. **Fuzzy matching is single-word.** `Machine learing` works only because it is in `MISSPELLINGS`.
3. **Negation is simple.** It catches "no experience with X", "did not use X", "not familiar with X", not every possible phrasing.
4. **Scanned PDFs** have no text (OCR is still not implemented), so they return no skills and a warning.
5. **English only.**
6. **Years of experience** per skill are only found when written next to or in the same sentence as one skill.

**Possible upgrade:** load a spaCy model (e.g. `en_core_web_sm`) and use `EntityRuler` with the same dictionary, or train a small NER model on labelled resumes. The dictionary and the scoring code can stay as they are.

---

## 9. Self-check questions

1. Why is the longest alias matched first?
2. Why can `python` get a score above 1.0 before the cap, and why do we still cap at 0.99?
3. Why does `Go` need proof but `Python` does not?
4. A resume says "MERN stack". Which skills are output, with what `source` and what confidence label?
5. Why is the fuzzy step limited to skills lists?
6. Which part of the code removes duplicates? What is the "key"?
7. Why is a skill that is only listed in the Skills section never rated "high"?

**Answers:** (1) so `react native` beats `react`; (2) clues are added, and a parser should never claim certainty; (3) `go` and `r` are also normal words/letters; (4) mongodb, express, react, node.js, `source: "inferred"`, low; (5) in sentences, normal words that look like skills would create false skills; (6) `_merge`, keyed by canonical name; (7) it lacks the "used in real work" and "found in another section" evidence.

## 10. Exercises

1. **Easy:** add `"figma"`'s typo `"figam"` to `MISSPELLINGS`, then run a resume containing it.
2. **Easy:** change `HIGH` to `0.80` in `skill_confidence.py`. Which tests fail, and why?
3. **Medium:** add the stack `JAMSTACK` (`javascript`, `rest api`, `html`) and write a test.
4. **Medium:** add the negation phrase "limited exposure to" and a test.
5. **Hard:** make the extractor also report the *job title*'s skills (e.g. "Python Developer" implies `python`) with `source: "inferred"`.
