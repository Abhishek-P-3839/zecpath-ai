# Day 8 - Resume Section Segmentation

**Goal:** automatically split a resume into its sections (Skills, Work Experience, Education, Certifications, Projects ...) so later AI models read structured, meaningful text instead of one big blob.

## 1. The idea in plain words

A human looks at a resume and instantly sees "this part is skills, this part is education". We teach the computer to do the same with two helpers:

| Helper | What it does | Good at | Weak at |
|---|---|---|---|
| **Rules** | Looks for heading lines such as `Work Experience`, `SKILLS:`, `Education`. Everything under a heading belongs to it. | Clear, well-written resumes | Resumes with no headings |
| **NLP scoring** | Reads the *content* of each line and asks "what does this look like?" (dates -> job, `B.Tech` -> education, `Python, SQL, Git` -> skills) | Missing / combined headings | Short, ambiguous lines |

We use **both** ("hybrid"): rules first, NLP for whatever the rules cannot explain.

## 2. The sections

`header` (name + contact), `summary`, `skills`, `experience`, `education`, `certifications`, `projects`, `other` (languages, hobbies, declaration ...).

## 3. Step by step: what happens to one resume

1. **Text comes in.** The Day 5 extractor gives clean text (`extract_resume`). The classifier takes plain text, so it also works on `.txt`.
2. **Find headings (rules).** `detect_heading(line)` handles: normal (`Experience`), CAPS and colons (`TECHNICAL SKILLS:`), numbered (`3. Core Competencies`), typos (`Experiance`), inline (`Skills: Python, SQL`), table rows (`Skills | Python`), and combined (`Certifications & Skills`, `Skills Education`).
3. **Assign lines.** A line under a single heading takes that heading's section. A line under a *combined* heading is decided by NLP, but only between the sections named in the heading.
4. **Score the remaining lines (NLP).** `score_line(text)` gives each section a score from clues: dates, job titles, action verbs (`Led`, `Built`), company words (`Pvt Ltd`), degree words (`B.Tech`, `CGPA`), university words, skill words (reuses the Day 6 skill dictionary), certificate words (`Certified`, `Coursera`), project words (`app`, `Tech stack:`), summary phrases (`years of experience`, `seeking`), contact patterns (email, phone, LinkedIn).
5. **Smooth.** Neighbouring lines usually share a section, so each line's scores are blended a little with the lines next to it. A lowercase line that follows another line is treated as a wrapped continuation and inherits its section.
6. **Pick and tag.** The highest score wins. Every line gets: `section`, `method` (`heading`, `heading+nlp`, `content`, `wrap`) and `confidence` (0-1).
7. **Build blocks and warnings.** Neighbouring lines with the same section become a block. Missing sections, no headings at all, scanned PDFs, and low-confidence blocks produce warnings.

## 4. How to use it

```python
from parsers.section_classifier import segment_file, segment_resume

result = segment_file("data/raw_resumes/Maya.pdf")      # PDF / DOCX
result = segment_resume(some_text)                      # plain text

result["sections"]     # {"skills": "...", "experience": "..."}
result["blocks"]       # [{"section", "start_line", "end_line", "method", "confidence", "text"}]
result["line_tags"]    # one dict per line
result["warnings"]     # ["No 'education' section detected."]
```

Command line: `python -m parsers.section_classifier data/raw_resumes/Maya.pdf` (add `--json` for everything).

## 5. How to teach it something new

Open `parsers/section_taxonomy.py`:

- New heading name -> add it to `HEADING_ALIASES` (e.g. `"technical proficiency"` is already there).
- New keyword (a certificate such as `ACCA`) -> add to `CERT_CODE_RE` / `CERT_WORDS`.
- A skill the classifier does not know -> add it to `SKILLS` in `parsers/jd_taxonomy.py` (shared with the JD parser).

No code changes are needed; then run `python run_section_eval.py` to see if accuracy went up.

## 6. How accuracy is measured

20 resumes were labeled by hand: each line of `data/labeled_resumes/*.labeled.txt` is `section<TAB>text`. `parsers/section_eval.py` runs the classifier and compares. Results, per-section scores, the confusion matrix and every mistake are in [Day8_Section_Detection_Accuracy_Report.md](Day8_Section_Detection_Accuracy_Report.md).

Samples are split into **real** (Day 5 outputs), **dev** (used while tuning) and **holdout** (never tuned on). Quote the holdout number as the honest one.

## 7. Known limits (next steps)

- Two-column PDFs whose columns interleave line by line are not untangled here (the Day 5 reader handles clean two-column pages).
- Scanned resumes need OCR first (flagged with a warning).
- English only.
- A headingless project title can look like a job line; a stronger sequence model (Viterbi / CRF) or a trained classifier (scikit-learn) trained on many more labeled resumes is the natural upgrade.
- Day 5's `normalizer.split_sections` is the older, simpler splitter. The Day 8 classifier replaces it for anything new; the old one is left untouched so earlier tests keep passing.
