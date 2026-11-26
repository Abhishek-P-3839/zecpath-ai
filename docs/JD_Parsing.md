# Day 6 - Job Description Parsing System

## 1. Purpose
Employers write job descriptions (JDs) as free text. The ATS, eligibility and scoring engines need
**structured data**. `parsers/jd_parser.py` converts one into a job object that follows
`data/schemas/job_schema.json` (Day 4), plus a small flat **AI profile** for matching and LLM prompts.

```
raw JD text -> normalize -> split sections -> extract fields -> job object (schema valid)
                                                              -> AI profile
```

## 2. How to use

```python
from parsers.jd_parser import parse_job_description, build_ai_profile

job = parse_job_description(text, job_id="job_0002", company_id="comp_0001")
profile = build_ai_profile(job)
```

| Command | What it does |
|---|---|
| `python run_jd_demo.py` | Parses every file in `data/job_descriptions/`, validates against the schema, writes `data/parsed_jobs/` |
| `python -m parsers.jd_parser <file.txt>` | Prints the job object and AI profile for one file |
| `python -m unittest tests.test_jd_parser -v` | Runs the parser tests |

`job_id` and `company_id` are optional. If missing, `job_id` is `job_` + a short hash of the text
(same text, same id) and `company_id` is `comp_unknown`. Empty text raises `ValueError`.

## 3. Pipeline steps

1. **Normalize text** (`normalize_jd_text`): remove HTML tags and entities, convert every bullet style
   and numbered list to `- `, replace smart quotes and en/em dashes, collapse extra spaces and blank lines.
   (Bullet handling reuses `extraction.normalizer.normalize_bullets` from Day 5.)
2. **Split into sections** (`split_jd_sections`): finds headings such as *Responsibilities, Requirements,
   Nice to Have, About the Role, Benefits* (many spellings). Also handles `Required Skills: Python, Java` on one line.
3. **Extract fields**: skills, title and role, experience, education, certifications, languages,
   employment type, work mode, location, openings, responsibilities.
4. **Build the job object** and **AI profile**.

## 4. Extraction rules

| Field | Rule |
|---|---|
| **Skills** | Whole-word search for every alias in `jd_taxonomy.SKILLS`. `java` never matches inside `javascript`, `sql` never matches inside `mysql`. Longest alias wins (`react native` is not also `react`). |
| **Skill importance** | `must_have` by default. `good_to_have` if the skill is under a Nice-to-have / Preferred heading, or its sentence has *preferred, good to have, bonus, a plus, added advantage*. If a skill is both, `must_have` wins. |
| **Skill min_years** | Only when the sentence names exactly one skill: `2+ years of hands-on experience with MongoDB` -> 2. |
| **Skill proficiency** | From words in the sentence: expert, strong/advanced/solid, hands-on/working knowledge, basic/familiarity. Not set for soft skills. |
| **Title** | `Job Title:` label, else the first title-like line (ignores headings, `Hiring:` prefixes and ` - Location` tails). |
| **Role names** | `normalized_title` = canonical role from `jd_taxonomy.ROLES` (`MERN Stack Developer` -> `full stack developer`). Unknown roles: the title lowercased without *senior / junior / lead*. |
| **role_category** | Known role, else title words (developer, engineer...), else 2 or more technical skills, else `non_technical`. |
| **Experience** | From lines mentioning "experience". `3-5 years` -> 3 to 5, `5+` -> 5 and no max, `up to 1 year` -> 0 to 1. Nothing found -> 0. Lines without a skill name are preferred over `3 years of React`. |
| **Level** | From the title (intern, manager, lead, senior, junior, fresher), else from min years (0 fresher, under 2 junior, under 5 mid, else senior). Internships are always `intern`. |
| **Education** | Lowest degree level mentioned. `Bachelor's or Master's` -> bachelor. `MBA or any degree` -> bachelor. `Scrum Master` is not a degree. Fields come from `jd_taxonomy.FIELDS`. |
| **Certifications** | Phrases like `AWS Certified Solutions Architect`; `required` is false when the line says preferred / a plus. |
| **Languages** | English, Hindi, Malayalam and others, only on lines about language skills. |
| **Employment type** | `Employment Type:` label, then title, then top 5 lines, else `full_time`. |
| **Work mode / location** | `Work Mode:` or `Location:` line, else top lines. `Kochi, Kerala, India (Hybrid)` -> city, state, country, hybrid. |
| **Openings** | `2 openings`, `Vacancies: 3`. Default 1. |
| **Responsibilities** | Lines under a Responsibilities heading; if none, the bullets above the first heading. |

## 5. Skill synonyms and role variations

All in `parsers/jd_taxonomy.py`. Examples:

| Written in the JD | `normalized_name` |
|---|---|
| ReactJS, React.js, react js | `react` |
| NodeJS, Node | `node.js` |
| k8s | `kubernetes` |
| Amazon Web Services | `aws` |
| Postgres | `postgresql` |
| RESTful APIs | `rest api` |

| Written as a title | `normalized_title` |
|---|---|
| MERN Stack Developer, Full-Stack Engineer | `full stack developer` |
| Front-End Engineer, React Developer | `frontend developer` |
| Recruiter, HR Recruiter | `hr executive` |

A space and a hyphen are interchangeable (`front end` = `front-end`). The job keeps the original spelling in
`name` and the canonical form in `normalized_name`. **Use `normalized_name` for matching.**
Two helpers expose this for other modules (ATS engine, resume parser): `normalize_skill(name)` and `normalize_role(title)`.

**To add a skill or role:** add one entry to `SKILLS` or `ROLES` in `jd_taxonomy.py`. No other change is needed.

## 6. Output

### Job object (`data/parsed_jobs/<name>.json`)
Follows `job_schema.json`: `schema_version, job_id, company_id, title, normalized_title, role_category,
employment_type, work_mode, location, openings, description, responsibilities, requirements, status`.
`requirements` holds `skills[]` (name, normalized_name, category, importance, min_years, proficiency),
`experience` (min_years, max_years, level), `education` (min_level, preferred_fields), `certifications`, `languages`.
Fields a JD cannot give (compensation, scoring weights, interview rounds, call settings) are left out
for the recruiter to fill in. `status` is `draft`.

### AI profile (`data/parsed_jobs/<name>.profile.json`), shortened example
```json
{
  "job_id": "job_mern_developer",
  "normalized_title": "full stack developer",
  "role_category": "technical",
  "level": "mid",
  "min_years": 3,
  "max_years": 5,
  "must_have_skills": ["rest api", "node.js", "react", "mongodb"],
  "good_to_have_skills": ["aws", "docker"],
  "education_min_level": "bachelor",
  "keywords": ["full stack developer", "rest api", "node.js", "..."],
  "summary": "mid full stack developer (technical); experience: 3-5 years. Must have: ..."
}
```
Use `must_have_skills` / `good_to_have_skills` for ATS matching, `keywords` for search or embeddings,
and `summary` as ready-made text for an LLM prompt.

## 7. Known limits (rule-based, no ML yet)
- Only skills in the taxonomy are found. Unknown skills are ignored, so the taxonomy should grow.
- Importance is judged per sentence. `Python (preferred), Java` in one sentence marks both as preferred.
- A skill named only in the company description (About section) still counts as must-have.
- Very short skills (`R`, `C`, `Go`) are not matched because they cause too many false hits (`Go` is matched as `golang`).
- Salary, interview rounds and scoring weights are not parsed from the JD text.
- Education, location and employment type use simple patterns. Unusual wording falls back to defaults.

## 8. Tests
`tests/test_jd_parser.py` (31 tests): text cleaning, headings, synonyms, false-match guards
(java/javascript, sql/mysql, Scrum Master, Lead Generation), skill importance, years ranges, education,
full parsing of the four sample JDs, schema validation of every sample, and the AI profile.
