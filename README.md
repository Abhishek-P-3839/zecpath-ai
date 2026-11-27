# Zecpath AI System

AI modules for the Zecpath hiring platform: resume parsing, ATS scoring, screening, interview support and final scoring.
This is the Day 3 setup, so most modules are simple starters that will grow later.

## Project layout

```
zecpath-ai/
├── data/            sample input files (no real candidate data)
├── parsers/         read resumes and pull out email, skills, experience
├── ats_engine/      ATS score (resume vs job requirements)
├── screening_ai/    screening questions and report
├── interview_ai/    HR and technical interview questions
├── scoring/         combine all scores and give a decision
├── pipeline/        Day 7: metadata, versioned storage, lifecycle, training snapshots
├── matching/        Day 12: embeddings, semantic matching, similarity scorer, accuracy metrics
├── utils/           shared helpers (logger)
├── tests/           test files
├── logs/            log files are saved here (not pushed to GitHub)
├── docs/            CODE_STANDARDS.md
├── run_demo.py      small demo of the full flow
├── run_pipeline_demo.py  Day 7 demo: one candidate through the whole data pipeline
├── requirements.txt
└── .gitignore
```

## Setup

1. Install Python 3.10 or higher and check it: `python --version`
2. Create and activate a virtual environment:
   - Windows: `python -m venv venv` then `venv\Scripts\activate`
   - Mac / Linux: `python3 -m venv venv` then `source venv/bin/activate`
3. Install the libraries: `pip install -r requirements.txt`

## Run

- Demo: `python run_demo.py`
- Day 7 pipeline demo: `python run_pipeline_demo.py` (saves to `data/store/`)
- Tests: `python -m unittest discover -s tests -t .` (or `pytest`)

## Logging

All AI activities are logged using `utils/logger.py`. Logs show on the screen and are saved in `logs/ai_activity.log`.

```python
from utils.logger import get_logger
log = get_logger(__name__)
log.info("Resume parsed")
```

## Code standards

See [docs/CODE_STANDARDS.md](docs/CODE_STANDARDS.md).

## Push to GitHub

```
git init
git add .
git commit -m "Initial project setup"
git branch -M main
git remote add origin https://github.com/<your-username>/zecpath-ai.git
git push -u origin main
```
## Day 4 - Data schemas
- data/schemas/resume_schema.json : JSON Schema for a parsed resume (candidate profile)
- data/schemas/job_schema.json : JSON Schema for a job description
- data/samples/ : example resume and job that follow the schemas
- utils/schema_validator.py : validates a JSON file against a schema
- tests/test_schemas.py : unit tests for the schemas

Validate a file:
python -m utils.schema_validator data/samples/sample_resume.json resume
## Day 5 - Resume text extraction

Reads PDF and DOCX resumes and produces clean, consistent text for the parser (Day 6+).

**Install:** `pip install pdfplumber python-docx`

**Create dummy sample resumes:** `python -m tests.sample_builder`

**Run on one resume:** `python -m extraction.extractor data/raw_resumes/sample_simple.pdf`
**Run on a folder:** `python -m extraction.extractor data/raw_resumes`

Outputs go to `data/extracted/` as `name.txt` and `name.json`
(fields: source_file, file_type, page_count, char_count, needs_ocr, warnings, sections, clean_text).

**Run tests:** `python -m unittest discover -s tests -t . -v > logs\test_results.log 2>&1`

Modules: `pdf_reader`, `docx_reader`, `cleaner`, `normalizer`, `extractor` (in `extraction/`).
Scanned/image-only PDFs are flagged with `needs_ocr: true` (OCR is not implemented yet).

## Day 6 - Job description parsing

Converts employer job descriptions into structured, AI-readable job objects (same format as `data/schemas/job_schema.json`).

**Run the demo (parses all samples, validates, saves JSON):** `python run_jd_demo.py`
**Parse one JD:** `python -m parsers.jd_parser data/job_descriptions/jd_mern_developer.txt`
**Run tests:** `python -m unittest tests.test_jd_parser -v`

Files:
- `parsers/jd_parser.py` : the parser (normalize, split sections, extract skills / role / experience / education, build AI profile)
- `parsers/jd_taxonomy.py` : skill synonyms, role variations, education keywords (edit this to teach the parser new terms)
- `data/job_descriptions/` : sample JD text files
- `data/parsed_jobs/` : structured output (`<name>.json`) and AI profile (`<name>.profile.json`)
- `docs/JD_Parsing.md` : full documentation
- `tests/test_jd_parser.py` : unit tests


## Day 7 - AI data pipeline & storage design

Designs how AI data is stored, labelled with metadata, versioned and moved from resume upload to hiring decision.

Run the pipeline demo: `python run_pipeline_demo.py`
Run tests: `python -m unittest tests.test_pipeline -v`

Docs:

- [Pipeline diagram](docs/pipeline_diagram.png)
- [Storage structure](docs/Day7_Storage_Structure.md)
- [Metadata standards](docs/Day7_Metadata_Standards.md)
- [Lifecycle, versioning and retraining](docs/Day7_Pipeline_Lifecycle_Versioning.md)

## Day 8 - Resume section segmentation

Finds the sections of a resume (header, summary, skills, experience, education, certifications, projects, other)
and tags every line with its section, so later AI steps work on structured text.
Uses **rules** (headings) + **NLP-style content scoring** (for missing or combined headings). No new libraries needed.

Segment one resume: `python -m parsers.section_classifier data/raw_resumes/Maya.pdf`
Segment all resumes: `python run_section_demo.py` (saves to `data/segmented/`, not pushed to GitHub)
Measure accuracy + rewrite the report: `python run_section_eval.py`
Run tests: `python -m unittest tests.test_section_classifier -v`

```python
from parsers.section_classifier import segment_file
result = segment_file("data/raw_resumes/Maya.pdf")
result["sections"]["skills"]      # text of the skills section
result["line_tags"]               # every line + its section + how it was decided + confidence
```

Files:
- `parsers/section_classifier.py` : the classifier module
- `parsers/section_taxonomy.py` : headings and keyword lists (edit this to teach it new words)
- `parsers/section_eval.py` : accuracy measurement
- `data/labeled_resumes/` : 20 hand-labeled resumes (`*.labeled.txt` = answer keys) + `manifest.json`
- `tests/labeled_sample_builder.py` : builds the labeled samples
- `docs/Day8_Resume_Section_Segmentation.md` : how it works (beginner guide)
- `docs/Day8_Section_Detection_Accuracy_Report.md` : accuracy report

## Day 9 - Skill extraction engine

Finds every skill in a resume (technical, business, creative, soft) and returns a clean, de-duplicated list
with a **confidence score** per skill. Handles synonyms (`ReactJS` -> `react`), spelling variations
(`Pyhton`, `Postgresq1`), skill stacks (`MERN`, `MEAN`) and risky words (`Go`, `R`, `Excel`).
Rules + dictionary + context (NLP-style). No new libraries needed.

Extract from one resume: `python -m parsers.skill_extractor data/raw_resumes/Maya.pdf` (add `--json` for everything)
Extract from all resumes: `python run_skill_demo.py` (saves to `data/skills/`, not pushed to GitHub)
Run tests: `python -m unittest tests.test_skill_extractor -v`

```python
from parsers.skill_extractor import extract_skills_from_file, to_schema_skills
result = extract_skills_from_file("data/raw_resumes/Maya.pdf")
result["skills"]                  # one record per skill: normalized_name, category, confidence, reasons ...
result["stacks"]                  # e.g. MERN and its component skills
to_schema_skills(result)          # the `skills` list for data/schemas/resume_schema.json
```

Files:
- `parsers/skill_taxonomy.py` : master skill dictionary, synonyms, misspellings, risky words, stacks (edit this to teach it new skills)
- `parsers/skill_extractor.py` : the engine (find, normalize, deduplicate, output)
- `parsers/skill_confidence.py` : confidence scoring logic (all the numbers in one place)
- `data/samples/sample_skills_output.json` : example of the structured output
- `tests/test_skill_extractor.py` : unit tests
- `docs/Day9_Skill_Extraction_Engine.md` : beginner guide (how it works, worked example, exercises)


## Day 10 - Experience parsing and relevance engine

- parsers/experience_parser.py : jobs (company, title, dates), total experience, gaps, overlaps
- parsers/experience_relevance.py : role-to-role similarity and experience relevance score (0-100) for a job
- run_experience_demo.py : parse every resume and score it against every parsed job (saves to data/experience/)
- tests/test_experience.py : unit tests
- docs/DAY10_STUDY_GUIDE.md : step-by-step explanation

Run: `python run_experience_demo.py`   Test: `python -m unittest tests.test_experience -v`


## Day 11 - Education & certification parsing, academic profile, education relevance

Extracts academic qualifications and certifications from resumes, builds one structured academic profile,
and scores how well it fits a job.

- parsers/education_parser.py : degree, field of study, institution, start/end year, grade; certifications
  (name, issuer, dates, credential ID, level, relevance category); names are normalized
  (B.S. / BSc -> B.Sc, CSE -> Computer Science, Amazon Web Services -> AWS)
- parsers/academic_profile.py : `build_academic_profile()` gives one object: highest degree, primary field,
  latest graduation year, in-progress degrees, certifications, counts, warnings and schema-ready lists
- parsers/education_relevance.py : `score_education()`, `score_certifications()` and
  `score_education_with_certifications()`; every score comes with reasons
- ats_engine/scoring_engine.py : the Day 13 education part now calls `score_education()` (one source of truth)
- run_education_demo.py : parse every resume and score it against every parsed job (saves to data/education/)
- tests/test_education.py : unit tests
- docs/DAY11_STUDY_GUIDE.md : step-by-step explanation with a worked example

How the score is built: education = 100 x (0.6 x level fit + 0.4 x field fit), weights from
ats_engine/ats_weights.json. Certifications add at most 10 points (half if the required degree level is not
met) and never replace a missing degree.

Run: `python run_education_demo.py`   Test: `python -m unittest tests.test_education -v`
Single resume: `python -m parsers.academic_profile data/raw_resumes/Maya.pdf`


## Day 12 - Semantic matching engine, similarity scorer and accuracy report

Moves beyond keyword matching: resumes and job descriptions are turned into embeddings (vectors) and compared by meaning.
A resume and a job get one 0-100 similarity score, a label (strong / good / partial / weak), the part scores, the skills that
matched or are missing, and plain-English reasons. A report measures how accurate this is.

**Deliverables**

1. Semantic matching engine: `matching/embedders.py` + `matching/semantic_engine.py`
2. Resume-to-job similarity scorer: `matching/similarity_scorer.py` + `matching/similarity_thresholds.json`
3. Matching accuracy report: `docs/Day12_Matching_Accuracy_Report.md` (written by `run_matching_eval.py`)

**How it works**

- `matching/embedders.py`: two interchangeable backends.
  - `SentenceTransformerEmbedder`: neural embeddings (`pip install sentence-transformers`, model downloads on first use)
  - `HashingEmbedder`: offline numpy fallback (knows Day 9 skill synonyms/categories and related words)
  - `get_embedder()` uses the neural model when available, otherwise the offline one
- `matching/semantic_engine.py`: `SemanticMatcher.match(resume, job)` compares
  - skills (exact matches plus related skills, missing skills listed)
  - experience summaries (job history vs job responsibilities)
  - project descriptions (parts with no data are skipped and weights re-scaled)
  - default weights: skills 45%, experience 35%, projects 20% (constants at the top of the file)
- `matching/similarity_scorer.py`: one entry point on top of the matcher.
  - `score_resume_to_job(resume, job_profile, job_doc)`: score, label, part scores, matched / missing skills, reasons
  - `score_many(resumes, job_profile, job_doc)`: ranks a list of resumes for one job (best first, unscorable last)
  - accepts a file path, resume text or ready-made views; scanned or empty resumes return status `unscorable`, never a fake 0
- `matching/similarity_thresholds.json`: the label cut-offs (strong 75, good 42, partial 16). They are data, not code,
  and are checked when loaded (all numbers 0-100 and strong > good > partial). Edit the file to change them.
- `matching/evaluation.py`: metric functions (precision, recall, F1, accuracy, threshold sweep, AUC, ranking quality,
  leave-one-job-out). Pure functions, easy to check by hand.
- `run_matching_eval.py`: scores every labeled pair, tunes the cut-offs, runs the validation and writes the report.
- `data/samples/matching_ground_truth.json`: 24 labeled pairs (6 resumes x 4 jobs). The labels are judgments by Claude,
  not by a recruiter, so a person should review them (the close calls are marked doubtful).

**Run**

- Demo: `python run_matching_demo.py` (prints the embedding backend used, then every resume vs every job)
- One pair: `python -m matching.similarity_scorer data/raw_resumes/Maya.pdf data/parsed_jobs/jd_mern_developer.profile.json` (add `--json` for raw output)
- Accuracy report: `python run_matching_eval.py` (writes `data/matching/matching_eval.json` and the report)
- Also save the tuned cut-offs: `python run_matching_eval.py --write-thresholds`
- Tests: `python -m unittest tests.test_similarity_scorer tests.test_matching_eval tests.test_ranking -v`

```python
from matching.similarity_scorer import score_resume_to_job, score_many
result = score_resume_to_job("data/raw_resumes/Maya.pdf", job_profile, job_doc)
result["score"], result["label"], result["reasons"]
ranked = score_many(["a.pdf", "b.pdf"], job_profile, job_doc)
```

**Needs `numpy`** (the offline embedder uses it): `pip install numpy`. It is not in `requirements.txt` yet, so add it there.

**Results and limits (read the report before trusting the numbers)**

- Only 24 labeled pairs (3 relevant, 10 partly relevant, 11 not relevant), so the numbers are indicative, not statistically strong.
- The cut-offs were tuned on the same 24 pairs, so they will move when more labeled data is added.
- `strong` (75) is not tuned: no sample pair scores above 55, so no pair is labeled `strong` with the offline embedder.
- Scanned resumes (`img.pdf`, `sample_scanned.pdf`) cannot be scored until OCR is added; `m.pdf` is not a resume.

Study guide: `docs/DAY12_STUDY_GUIDE.md`

## Day 13 - ATS scoring formula (explainable candidate score)

Scores a resume against a job from 0 to 100 using four parts, and explains every number.

    overall = skill_match x w1 + experience_relevance x w2 + education_alignment x w3 + semantic_similarity x w4

- `ats_engine/scoring_engine.py` : the ATS scoring engine (four parts, missing-data rules, explainable report)
- `ats_engine/ats_weights.json` : the configurable weights (default, per profile, per role, missing-data policy, cutoffs)
- `ats_engine/weights.py` : loads and checks the weights, picks the right set for each job, re-scales when a part is skipped
- `ats_engine/score_generator.py` : candidate score generator (resume file -> all earlier modules -> report, ranking, saving)
- `run_ats_demo.py` : scores every resume in `data/raw_resumes/` against every job in `data/parsed_jobs/` (saves to `data/ats_scores/`)
- `tests/test_ats_engine.py` : unit tests

Run: `python run_ats_demo.py`
One pair: `python -m ats_engine.score_generator data/raw_resumes/Maya.pdf data/parsed_jobs/jd_mern_developer.profile.json`
Test: `python -m unittest tests.test_ats_engine -v`

Change how much each part counts by editing `ats_engine/ats_weights.json` (no Python needed).
A single job can override the weights with an `"ats_weights"` object in its profile.


## Day 14 - Candidate ranking and shortlisting

Sorts candidates by ATS score, puts them into three zones (shortlisted / review / rejected), builds top candidate lists
and writes recruiter-friendly files.

**Deliverables**

1. Auto-ranking engine: `ats_engine/ranking_engine.py`
2. Shortlisting automation module: `ats_engine/shortlisting.py` + `ats_engine/shortlist_config.json`
3. Ranked candidate output: `data/rankings/` and `data/shortlists/` (`.json`, `.csv`, `.txt` for every job)

**How it works**

- `ranking_engine.py`: orders candidates of ONE job by overall score, then skill score, then experience score, then data
  completeness, then candidate id. `position` is always unique; `rank` is shared by equal scores (shown as `T-2`).
  Builds the score summary (highest, lowest, average, median), the top-N list and warnings.
- `shortlisting.py`: zones from the score, then safety rules.
  - score >= 60: SHORTLISTED (invite to the next round); 50 up to 60: REVIEW (recruiter checks the resume);
    below 50: REJECTED (send rejection)
  - low confidence: always REVIEW; more than 3 missing must-have skills: REVIEW; auto-reject off: reject zone becomes
    REVIEW; `max_shortlist`: extra qualified candidates become WAITLIST (ties with the last place stay together)
  - warnings tell the truth (nobody reached the cutoff vs a safety rule held people back, duplicate ids, low confidence)
- `shortlist_config.json`: all numbers. Order (later wins): default, role override, the job's `ats_cutoff_score`, command line.
  The defaults agree with the Day 13 thresholds in `ats_weights.json` (shortlist 60, review margin 10).

**Run**

- All four jobs in one command: `python run_ranking_demo.py` (writes `data/rankings/` and `data/shortlists/`)
- One job: `python -m ats_engine.shortlisting data/parsed_jobs/jd_mern_developer.profile.json data/raw_resumes`
- Without scoring again: `python -m ats_engine.shortlisting data/parsed_jobs/jd_mern_developer.profile.json --ranking data/rankings/job_mern_developer.ranking.json`
- Options: `--cutoff 65`, `--reject-below 45`, `--max-shortlist 3`, `--top 3`, `--no-auto-reject`
- Tests: `python -m unittest tests.test_ranking tests.test_shortlisting -v`

Study guide: `docs/DAY14_STUDY_GUIDE.md`

**Limits**

- The sample resumes are tiny dummy files, so nobody reaches the shortlist score of 60 for any job. The module says so in a warning.
- Scanned resumes score 0 but go to REVIEW, not REJECTED, because their confidence is low.
- The thresholds and the missing-skill limit (3) are defaults, not business rules: change them in `shortlist_config.json`.


## Day 15 - Fairness, normalization and bias reduction

Deliverable 1 of 3 (fair scoring improvements) is done; normalization logic and the bias-reduction documentation follow.

- `ats_engine/fair_scoring.py`
  - `FairATSScoringEngine` (extends the Day 13 engine): **less dependence on keywords**. A matched skill that is only listed earns 70% of the credit of a skill that is also used in a job or project. Not penalised: soft skills, skills whose name is an ordinary word (express, go, r...), and resumes with no experience/project text (nothing to check against). Keyword stuffing (20+ listed skills, under 35% used) is flagged and an automatic "shortlist" becomes "review".
  - `normalize_reports()` and `fair_score_resumes()`: **scoring normalization** per job pool (percentile, T-score or min-max). Pools under 5 candidates are not normalized; resumes where nothing could be scored are left out of the pool. The raw `overall_score` is never changed; reports gain `fairness` and `normalized` blocks.
- Run: `python run_fair_scoring_demo.py` (optional arguments: job profile path, minimum pool size)
- Test: `python -m unittest tests.test_fair_scoring -v`
- No new ML model is used.
- Still to do: resume normalization and masking of personal attributes, bias-indicator evaluation, bias-reduction documentation.
