"""Day 10: Experience parser.

Turns the "experience" section of a resume into a structured experience object:

    company names, job titles, start/end dates, durations  ->  one entry per job
    total experience (overlapping jobs are NOT counted twice)
    gaps between jobs and overlapping jobs

Pipeline (each step is one small function, so it is easy to test and to study):

    experience text
        -> split_into_entries()    find every job (a line that contains a date range)
        -> split_header()          "Title | Company  Jan 2020 - Present" -> title, company
        -> parse_date_range()      "Jan 2020 - Present" -> (2020, 1) .. today
        -> compute_total_months()  merge overlapping jobs, add up the months
        -> find_gaps() / find_overlaps()
        -> parse_experience()      the main entry point, returns the structured object

Run it:
    python -m parsers.experience_parser data/raw_resumes/Maya.pdf
"""
import re
import sys
from datetime import date

from parsers import skill_extractor as _skills
from parsers.jd_parser import normalize_role
from utils.logger import get_logger

log = get_logger(__name__)

MIN_GAP_MONTHS = 3        # a break shorter than this is normal (notice period, holiday) and is ignored
MAJOR_GAP_MONTHS = 6      # a break this long or longer is marked "major"

# --------------------------------------------------------------------------- dates

_MONTHS = {"jan": 1, "feb": 2, "mar": 3, "apr": 4, "may": 5, "jun": 6,
           "jul": 7, "aug": 8, "sep": 9, "oct": 10, "nov": 11, "dec": 12}

# One date: "Jan 2020", "January, 2020", "03/2020" or just "2020".
_DATE = (r"(?:(?:jan|feb|mar|apr|may|jun|jul|aug|sep|sept|oct|nov|dec)[a-z]*\.?\s*,?\s*(?:19|20)\d{2}"
         r"|\d{1,2}/(?:19|20)\d{2}"
         r"|(?:19|20)\d{2})")
_NOW = r"(?:present|current|currently|now|till date|to date|ongoing|today|till now)"
DATE_RANGE_RE = re.compile(
    rf"({_DATE})\s*(?:-|\u2013|\u2014|to|until|till)\s*({_DATE}|{_NOW})(?![\w/])", re.IGNORECASE)
_ONE_DATE_RE = re.compile(
    r"(?:(?P<mon>[a-z]{3})[a-z]*\.?\s*,?\s*(?P<y1>(?:19|20)\d{2})"
    r"|(?P<m2>\d{1,2})/(?P<y2>(?:19|20)\d{2})"
    r"|(?P<y3>(?:19|20)\d{2}))", re.IGNORECASE)


def parse_date(token, is_end=False, today=None):
    """'Jan 2020' -> (2020, 1, 'month').   '2020' -> (2020, 1, 'year') for a start, (2020, 12, 'year') for an end.

    'Present' / 'Current' -> today's year and month. Returns None if the token is not a date.
    """
    today = today or date.today()
    token = token.strip().lower()
    if re.fullmatch(_NOW, token):
        return today.year, today.month, "present"
    match = _ONE_DATE_RE.fullmatch(token)
    if not match:
        return None
    if match.group("mon"):
        month = _MONTHS.get(match.group("mon")[:3].lower())
        if month:
            return int(match.group("y1")), month, "month"
        return None
    if match.group("m2"):
        month = int(match.group("m2"))
        return (int(match.group("y2")), month, "month") if 1 <= month <= 12 else None
    return int(match.group("y3")), (12 if is_end else 1), "year"


def month_index(year, month):
    """Count months on one number line so we can subtract dates: Jan 2020 = 24240."""
    return year * 12 + (month - 1)


def index_to_ym(index):
    """Back to the schema format 'YYYY-MM'."""
    return f"{index // 12:04d}-{index % 12 + 1:02d}"


def parse_date_range(text, today=None):
    """Find the first date range in a text. Returns a dict or None.

    {"start": 24240, "end": 24299, "is_current": False, "precision": "month",
     "span": (start_char, end_char), "warnings": [...]}
    """
    today = today or date.today()
    match = DATE_RANGE_RE.search(text)
    if not match:
        return None
    start = parse_date(match.group(1), is_end=False, today=today)
    end = parse_date(match.group(2), is_end=True, today=today)
    if not start or not end:
        return None

    warnings = []
    start_i = month_index(start[0], start[1])
    end_i = month_index(end[0], end[1])
    today_i = month_index(today.year, today.month)
    if end_i > today_i and end[2] != "present":
        warnings.append("End date is in the future; counted only up to today.")
        end_i = today_i
    if end_i < start_i:
        warnings.append("End date is before the start date; duration not trusted.")
    precision = "year" if "year" in (start[2], end[2]) else "month"
    if precision == "year":
        warnings.append("Only years were written (no months); duration is approximate.")
    return {"start": start_i, "end": end_i, "is_current": end[2] == "present",
            "precision": precision, "span": match.span(), "warnings": warnings}


# --------------------------------------------------------------------------- titles / companies

TITLE_WORDS = (
    "engineer|developer|manager|analyst|intern|internship|trainee|executive|specialist|coordinator|"
    "consultant|designer|architect|lead|director|officer|associate|administrator|assistant|head|"
    "scientist|recruiter|representative|programmer|tester|accountant|supervisor|founder|owner|"
    "president|sde|sre|qa|writer|editor|teacher|lecturer|technician|operator|strategist|advisor|"
    "agent|clerk|auditor|researcher|freelancer|apprentice"
)
_TITLE_RE = re.compile(rf"\b({TITLE_WORDS})\b", re.IGNORECASE)
_COMPANY_SUFFIX_RE = re.compile(
    r"\b(inc|llc|ltd|limited|pvt|corp|corporation|company|technologies|technology|solutions|systems|"
    r"labs|group|services|consulting|software|infotech|enterprises|agency|studios?|bank|university)\b",
    re.IGNORECASE)
_US_STATE_RE = re.compile(r"^[A-Z]{2}$")
_BULLET_RE = re.compile(r"^\s*[-\u2022*\u2013\u25aa\u25cf\u25e6\u00b7>]\s+")
_METRIC_RE = re.compile(r"\d+\s*%|\d+\s*\+|[$\u20b9\u20ac\u00a3]\s?\d|\b(?:INR|USD|EUR)\b|\b\d+x\b|\b\d{2,}\b")

_SEPARATORS = [" | ", " @ ", " at ", " \u2013 ", " \u2014 ", " - ", " \u2022 "]

_EMPLOYMENT_CUES = [
    ("internship", re.compile(r"\b(intern|internship|trainee|apprentice)\b", re.I)),
    ("freelance", re.compile(r"\bfreelanc\w*\b", re.I)),
    ("contract", re.compile(r"\b(contract|contractor|consultant)\b", re.I)),
    ("part_time", re.compile(r"\bpart[- ]time\b", re.I)),
    ("full_time", re.compile(r"\bfull[- ]time\b", re.I)),
]


def looks_like_title(text):
    return bool(_TITLE_RE.search(text or ""))


def looks_like_location(text):
    """'Austin, TX' / 'Bengaluru, India' / 'Remote'. A short, comma-separated, capitalised phrase."""
    text = (text or "").strip()
    if not text or len(text) > 50 or any(ch.isdigit() for ch in text) or _BULLET_RE.match(text):
        return False
    if re.fullmatch(r"(remote|hybrid|on-?site)", text, re.IGNORECASE):
        return True
    parts = [p.strip() for p in text.split(",")]
    return len(parts) >= 2 and all(p and p[0].isupper() and len(p.split()) <= 3 for p in parts)


def _clean(text):
    return re.sub(r"\s+", " ", (text or "")).strip(" |-\u2013\u2014\u2022,;:@()")


def _split_company_location(text):
    """'Lakefront Logistics Tech, Chicago, IL' -> ('Lakefront Logistics Tech', 'Chicago, IL')."""
    text = _clean(text)
    if "," not in text:
        return text, None
    first, rest = text.split(",", 1)
    # keep 'Acme, Inc.' together: only split when what follows looks like a place
    if _COMPANY_SUFFIX_RE.fullmatch(rest.strip(" .").lower()) or not first.strip():
        return text, None
    rest = rest.strip()
    place_parts = [p.strip() for p in rest.split(",")]
    if all(p and p[0].isupper() for p in place_parts) and len(place_parts) <= 3:
        return first.strip(), rest
    return text, None


def split_header(header):
    """Split a job header into (title, company, location).

        'Senior Project Analyst | Apex Digital Solutions'  -> title, company
        'Software Engineer II - Bluebonnet Cloud, Austin, TX' -> title, company, location
        'Intern at Demo Corp'                              -> title, company
        'Google - Software Engineer'                       -> title, company  (order is detected)
    """
    header = _clean(header)
    location = None
    extra = re.search(r"\(([^)]*)\)", header)       # '(Remote)' / '(Contract)' notes
    if extra:
        if looks_like_location(extra.group(1)):
            location = extra.group(1).strip()
        header = _clean(header.replace(extra.group(0), " "))

    for sep in _SEPARATORS:
        if sep in header:
            left, right = header.split(sep, 1)
            break
    else:
        if "," in header:                            # 'Software Engineer, Google'
            left, right = header.split(",", 1)
        else:
            return (header or None), None, location

    left, right = _clean(left), _clean(right)
    # Decide which side is the job title.
    if looks_like_title(left) and not looks_like_title(right):
        title, company = left, right
    elif looks_like_title(right) and not looks_like_title(left):
        title, company = right, left
    elif looks_like_title(left) and looks_like_title(right):
        # both have title words ('Operations Manager - Sales Team'): the one that does not look
        # like a company is the title; if still tied, the left one is.
        title, company = (right, left) if _COMPANY_SUFFIX_RE.search(left) else (left, right)
    else:
        title, company = left, right

    company, place = _split_company_location(company)
    return title or None, company or None, place or location


# --------------------------------------------------------------------------- skills used

def find_skills(text):
    """Canonical skill names mentioned in a piece of text (uses the Day 9 skill dictionary)."""
    found = []
    for match in _skills._TERM_RE.finditer(text or ""):
        key = _skills._key(match.group(1))
        if key in _skills._AMBIGUOUS:          # 'go', 'r', 'spring'... too risky without context
            continue
        info = _skills._ALIAS_INDEX.get(key)
        if info and info[0] not in found:
            found.append(info[0])
    return found


# --------------------------------------------------------------------------- split into entries

def _is_header_candidate(line):
    return not _BULLET_RE.match(line) and len(line) <= 160 and DATE_RANGE_RE.search(line)


def split_into_entries(text, today=None):
    """Cut the experience section into one raw block per job.

    A job starts at a line that has a date range. If the dates sit on their own line (table style),
    the 1-2 lines above them are the header. Everything below, up to the next header, is the description.
    Returns a list of {"header": str, "range": dict | None, "body": [lines]}.
    """
    lines = [l.strip() for l in text.splitlines() if l.strip()]
    header_idx = [i for i, l in enumerate(lines) if _is_header_candidate(l)]
    if not header_idx:
        # No dates anywhere (e.g. "Intern at Demo Corp"): treat the first line as one undated job.
        if not lines:
            return []
        # prefer the first non-bullet line that has a job-title word; otherwise the first line
        pick = next((i for i, l in enumerate(lines)
                     if not _BULLET_RE.match(l) and looks_like_title(l)), None)
        if pick is None:                      # only bullets: a job with unknown title and company
            return [{"header": "", "range": None, "body": lines}]
        return [{"header": lines[pick], "range": None, "body": lines[:pick] + lines[pick + 1:]}]

    entries, used = [], set()
    for n, i in enumerate(header_idx):
        rng = parse_date_range(lines[i], today)
        before = lines[i][:rng["span"][0]] if rng else ""
        after = lines[i][rng["span"][1]:] if rng else ""
        header = _clean(before) or _clean(after)
        start_line = i
        if not _clean(before):
            # dates on their own line (or dates first): the header is the line(s) above
            above = []
            j = i - 1
            while j >= 0 and j not in used and len(above) < 2:
                prev = lines[j]
                if _BULLET_RE.match(prev) or j in header_idx or prev[0].islower() or len(prev) > 80:
                    break
                above.insert(0, prev)
                j -= 1
            if above and not header:
                header = " | ".join(above)
                start_line = i - len(above)
            elif above:
                header = " | ".join(above + [header])
                start_line = i - len(above)
        nxt = header_idx[n + 1] if n + 1 < len(header_idx) else len(lines)
        body = lines[i + 1:nxt]
        # the last body lines may really be the title/company of the NEXT job (table style): drop them
        while n + 1 < len(header_idx) and body and _belongs_to_next_header(body, lines, nxt):
            body.pop()
        used.update(range(start_line, i + 1))
        entries.append({"header": header, "range": rng, "body": body})
    return entries


def _belongs_to_next_header(body, lines, next_header_line):
    """True when the last body line is really the company/title line of a table-style next job."""
    next_line = lines[next_header_line]
    before_next = DATE_RANGE_RE.sub("", next_line).strip(" |-\u2013\u2014")
    if before_next:                      # next header already has its title text on the same line
        return False
    last = body[-1]
    return not _BULLET_RE.match(last) and len(last) <= 80 and not last[0].islower() \
        and not last.endswith(".") and (looks_like_title(last) or _COMPANY_SUFFIX_RE.search(last) is not None)


def _build_entry(raw, today):
    """Raw block -> one structured entry."""
    title, company, location = split_header(raw["header"])
    body = list(raw["body"])

    # a short location line right under the header ('Bengaluru, India')
    if body and not _BULLET_RE.match(body[0]) and looks_like_location(body[0]):
        location = location or body.pop(0)

    bullets, loose = [], []
    for line in body:
        if _BULLET_RE.match(line):
            bullets.append(_BULLET_RE.sub("", line).strip())
        elif bullets and line[0].islower():           # a wrapped line continues the bullet above
            bullets[-1] += " " + line
        elif bullets:
            bullets.append(line)
        else:
            loose.append(line)
    responsibilities = bullets + [l for l in loose if len(l) > 3]
    description = " ".join(loose + bullets).strip() or None

    rng = raw["range"]
    notes = list(rng["warnings"]) if rng else ["No dates found for this job; it is not counted in total experience."]
    start = rng["start"] if rng else None
    end = rng["end"] if rng else None
    valid_dates = rng is not None and end >= start
    duration = (end - start + 1) if valid_dates else None     # +1: Jan..Jan is one month of work

    whole_text = " ".join([raw["header"], description or ""])
    employment_type = None
    for label, pattern in _EMPLOYMENT_CUES:
        if pattern.search(raw["header"]):
            employment_type = label
            break

    confidence, reasons = 1.0, []
    if not valid_dates:
        confidence -= 0.35; reasons.append("no usable dates")
    if rng and rng["precision"] == "year":
        confidence -= 0.1; reasons.append("year-only dates")
    if not title or not looks_like_title(title):
        confidence -= 0.2; reasons.append("title not recognised")
    if not company:
        confidence -= 0.25; reasons.append("no company found")

    return {
        "company": company or "Unknown",
        "designation": title or "Unknown",
        "normalized_designation": normalize_role(title or ""),
        "employment_type": employment_type,
        "industry": None,
        "location": location,
        "start_date": index_to_ym(start) if start is not None else None,
        "end_date": None if (rng and rng["is_current"]) else (index_to_ym(end) if end is not None else None),
        "is_current": bool(rng and rng["is_current"]),
        "duration_months": duration,
        "description": description,
        "responsibilities": responsibilities,
        "achievements": [b for b in bullets if _METRIC_RE.search(b)],
        "skills_used": find_skills(whole_text),
        # extra fields (removed by to_schema_experience, the schema does not allow them)
        "_start_index": start if valid_dates else None,
        "_end_index": end if valid_dates else None,
        "date_precision": rng["precision"] if rng else None,
        "confidence": round(max(confidence, 0.1), 2),
        "notes": notes + ([f"Low confidence: {', '.join(reasons)}."] if reasons else []),
    }


# --------------------------------------------------------------------------- totals, gaps, overlaps

def _dated(entries):
    return sorted((e for e in entries if e["_start_index"] is not None),
                  key=lambda e: (e["_start_index"], e["_end_index"]))


def merge_periods(entries):
    """Merge overlapping / back-to-back jobs into non-overlapping periods: [(start, end), ...]."""
    merged = []
    for e in _dated(entries):
        start, end = e["_start_index"], e["_end_index"]
        if merged and start <= merged[-1][1] + 1:          # overlaps or touches the previous period
            merged[-1][1] = max(merged[-1][1], end)
        else:
            merged.append([start, end])
    return [tuple(p) for p in merged]


def compute_total_months(entries):
    """Total months worked. Two jobs held at the same time count once, not twice."""
    return sum(end - start + 1 for start, end in merge_periods(entries))


def find_gaps(entries, today=None, min_gap_months=MIN_GAP_MONTHS):
    """Breaks between jobs (and since the last job if the person is not currently employed)."""
    today = today or date.today()
    gaps = []
    running_end, running_entry = None, None
    for e in _dated(entries):
        if running_end is not None:
            empty = e["_start_index"] - running_end - 1        # whole months with no job at all
            if empty >= min_gap_months:
                gaps.append({"type": "gap", "from": index_to_ym(running_end + 1),
                             "to": index_to_ym(e["_start_index"] - 1), "months": empty,
                             "severity": "major" if empty >= MAJOR_GAP_MONTHS else "minor",
                             "between": [running_entry["company"], e["company"]]})
        if running_end is None or e["_end_index"] > running_end:
            running_end, running_entry = e["_end_index"], e
    if running_end is not None and not any(e["is_current"] for e in entries):
        since = month_index(today.year, today.month) - running_end
        if since >= min_gap_months:
            gaps.append({"type": "current_gap", "from": index_to_ym(running_end + 1),
                         "to": index_to_ym(month_index(today.year, today.month)), "months": since,
                         "severity": "major" if since >= MAJOR_GAP_MONTHS else "minor",
                         "between": [running_entry["company"], None]})
    return gaps


def find_overlaps(entries):
    """Jobs whose dates overlap.

    1 month overlap            -> 'handover'   (normal: notice period / joining before leaving)
    part-time/intern/freelance -> 'concurrent' (legitimately two things at once)
    2+ months, both full-time  -> 'review'     (a recruiter should look at this)
    """
    overlaps = []
    dated = _dated(entries)
    for i, a in enumerate(dated):
        for b in dated[i + 1:]:
            months = min(a["_end_index"], b["_end_index"]) - max(a["_start_index"], b["_start_index"]) + 1
            if months <= 0:
                continue
            side_jobs = {"internship", "part_time", "freelance", "contract"}
            if months <= 1:
                kind = "handover"
            elif a["employment_type"] in side_jobs or b["employment_type"] in side_jobs:
                kind = "concurrent"
            else:
                kind = "review"
            overlaps.append({
                "companies": [a["company"], b["company"]], "designations": [a["designation"], b["designation"]],
                "from": index_to_ym(max(a["_start_index"], b["_start_index"])),
                "to": index_to_ym(min(a["_end_index"], b["_end_index"])),
                "months": months, "kind": kind})
    return overlaps


# --------------------------------------------------------------------------- main entry points

def parse_experience(text, today=None):
    """Main entry point: experience-section text -> structured experience object.

    Returns:
        entries                   list of jobs, newest first
        total_experience_months   overlaps counted once
        total_experience_years    same in years (1 decimal) - goes into resume_schema.json
        current_designation       title of the job that is current / ended last
        is_currently_employed
        gaps, overlaps            see find_gaps / find_overlaps
        warnings                  human-readable notes
    """
    today = today or date.today()
    raw_entries = split_into_entries(text or "", today)
    entries = [_build_entry(raw, today) for raw in raw_entries]
    entries.sort(key=lambda e: (e["_end_index"] is None, e["_end_index"] or 0,
                                e["_start_index"] or 0), reverse=True)

    warnings = []
    if not text or not text.strip():
        warnings.append("No experience text given (fresher, or the section was not detected).")
    for e in entries:
        for note in e["notes"]:
            warnings.append(f"{e['designation']} @ {e['company']}: {note}")

    total_months = compute_total_months(entries)
    gaps = find_gaps(entries, today)
    overlaps = find_overlaps(entries)
    for g in gaps:
        warnings.append(f"Gap of {g['months']} month(s) from {g['from']} to {g['to']} ({g['severity']}).")
    for o in overlaps:
        if o["kind"] == "review":
            warnings.append(f"Overlapping full-time jobs for {o['months']} month(s): "
                            f"{o['companies'][0]} and {o['companies'][1]}.")

    dated = _dated(entries)
    current = next((e for e in entries if e["is_current"]), None) or (entries[0] if entries else None)
    years = round(total_months / 12, 1)
    if years > 60:
        years = 60.0
        warnings.append("Total experience looked impossible (> 60 years); capped at 60.")

    result = {
        "entries": entries,
        "total_experience_months": total_months,
        "total_experience_years": years,
        "current_designation": current["designation"] if current and current["designation"] != "Unknown" else None,
        "is_currently_employed": any(e["is_current"] for e in entries),
        "career_start": index_to_ym(dated[0]["_start_index"]) if dated else None,
        "gaps": gaps,
        "overlaps": overlaps,
        "warnings": warnings,
    }
    log.info("Parsed experience: %d job(s), %.1f years, %d gap(s), %d overlap(s)",
             len(entries), years, len(gaps), len(overlaps))
    return result


_SCHEMA_KEYS = ("company", "designation", "normalized_designation", "employment_type", "industry",
                "location", "start_date", "end_date", "is_current", "duration_months", "description",
                "responsibilities", "achievements", "skills_used")


def to_schema_experience(result):
    """Only the `experience` list, in exactly the shape resume_schema.json allows.

    The schema requires a start_date, so jobs without dates are left out here (they stay in `entries`).
    """
    return [{k: e[k] for k in _SCHEMA_KEYS} for e in result["entries"] if e["start_date"]]


def parse_experience_from_resume_text(resume_text, today=None):
    """Whole resume text -> segment it (Day 8) -> parse the experience section."""
    from parsers.section_classifier import segment_resume
    segmented = segment_resume(resume_text)
    result = parse_experience(segmented["sections"].get("experience", ""), today)
    result["warnings"] = [w for w in segmented["warnings"] if "experience" in w.lower()] + result["warnings"]
    return result


def parse_experience_from_file(path, today=None):
    """PDF / DOCX file -> extract (Day 5) -> segment (Day 8) -> parse experience (Day 10)."""
    from extraction.extractor import extract_resume
    extracted = extract_resume(path, save=False)
    result = parse_experience_from_resume_text(extracted["clean_text"], today)
    result["source_file"] = extracted["source_file"]
    return result


def main(argv=None):
    import json
    args = argv if argv is not None else sys.argv[1:]
    if not args:
        print("usage: python -m parsers.experience_parser <resume.pdf|resume.docx>")
        return 1
    result = parse_experience_from_file(args[0])
    print(json.dumps(result, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
