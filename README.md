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

