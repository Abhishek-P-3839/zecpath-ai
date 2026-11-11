# Code Standards

Simple rules the whole team follows.

## Python style
- Follow PEP 8 (4 spaces, max about 100 characters per line).
- Names: `snake_case` for functions and variables, `PascalCase` for classes, `UPPER_CASE` for constants.
- Use clear names (`calculate_ats_score`, not `calc`).
- Keep each function small and doing one job.

## Documentation
- Every file starts with a short docstring saying what it does.
- Every function has a one-line docstring (what it takes and what it returns).
- Use comments only for things that are not obvious.

## Logging
- Do not use `print` inside the modules. Use `get_logger(__name__)` from `utils/logger.py`.
- `info` for normal steps, `warning` for odd inputs, `error` for failures.
- Never log personal data like phone numbers or full resumes.

## Testing
- Every new function gets at least one test in `tests/`.
- Test file name: `test_<module>.py`.
- Run all tests before every commit.

## Git
- Branch names: `feature/<short-name>`, `fix/<short-name>`.
- Commit messages: short and in present tense, for example `Add resume parser`.
- Never commit `venv/`, `.env`, log files or real candidate data.
