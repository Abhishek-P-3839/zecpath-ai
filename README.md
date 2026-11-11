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
├── utils/           shared helpers (logger)
├── tests/           test files
├── logs/            log files are saved here (not pushed to GitHub)
├── docs/            CODE_STANDARDS.md
├── run_demo.py      small demo of the full flow
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

