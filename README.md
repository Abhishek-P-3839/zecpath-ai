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
