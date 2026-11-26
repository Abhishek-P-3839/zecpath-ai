"""Resume section classifier (Day 8): split a resume into labelled sections.

Two layers work together ("hybrid"):

  1. RULES  - look for headings ("Work Experience", "SKILLS:", "Skills: Python, SQL").
              Everything under a heading belongs to that section.
  2. NLP    - for lines that no heading explains (missing headings, combined headings
              like "Certifications & Skills", the top of the resume) we score the
              *content* of each line (dates, degree names, skill words, action verbs...)
              and smooth the scores over neighbouring lines.

Use it from code:
    from parsers.section_classifier import segment_resume, segment_file
    result = segment_resume(text)          # text from extraction.extractor
    result["sections"]["skills"]           # the skills text
    result["line_tags"]                    # every line with its section

Or from the command line:
    python -m parsers.section_classifier data/raw_resumes/Maya.pdf
"""
import argparse
import difflib
import json
import re
import sys
from dataclasses import asdict, dataclass
from pathlib import Path

from parsers import section_taxonomy as tx
from parsers.jd_taxonomy import SKILLS
from utils.logger import get_logger

log = get_logger(__name__)

MODES = ("hybrid", "rules")
LOW_CONFIDENCE = 0.5
MIN_EVIDENCE = 0.4          # below this total score a line has no real evidence
SCORE_CAP = 5.0             # one very strong line must not drown out its neighbours
EXPECTED_SECTIONS = ("skills", "experience", "education")

# ------------------------------------------------------------------ small helpers

_BULLET_RE = re.compile(r"^\s*(?:[-*•●▪■◦‣∙·○]+)\s*")
_BULLET_START_RE = re.compile(r"^\s*(?:[-*•●▪■◦‣∙·○]+)\s+")
_NUMBERING_RE = re.compile(r"^(?:\d+[.)]|[ivx]+\.)\s+", re.I)
_INLINE_RE = re.compile(r"^([A-Za-z &/]{3,40}?)\s*[:|]\s*(\S.*)$")
_WORD_RE = re.compile(r"[A-Za-z0-9+#.'/-]+")
_METRIC_RE = re.compile(r"\d+\s?%|[$₹]\s?\d|\b\d+\+|\b\d+\s?(?:lakhs?|k|m)\b", re.I)
_SKILL_PHRASES = ("proficient", "familiar", "basics", "knowledge of", "hands-on", "working knowledge",
                  "exposure to", "comfortable with")


def _heading_key(text):
    """'WORK  Experience:' -> 'work experience' (lowercase letters and single spaces)."""
    text = text.lower().replace("&", " and ")
    text = re.sub(r"[^a-z ]", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def _build_alias_lookup():
    """alias key -> section label, e.g. 'work experience' -> 'experience'."""
    return {_heading_key(alias): label
            for label, aliases in tx.HEADING_ALIASES.items() for alias in aliases}


def _build_skill_regex():
    """One regex that finds any known skill (reuses the Day 6 JD skill dictionary)."""
    aliases = sorted({a for _, names in SKILLS.values() for a in names if len(a) > 1},
                     key=len, reverse=True)
    return re.compile(r"(?<![\w+#.])(?:" + "|".join(re.escape(a) for a in aliases) + r")(?![\w+#])", re.I)


_LOOKUP = _build_alias_lookup()
_SKILL_RE = _build_skill_regex()


# ------------------------------------------------------------------ result types

@dataclass
class Heading:
    """A detected heading line."""
    labels: list          # one label, or several for "Skills & Certifications"
    inline: str           # text after the colon in "Skills: Python, SQL" (or "")
    confidence: float


@dataclass
class LineTag:
    """One resume line and the section it was tagged with."""
    line_no: int          # 1-based
    text: str
    section: str
    method: str           # heading | heading+nlp | content | wrap | rule
    confidence: float
    is_heading: bool = False

    def to_dict(self):
        return asdict(self)


# ------------------------------------------------------------------ layer 1: rules

def _parse_heading_words(words):
    """['certifications', 'and', 'skills'] -> ['certifications', 'skills'] or None."""
    labels, i = [], 0
    while i < len(words):
        if words[i] == "and":
            i += 1
            continue
        for size in (4, 3, 2, 1):
            phrase = " ".join(words[i:i + size])
            if phrase in _LOOKUP:
                labels.append(_LOOKUP[phrase])
                i += size
                break
        else:
            return None
    return list(dict.fromkeys(labels)) or None


def detect_heading(line):
    """Return a Heading if the line is a section heading, else None."""
    raw = line.strip()
    if not raw or _BULLET_START_RE.match(raw):
        return None
    raw = _NUMBERING_RE.sub("", raw)

    # "Skills: Python, SQL"  or a table row "Skills | Python, SQL"
    match = _INLINE_RE.match(raw)
    if match:
        key = _heading_key(match.group(1))
        label = _LOOKUP.get(key)
        if label in tx.INLINE_SAFE and key not in tx.INLINE_BLOCKED:
            return Heading([label], match.group(2).strip(), 1.0)

    core = raw.strip(" \t:-–—_=*#|")
    words = _heading_key(core).split()
    if not words or len(words) > 6:
        return None
    labels = _parse_heading_words(words)
    if labels:
        return Heading(labels, "", 1.0)

    # typo tolerance: "Experiance", "Educaton"
    key = " ".join(words)
    looks_like_heading = raw.isupper() or raw.istitle() or raw.endswith(":")
    if len(words) <= 3 and len(key) >= 5 and looks_like_heading and not raw.endswith("."):
        close = difflib.get_close_matches(key, _LOOKUP, n=1, cutoff=0.85)
        if close:
            return Heading([_LOOKUP[close[0]]], "", 0.8)
    return None


# ------------------------------------------------------------------ layer 2: NLP scoring

def _is_listy(text):
    """True for 'Python, SQL, Git' style lists: 3+ short comma/pipe separated items."""
    body = text.split(":", 1)[1] if re.match(r"^[^:]{2,30}:\s*\S", text) else text
    items = [i.strip() for i in re.split(r"[,;|]", body) if i.strip()]
    if len(items) < 3:
        return False
    with_digits = sum(any(ch.isdigit() for ch in item) for item in items)
    if with_digits > len(items) / 3:          # "Pune, 2021 - 2025, CGPA 8.9" is not a skill list
        return False
    avg_words = sum(len(i.split()) for i in items) / len(items)
    return avg_words <= 3.5


def score_line(text):
    """Return {section: score} for one line, based only on what the line says."""
    s = {label: 0.0 for label in tx.SECTIONS}
    stripped = _BULLET_RE.sub("", text).strip()
    low = stripped.lower()
    words = _WORD_RE.findall(stripped)
    tokens = [w.lower().strip(".'-/") for w in words]
    n = len(words)
    is_bullet = bool(_BULLET_START_RE.match(text))
    first = tokens[0] if tokens else ""
    has_date = bool(tx.DATE_RANGE_RE.search(stripped))
    listy = _is_listy(stripped)
    skill_hits = len(_SKILL_RE.findall(stripped))

    # ---- header (name + contact)
    phone = tx.CONTACT_PHONE_RE.search(stripped)
    if tx.CONTACT_EMAIL_RE.search(stripped):
        s["header"] += 4
    if phone and sum(c.isdigit() for c in phone.group(0)) >= 9:
        s["header"] += 4
    if tx.CONTACT_URL_RE.search(stripped):
        s["header"] += 3
    if tx.CITY_STATE_RE.search(stripped) and n <= 8 and not has_date:
        s["header"] += 1.5

    # ---- skills
    weight = 1.1 if (listy or n <= 5) else 0.6
    s["skills"] += min(skill_hits, 6) * weight
    if listy:
        s["skills"] += 2.0
        if re.match(r"^[^:]{2,30}:\s*\S", stripped):
            s["skills"] += 1.0
    if n <= 4 and skill_hits:
        s["skills"] += 0.8
    if any(p in low for p in _SKILL_PHRASES):
        s["skills"] += 1.0
    if n >= 12 and not listy:
        s["skills"] -= 1.5
    if first in tx.ACTION_VERBS:
        s["skills"] -= 1.5

    looks_educational = bool(tx.DEGREE_RE.search(stripped) or tx.DEGREE_SHORT_RE.search(stripped)
                             or set(tokens) & (tx.EDU_PLACE_WORDS | tx.EDU_WORDS))

    # ---- experience
    if has_date:
        s["experience"] += 1.5 if looks_educational else 3.5
    title_hits = len(set(tokens) & tx.JOB_TITLE_WORDS)
    if title_hits and n <= 14 and not listy:
        s["experience"] += 1.5 + 0.5 * (title_hits - 1)
    if first in tx.ACTION_VERBS:
        s["experience"] += 2.5 if is_bullet else 1.8
        if _METRIC_RE.search(stripped):
            s["experience"] += 0.8
    if set(tokens) & tx.COMPANY_WORDS and n <= 14:
        s["experience"] += 1.5
    if re.search(r"\b(?:intern|engineer|developer|analyst|manager)\s+at\s+[A-Z]", stripped):
        s["experience"] += 1.5
    if title_hits and re.search(r"\s[|–-]\s", stripped):
        s["experience"] += 1.0

    # ---- education
    if tx.DEGREE_RE.search(stripped) or tx.DEGREE_SHORT_RE.search(stripped):
        s["education"] += 3.0
    if set(tokens) & tx.EDU_PLACE_WORDS:
        s["education"] += 2.5
    if set(tokens) & tx.EDU_WORDS:
        s["education"] += 2.0
    if n <= 8 and tx.YEAR_RE.search(stripped) and not has_date:
        s["education"] += 0.3

    # ---- certifications
    if set(tokens) & tx.CERT_WORDS:
        s["certifications"] += 3.2
    if any(p in low for p in tx.CERT_PROVIDERS):
        s["certifications"] += 1.5
    if tx.CERT_CODE_RE.search(stripped):
        s["certifications"] += 2.0
    if re.search(r"\b(?:issued|valid until|credential id)\b", low):
        s["certifications"] += 2.0

    # ---- projects
    project_hits = set(tokens) & tx.PROJECT_WORDS
    if project_hits and n <= 8:
        s["projects"] += (1.6 if "project" in project_hits or "projects" in project_hits else 0.9)
        if len(project_hits) > 1:
            s["projects"] += 0.5
    if any(m in low for m in tx.PROJECT_MARKERS[:5]):
        s["projects"] += 2.0
    if any(m in low for m in tx.PROJECT_MARKERS[5:]) and not tx.CONTACT_EMAIL_RE.search(stripped):
        s["projects"] += 1.2
    if first in tx.ACTION_VERBS:
        s["projects"] += 0.8
    if low.startswith(tx.PROJECT_MARKERS[:5]):       # "Tech stack: A, B, C" describes ONE project
        s["projects"] += 3.5
        s["skills"] -= 2.5

    # ---- summary
    phrase_hits = sum(1 for p in tx.SUMMARY_PHRASES if p in low)
    s["summary"] += 2.5 * min(phrase_hits, 2)
    if not is_bullet and n >= 12 and not has_date and not listy:
        s["summary"] += 1.0
    if re.search(r"\b(?:i|my|i'm)\b", low):
        s["summary"] += 1.5
    if stripped.endswith(".") and n >= 5 and not is_bullet:
        s["summary"] += 0.5
    if re.search(r"\d\+?\s*years?", low):
        s["summary"] += 1.0
    if phrase_hits == 0 and re.search(r"\bfresher\b", low):
        s["summary"] += 2.5
    if is_bullet:
        s["summary"] -= 1.0

    # ---- other
    if any(p in low for p in tx.OTHER_PHRASES):
        s["other"] += 3.0
    return s


def _smooth(raws, idxs):
    """Blend each line's scores with its neighbours' (neighbours across a blank line count less)."""
    raws = [{label: min(value, SCORE_CAP) for label, value in vec.items()} for vec in raws]
    out = []
    for k, vec in enumerate(raws):
        blended = dict(vec)
        for step, weight in ((1, 0.35), (2, 0.15)):
            for j in (k - step, k + step):
                if 0 <= j < len(raws):
                    gap = abs(idxs[j] - idxs[k]) > abs(j - k)      # a blank line sits between
                    for label, value in raws[j].items():
                        blended[label] += value * weight * (0.4 if gap else 1.0)
        out.append(blended)
    return out


def _looks_like_name(text):
    """'Priya Nair' -> True.  Short, capitalised words, no digits, no known skill."""
    words = text.split()
    return (1 <= len(words) <= 5 and all(w[:1].isupper() and w.replace(".", "").isalpha() for w in words)
            and not _SKILL_RE.search(text) and "@" not in text)


def _pick(vec, candidates):
    """Best candidate label and a confidence between 0 and 1."""
    ranked = sorted(candidates, key=lambda lab: vec[lab], reverse=True)
    top = ranked[0]
    positive = sum(max(vec[lab], 0.0) for lab in candidates)
    confidence = (vec[top] / positive) if positive > 0 and vec[top] > 0 else 0.0
    return top, round(confidence, 2), vec[top]


# ------------------------------------------------------------------ putting it together

def classify_lines(text, mode="hybrid"):
    """Tag every non-blank line of the text with a section. Returns a list of LineTag."""
    if mode not in MODES:
        raise ValueError(f"mode must be one of {MODES}, got {mode!r}")
    lines = (text or "").split("\n")
    nonblank = [i for i, ln in enumerate(lines) if ln.strip()]
    position = {idx: k for k, idx in enumerate(nonblank)}

    # Pass 1 (rules): find headings, remember which heading each body line sits under.
    plan, current = {}, None
    for i in nonblank:
        heading = detect_heading(lines[i])
        if heading:
            inside_shared_block = (heading.inline and current and len(current) > 1
                                   and heading.labels[0] in current)
            if not inside_shared_block:       # "Certifications: ..." inside "Certifications & Skills"
                current = tuple(heading.labels)
            plan[i] = ("heading", heading)
        else:
            plan[i] = ("body", current)

    tags = {}
    for i in nonblank:
        kind, info = plan[i]
        if kind == "heading":
            tags[i] = LineTag(i + 1, lines[i], info.labels[0], "heading", info.confidence, True)
        elif info is not None and len(info) == 1:
            tags[i] = LineTag(i + 1, lines[i], info[0], "heading", 1.0)
        elif mode == "rules":                       # rules-only baseline
            label = info[0] if info else "header"   # before any heading = header
            tags[i] = LineTag(i + 1, lines[i], label, "rule", 1.0 if info else 0.5)

    if mode == "hybrid":
        _classify_open_runs(lines, nonblank, plan, position, tags)

    return [tags[i] for i in nonblank]


def _classify_open_runs(lines, nonblank, plan, position, tags):
    """Pass 2 (NLP): label lines that no single heading explains."""
    runs, last = [], None
    for i in nonblank:
        kind, info = plan[i]
        open_line = kind == "body" and (info is None or len(info) > 1)
        if not open_line:
            last = None
            continue
        if runs and last is not None and runs[-1][0] == info:
            runs[-1][1].append(i)
        else:
            runs.append((info, [i]))
        last = i

    for info, idxs in runs:
        candidates = list(info) if info else list(tx.SECTIONS)
        raws = [score_line(lines[i]) for i in idxs]
        smoothed = _smooth(raws, idxs)
        previous = None
        for k, i in enumerate(idxs):
            vec = smoothed[k]
            if info is None:                          # top of the resume: name / contact prior
                if position[i] == 0:
                    vec["header"] += 3.0 if _looks_like_name(lines[i].strip()) else 1.0
            label, confidence, top_score = _pick(vec, candidates)
            method = "heading+nlp" if info else "content"
            text = lines[i].strip()
            if previous and text[:1].islower() and not _BULLET_START_RE.match(lines[i]):
                label, confidence, method = previous, 0.6, "wrap"      # wrapped continuation line
            elif top_score < MIN_EVIDENCE:
                label = previous or ("other" if not info else candidates[0])
                confidence = 0.2
            tags[i] = LineTag(i + 1, lines[i], label, method, confidence)
            previous = label


def _group_blocks(tags):
    """Merge neighbouring lines with the same section into blocks."""
    blocks = []
    for tag in tags:
        if blocks and blocks[-1]["section"] == tag.section:
            blocks[-1]["lines"].append(tag)
        else:
            blocks.append({"section": tag.section, "lines": [tag]})
    out = []
    for block in blocks:
        body = [t for t in block["lines"] if not (t.is_heading and t.method == "heading")]
        methods = sorted({t.method for t in block["lines"]})
        out.append({
            "section": block["section"],
            "start_line": block["lines"][0].line_no,
            "end_line": block["lines"][-1].line_no,
            "method": "+".join(methods),
            "confidence": round(sum(t.confidence for t in block["lines"]) / len(block["lines"]), 2),
            "text": "\n".join(t.text for t in body),
        })
    return out


def segment_resume(text, mode="hybrid"):
    """Main entry point. Returns a dict:

        sections    {section: text}  (in the order they appear)
        blocks      list of {section, start_line, end_line, method, confidence, text}
        line_tags   list of per-line dicts (see LineTag)
        headings    list of {line_no, labels} for every heading found
        warnings    list of human-readable notes (missing sections, low confidence...)
    """
    tags = classify_lines(text, mode)
    blocks = _group_blocks(tags)
    sections = {}
    for block in blocks:
        if block["text"]:
            joined = sections.get(block["section"], "")
            sections[block["section"]] = (joined + "\n" + block["text"]).strip()

    headings = [{"line_no": t.line_no, "labels": [t.section]} for t in tags if t.is_heading]
    warnings = []
    if not tags:
        warnings.append("Empty text: nothing to segment.")
    elif not headings:
        warnings.append("No headings found: sections were inferred from content (lower confidence).")
    for name in EXPECTED_SECTIONS:
        if tags and name not in sections:
            warnings.append(f"No '{name}' section detected.")
    low = [b for b in blocks if b["confidence"] < LOW_CONFIDENCE]
    if low:
        warnings.append(f"{len(low)} block(s) have low confidence (< {LOW_CONFIDENCE}); review them.")
    log.info("Segmented resume: %d lines, %d sections, %d headings", len(tags), len(sections), len(headings))
    return {"mode": mode, "sections": sections, "blocks": blocks,
            "line_tags": [t.to_dict() for t in tags], "headings": headings, "warnings": warnings}


def segment_file(path, mode="hybrid"):
    """Extract a PDF/DOCX with the Day 5 extractor, then segment it."""
    from extraction.extractor import extract_resume   # imported here: pdfplumber is only needed for files
    extracted = extract_resume(path, save=False)
    result = segment_resume(extracted["clean_text"], mode)
    result["source_file"] = extracted["source_file"]
    if extracted["needs_ocr"]:
        result["warnings"].append("File looks scanned (needs OCR): section detection is unreliable.")
    return result


def main(argv=None):
    parser = argparse.ArgumentParser(description="Split a resume (.pdf/.docx/.txt) into sections.")
    parser.add_argument("path")
    parser.add_argument("--mode", choices=MODES, default="hybrid")
    parser.add_argument("--json", action="store_true", help="print the full result as JSON")
    args = parser.parse_args(argv)
    path = Path(args.path)
    if path.suffix.lower() == ".txt":
        result = segment_resume(path.read_text(encoding="utf-8"), args.mode)
    else:
        result = segment_file(path, args.mode)
    if args.json:
        print(json.dumps(result, indent=2, ensure_ascii=False))
        return 0
    for block in result["blocks"]:
        print(f"[{block['section'].upper():14}] lines {block['start_line']}-{block['end_line']} "
              f"({block['method']}, conf {block['confidence']})")
    for warning in result["warnings"]:
        print("WARNING:", warning)
    return 0


if __name__ == "__main__":
    sys.exit(main())
