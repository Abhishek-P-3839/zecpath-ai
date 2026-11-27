"""Day 11: Education & certification parser.

Turns the "education" and "certifications" sections of a resume into structured objects:

    education      degree type, field of study, institution, start/end year, grade
    certification  name, issuer, issue/expiry date, credential id, relevance categories

Pipeline (each step is one small function, so it is easy to test and to study):

    education text
        -> split_entries()      one entry per degree (blank line, or a new degree line)
        -> find_degree()        "B.Tech" / "Bachelor of Technology"  -> ("B.Tech", level "bachelor")
        -> extract_field()      "in Computer Science and Engineering" -> "Computer Science"
        -> find_institution()   the part that says University / College / Institute / School
        -> extract_years()      "2017 - 2021" -> (2017, 2021)      "Expected 2026" -> in_progress
        -> extract_grade()      "CGPA 8.4/10" -> {"value": 8.4, "scale": "cgpa_10"}

    certification text
        -> parse_certification()  name, issuer, dates, credential id, url
        -> tag_certification()    relevance categories: cloud, data_ai, cybersecurity ...

Naming conventions are normalized: "B.Sc" = "BS" = "Bachelor of Science", "CSE" = "Computer Science",
"Amazon Web Services" = "AWS", so later matching (Day 12+) compares like with like.

Run it:
    python -m parsers.education_parser data/raw_resumes/Maya.pdf
"""
import re
import sys
from datetime import date

from parsers.experience_parser import _DATE, parse_date
from utils.logger import get_logger

log = get_logger(__name__)

_I = re.IGNORECASE
_YEAR = r"(?:19[5-9]\d|20\d{2})"

# =========================================================================== degrees
# (pattern, short name, full name, level, flags).  Order matters: the first pattern that matches wins.
# Short ambiguous forms (BE, ME, BA, MA, BS, MS) only match in capitals so normal words are not hit.
_DEGREE_DEFS = [
    (r"\b(?:ph\s?d|doctorate|doctor of philosophy)\b", "PhD", "Doctor of Philosophy", "doctorate", _I),
    (r"\b(?:mba|pgdm|master of business administration)\b", "MBA", "Master of Business Administration", "master", _I),
    (r"\b(?:mca|master of computer applications?)\b", "MCA", "Master of Computer Applications", "master", _I),
    (r"\b(?:mtech|master of technology)\b", "M.Tech", "Master of Technology", "master", _I),
    (r"\b(?i:msc|master of science)\b|\bMS\b", "M.Sc", "Master of Science", "master", 0),
    (r"\b(?:mcom|master of commerce)\b", "M.Com", "Master of Commerce", "master", _I),
    (r"\b(?i:master of arts)\b|\bMA\b", "M.A", "Master of Arts", "master", 0),
    (r"\b(?i:master of engineering)\b|\bME\b", "M.E", "Master of Engineering", "master", 0),
    (r"\bmaster'?s?(?:\s+degree)?\b", "Master's", "Master's Degree", "master", _I),
    (r"\b(?:btech|bachelor of technology)\b", "B.Tech", "Bachelor of Technology", "bachelor", _I),
    (r"\b(?i:bachelor of engineering)\b|\bBE\b", "B.E", "Bachelor of Engineering", "bachelor", 0),
    (r"\b(?:bca|bachelor of computer applications?)\b", "BCA", "Bachelor of Computer Applications", "bachelor", _I),
    (r"\b(?:bba|bachelor of business administration)\b", "BBA", "Bachelor of Business Administration", "bachelor", _I),
    (r"\b(?i:bsc|bachelor of science)\b|\bBS\b", "B.Sc", "Bachelor of Science", "bachelor", 0),
    (r"\b(?:bcom|bachelor of commerce)\b", "B.Com", "Bachelor of Commerce", "bachelor", _I),
    (r"\b(?i:bachelor of arts)\b|\bBA\b", "B.A", "Bachelor of Arts", "bachelor", 0),
    (r"\b(?:bachelor'?s?(?:\s+degree)?|undergraduate degree)\b", "Bachelor's", "Bachelor's Degree", "bachelor", _I),
    (r"\b(?:12th|xii|class 12|std 12|hsc|higher secondary|senior secondary|intermediate|high school|a levels?)\b",
     "Higher Secondary", "Higher Secondary (Class 12)", "higher_secondary", _I),
    (r"\b(?:10th|class 10|std 10|sslc|ssc|matriculation|secondary school|gcse|icse)\b",
     "Secondary", "Secondary (Class 10)", "secondary", _I),
    (r"\b(?:diploma|polytechnic)\b", "Diploma", "Diploma", "diploma", _I),
]
DEGREES = [(re.compile(p, f), short, full, level) for p, short, full, level, f in _DEGREE_DEFS]

LEVEL_ORDER = ["secondary", "higher_secondary", "diploma", "bachelor", "master", "doctorate"]

INSTITUTION_RE = re.compile(
    r"\b(?:university|college|institute|school|academy|polytechnic|vidyalaya|iit|iiit|nit|iim)\b", _I)
IN_PROGRESS_RE = re.compile(
    r"\b(?:pursuing|persuing|ongoing|present|current(?:ly)?|expected|expecting|in progress|final year|appearing)\b", _I)
YEAR_RANGE_RE = re.compile(
    rf"({_YEAR})\s*(?:-|\u2013|\u2014|to)\s*({_YEAR}|\d{{2}}(?!\d)|present|current|ongoing|expected)", _I)

# =========================================================================== fields of study
FIELD_ALIASES = {
    "cs": "Computer Science", "cse": "Computer Science", "computer science": "Computer Science",
    "computer science and engineering": "Computer Science", "computer science engineering": "Computer Science",
    "computer engineering": "Computer Engineering",
    "it": "Information Technology", "information technology": "Information Technology",
    "ece": "Electronics & Communication Engineering",
    "electronics and communication": "Electronics & Communication Engineering",
    "electronics and communication engineering": "Electronics & Communication Engineering",
    "eee": "Electrical & Electronics Engineering",
    "electrical and electronics engineering": "Electrical & Electronics Engineering",
    "ee": "Electrical Engineering", "electrical engineering": "Electrical Engineering",
    "mech": "Mechanical Engineering", "mechanical": "Mechanical Engineering",
    "mechanical engineering": "Mechanical Engineering",
    "civil": "Civil Engineering", "civil engineering": "Civil Engineering",
    "ai": "Artificial Intelligence", "artificial intelligence": "Artificial Intelligence",
    "aiml": "Artificial Intelligence & Machine Learning", "ai and ml": "Artificial Intelligence & Machine Learning",
    "artificial intelligence and machine learning": "Artificial Intelligence & Machine Learning",
    "ds": "Data Science", "data science": "Data Science",
    "ai and data science": "Artificial Intelligence & Data Science",
    "artificial intelligence and data science": "Artificial Intelligence & Data Science",
}
# keyword -> category, checked in order (first hit wins)
FIELD_CATEGORIES = [
    ("computer_it", ("computer", "software", "information technology", "data", "artificial intelligence",
                     "machine learning", "cyber", "informatics", "information systems")),
    ("business", ("business", "management", "commerce", "finance", "accounting", "economics", "marketing")),
    ("engineering", ("engineering", "electronics", "electrical", "mechanical", "civil", "technology")),
    ("science", ("physics", "chemistry", "mathematics", "statistics", "biology", "science")),
    ("arts_humanities", ("arts", "english", "history", "psychology", "sociology", "literature", "design", "law")),
]
_NOT_FIELDS = {"hons", "honours", "honors", "distinction", "pursuing", "completed", "degree"}


def field_category(field):
    low = (field or "").lower()
    for category, words in FIELD_CATEGORIES:
        if any(w in low for w in words):
            return category
    return "other" if field else None


def normalize_field(field):
    """'Computer Science and Engineering' -> 'Computer Science';  'mechanical' -> 'Mechanical Engineering'."""
    key = re.sub(r"\s+", " ", field.lower().replace("&", " and ")).strip()
    if key in FIELD_ALIASES:
        return FIELD_ALIASES[key]
    words = re.sub(r"\band\b", "&", field.strip(), flags=_I).split()
    return " ".join(w if (w.isupper() and len(w) <= 4) or w == "&" else w.capitalize() for w in words)


# =========================================================================== small helpers
def _plain(text):
    """Remove dots (B.Tech -> BTech) but keep decimals (8.5)."""
    return re.sub(r"(?<!\d)\.|\.(?!\d)", "", text)


def _strip_bullet(line):
    return re.sub(r"^[\s\u2022\u25cf\u25aa\u25e6\u25cb\u25a0\u25a1*\u00b7>\-\u2013\u2014]+", "", line).strip()


def _lines(text):
    return [_strip_bullet(l) for l in (text or "").splitlines()]


def find_degree(text):
    """First matching degree -> dict(short, full, level, start, end) or None.  `text` should be _plain()."""
    for pattern, short, full, level in DEGREES:
        m = pattern.search(text)
        if m:
            return {"short": short, "full": full, "level": level, "start": m.start(), "end": m.end()}
    return None


def extract_field(rest):
    """The text right after the degree -> field of study (or None)."""
    rest = rest.strip()
    m = re.match(r"\(([^)]{2,60})\)", rest)
    if m:
        cand = m.group(1)
    else:
        rest = re.sub(r"^(?:[\s\-\u2013\u2014|:,/]|\b(?:in|of|with|major in|majoring in|specialization in)\b)+",
                      "", rest, flags=_I)
        cand = re.split(r"\s[-\u2013\u2014|]\s|[|,;(@\n]", rest)[0]
    cand = re.split(r"\b(?:at|from)\b|\b" + _YEAR + r"\b|\b(?:cgpa|gpa|cpi|percentage|grade|expected|pursuing)\b",
                    cand, flags=_I)[0].strip(" .:-\u2013\u2014")
    if (not cand or cand.lower() in _NOT_FIELDS or INSTITUTION_RE.search(cand)
            or re.search(r"\d", cand) or len(cand.split()) > 8 or find_degree(_plain(cand))):
        return None
    return cand


def find_institution(lines, degree_span=None):
    """Look for the part of the entry that names a university / college / school."""
    for idx, line in enumerate(lines):
        text = _plain(line)
        if degree_span and idx == degree_span[0]:
            text = text[:degree_span[1]] + " " + text[degree_span[2]:]
        for strong in re.split(r"\s[-\u2013\u2014|]\s|[|;(@\n]", text):
            parts = [p.strip() for p in strong.split(",")]
            for i, part in enumerate(parts):
                if not INSTITUTION_RE.search(part):
                    continue
                name = [part]
                for nxt in parts[i + 1:]:          # "Indian Institute of Technology, Madras" -> keep the city
                    if (nxt and not re.search(r"\d", nxt) and len(nxt.split()) <= 3 and not find_degree(nxt)
                            and field_category(nxt) == "other"):
                        name.append(nxt)
                    else:
                        break
                name = ", ".join(name)
                name = re.split(r"\b" + _YEAR + r"\b|\b(?:cgpa|gpa|cpi|percentage|grade|score)\b", name,
                                flags=_I)[0]
                name = re.sub(r"^(?:from|at|in)\s+", "", name.strip(" ,.:-\u2013\u2014"), flags=_I)
                name = name.strip(" ,.:-\u2013\u2014")
                if name:
                    return name
    return None


def extract_years(text, today=None):
    """-> (start_year, end_year, in_progress).  A single year is the graduation year."""
    today = today or date.today()
    start = end = None
    in_progress = bool(IN_PROGRESS_RE.search(text))
    m = YEAR_RANGE_RE.search(text)
    if m:
        start = int(m.group(1))
        e = m.group(2).lower()
        if e.isdigit():
            end = int(e) if len(e) == 4 else int(str(start)[:2] + e)
        else:
            in_progress = True
    else:
        years = [int(y) for y in re.findall(rf"\b{_YEAR}\b", text)]
        if years:
            end = max(years)
    if start and end and end < start:
        end = None
    if end and end > today.year:
        in_progress = True
    return start, end, in_progress


def extract_grade(text):
    """CGPA / GPA / percentage -> {"value", "scale"} or None."""
    m = re.search(r"(?:cgpa|gpa|cpi|sgpa)\s*[:\-]?\s*(\d{1,2}(?:\.\d{1,2})?)(?:\s*/\s*(\d{1,2}(?:\.\d)?))?", text, _I)
    if not m:
        m = re.search(r"\b(\d(?:\.\d{1,2})?)\s*/\s*(10|4(?:\.0)?)\b", text)
    if m:
        value, scale = float(m.group(1)), m.group(2)
        if scale:
            kind = "cgpa_10" if float(scale) == 10 else "cgpa_4" if float(scale) == 4 else "other"
        else:
            kind = "cgpa_4" if value <= 4.0 else "cgpa_10" if value <= 10 else "other"
        return {"value": value, "scale": kind}
    m = re.search(r"\b(\d{2,3}(?:\.\d{1,2})?)\s*%", text)
    if m and float(m.group(1)) <= 100:
        return {"value": float(m.group(1)), "scale": "percentage"}
    return None


# =========================================================================== education
_HEADER_WORDS = {"degree", "qualification", "course", "university", "college", "institution", "institute", "school",
                 "year", "field", "major", "grade", "cgpa", "percentage", "board", "specialization", "stream"}


def _is_table_header(line):
    parts = [p.strip().lower() for p in line.split("|") if p.strip()]
    return len(parts) >= 2 and all(p in _HEADER_WORDS for p in parts)


def split_entries(text):
    """Education text -> list of entries, each a list of lines (one entry per degree)."""
    blocks, block = [], []
    for raw in (text or "").splitlines():
        line = _strip_bullet(raw)
        if line and _is_table_header(line):
            continue
        if line:
            block.append(line)
        elif block:
            blocks.append(block)
            block = []
    if block:
        blocks.append(block)

    entries = []
    for block in blocks:
        cur = []
        for line in block:
            if find_degree(_plain(line)) and any(find_degree(_plain(l)) for l in cur):
                carry = []
                institutions = sum(bool(INSTITUTION_RE.search(l)) for l in cur)
                if institutions >= 2 and INSTITUTION_RE.search(cur[-1]) and not find_degree(_plain(cur[-1])):
                    carry = [cur.pop()]            # institution-first layout: the school belongs to the NEXT degree
                entries.append(cur)
                cur = carry
            cur.append(line)
        if cur:
            entries.append(cur)
    return entries


def build_education_entry(lines, today=None):
    """One entry (list of lines) -> structured education dict, or None if no degree was found."""
    deg_idx, deg = next(((i, d) for i, d in ((i, find_degree(_plain(l))) for i, l in enumerate(lines)) if d),
                        (None, None))
    if not deg:
        return None
    deg_line = _plain(lines[deg_idx])
    field = extract_field(deg_line[deg["end"]:])
    if not field:                                   # "Bachelor of Technology" / "Computer Science" on the next line
        for i, l in enumerate(lines):
            c = _plain(l).strip(" ,.:-")
            if i != deg_idx and c and not INSTITUTION_RE.search(c) and not re.search(r"\d", c) \
                    and len(c.split()) <= 6 and (c.lower() in FIELD_ALIASES or field_category(c) != "other"):
                field = c
                break
    field = normalize_field(field) if field else None
    institution = find_institution(lines, (deg_idx, deg["start"], deg["end"]))
    joined = " | ".join(lines)
    start, end, in_progress = extract_years(joined, today)
    grade = extract_grade(joined)
    found = [True, bool(field), bool(institution), bool(end or in_progress)]
    return {
        "degree": deg["short"], "degree_full": deg["full"], "level": deg["level"],
        "field_of_study": field, "field_category": field_category(field),
        "institution": institution, "start_year": start, "end_year": end, "in_progress": in_progress,
        "grade": grade, "confidence": round(sum(found) / len(found), 2), "raw_text": joined,
    }


def parse_education(text, today=None):
    entries, warnings = [], []
    for lines in split_entries(text):
        entry = build_education_entry(lines, today)
        if entry:
            entries.append(entry)
        else:
            warnings.append(f"Could not identify a degree in: {' | '.join(lines)[:80]}")
    for e in entries:
        missing = [k for k, v in (("field of study", e["field_of_study"]), ("institution", e["institution"]),
                                  ("year", e["end_year"] or e["in_progress"])) if not v]
        if missing:
            warnings.append(f"{e['degree']}: missing {', '.join(missing)}.")
    return entries, warnings


def highest_level(entries):
    ranked = [e["level"] for e in entries if e["level"] in LEVEL_ORDER]
    return max(ranked, key=LEVEL_ORDER.index) if ranked else None


# =========================================================================== certifications
# (pattern, canonical name, issuer, categories, level)
CERT_CATALOG = [
    (r"aws.*solutions?\s+architect.*associate|saa-c0\d", "AWS Certified Solutions Architect \u2013 Associate",
     "Amazon Web Services", ["cloud"], "associate"),
    (r"aws.*solutions?\s+architect.*professional|sap-c0\d", "AWS Certified Solutions Architect \u2013 Professional",
     "Amazon Web Services", ["cloud"], "professional"),
    (r"aws.*cloud\s+practitioner|clf-c0\d", "AWS Certified Cloud Practitioner",
     "Amazon Web Services", ["cloud"], "foundational"),
    (r"aws.*developer.*associate|dva-c0\d", "AWS Certified Developer \u2013 Associate",
     "Amazon Web Services", ["cloud", "software_development"], "associate"),
    (r"az-900|azure\s+fundamentals", "Microsoft Certified: Azure Fundamentals", "Microsoft", ["cloud"], "foundational"),
    (r"az-104|azure\s+administrator", "Microsoft Certified: Azure Administrator Associate", "Microsoft",
     ["cloud"], "associate"),
    (r"az-204|azure\s+developer", "Microsoft Certified: Azure Developer Associate", "Microsoft",
     ["cloud", "software_development"], "associate"),
    (r"professional\s+cloud\s+architect", "Google Cloud Professional Cloud Architect", "Google Cloud",
     ["cloud"], "professional"),
    (r"\bpmp\b|project management professional", "Project Management Professional (PMP)",
     "Project Management Institute", ["project_management"], "professional"),
    (r"\bcapm\b", "Certified Associate in Project Management (CAPM)", "Project Management Institute",
     ["project_management"], "associate"),
    (r"certified\s+scrum\s*master|\bcsm\b", "Certified ScrumMaster (CSM)", "Scrum Alliance",
     ["project_management"], "associate"),
    (r"\bcissp\b", "CISSP", "(ISC)\u00b2", ["cybersecurity"], "professional"),
    (r"\bceh\b|certified ethical hacker", "Certified Ethical Hacker (CEH)", "EC-Council",
     ["cybersecurity"], "associate"),
    (r"security\+", "CompTIA Security+", "CompTIA", ["cybersecurity"], "associate"),
    (r"\bccna\b", "Cisco Certified Network Associate (CCNA)", "Cisco", ["networking"], "associate"),
    (r"\bcka\b|certified kubernetes administrator", "Certified Kubernetes Administrator (CKA)", "CNCF",
     ["devops", "cloud"], "professional"),
    (r"terraform\s+associate", "HashiCorp Certified: Terraform Associate", "HashiCorp", ["devops"], "associate"),
    (r"tensorflow\s+developer", "TensorFlow Developer Certificate", "Google", ["data_ai"], "associate"),
    (r"oracle.*java|\bocp\b.*java|\bocjp\b", "Oracle Certified Professional, Java SE", "Oracle",
     ["software_development"], "professional"),
    (r"six\s+sigma.*green\s+belt", "Six Sigma Green Belt", None, ["business"], "associate"),
    (r"\bitil\b", "ITIL Foundation", "Axelos", ["it_service_management"], "foundational"),
]
CERT_CATALOG = [(re.compile(p, _I), n, i, c, l) for p, n, i, c, l in CERT_CATALOG]

# (pattern, canonical issuer, issuer type)
ISSUERS = [
    (r"\baws\b|amazon web services", "Amazon Web Services", "vendor"),
    (r"microsoft|azure", "Microsoft", "vendor"), (r"google", "Google", "vendor"),
    (r"oracle", "Oracle", "vendor"), (r"cisco", "Cisco", "vendor"), (r"\bibm\b", "IBM", "vendor"),
    (r"salesforce", "Salesforce", "vendor"), (r"red\s?hat", "Red Hat", "vendor"),
    (r"databricks", "Databricks", "vendor"), (r"hashicorp", "HashiCorp", "vendor"),
    (r"snowflake", "Snowflake", "vendor"), (r"\bmeta\b", "Meta", "vendor"),
    (r"\bcncf\b|linux foundation", "Linux Foundation", "vendor"),
    (r"project management institute|\bpmi\b", "Project Management Institute", "professional_body"),
    (r"\(?isc\)?\u00b2|\bisc2\b", "(ISC)\u00b2", "professional_body"),
    (r"ec-council", "EC-Council", "professional_body"), (r"isaca", "ISACA", "professional_body"),
    (r"comptia", "CompTIA", "professional_body"), (r"scrum alliance", "Scrum Alliance", "professional_body"),
    (r"scrum\.org", "Scrum.org", "professional_body"), (r"axelos", "Axelos", "professional_body"),
    (r"coursera", "Coursera", "learning_platform"), (r"udemy", "Udemy", "learning_platform"),
    (r"\bedx\b", "edX", "learning_platform"), (r"udacity", "Udacity", "learning_platform"),
    (r"nptel", "NPTEL", "learning_platform"), (r"linkedin learning", "LinkedIn Learning", "learning_platform"),
    (r"simplilearn", "Simplilearn", "learning_platform"), (r"great learning", "Great Learning", "learning_platform"),
    (r"datacamp", "DataCamp", "learning_platform"), (r"pluralsight", "Pluralsight", "learning_platform"),
    (r"freecodecamp", "freeCodeCamp", "learning_platform"),
]
ISSUERS = [(re.compile(p, _I), n, t) for p, n, t in ISSUERS]

# keyword regex per relevance category (used when the certification is not in CERT_CATALOG)
CATEGORY_KEYWORDS = {
    "cloud": r"\baws\b|azure|\bgcp\b|google cloud|\bcloud\b",
    "data_ai": r"\bdata\b|machine learning|deep learning|\bai\b|artificial intelligence|analytics|tableau|power ?bi"
               r"|\bnlp\b|tensorflow|pytorch|statistics",
    "software_development": r"python|java\b|javascript|react|node\.?js|full.?stack|web develop|programming|software"
                            r"|c\+\+|golang|android|spring",
    "devops": r"devops|docker|kubernetes|terraform|jenkins|ci/cd|ansible|linux",
    "cybersecurity": r"security|cissp|ethical hack|penetration|cyber",
    "networking": r"network|ccna|ccnp",
    "database": r"\bsql\b|mysql|postgres|mongodb|database|\bdba\b",
    "project_management": r"project management|scrum|agile|\bpmp\b|kanban|prince2",
    "business": r"business|marketing|finance|excel|sales|accounting",
}
CATEGORY_KEYWORDS = {k: re.compile(v, _I) for k, v in CATEGORY_KEYWORDS.items()}

LEVEL_WORDS = [
    ("foundational", r"foundational|fundamentals?|foundation|essentials?|practitioner|beginner|introduction|intro"),
    ("associate", r"associate"),
    ("professional", r"professional|expert|advanced|specialty|master"),
]
_LEVEL_SEG_RE = re.compile(r"(?:associate|professional|foundational|specialty|expert|practitioner|fundamentals?"
                           r"|advanced|essentials?)", _I)
_URL_RE = re.compile(r"https?://\S+|www\.\S+", _I)
_CRED_RE = re.compile(r"(?:credential\s*id|cert(?:ificate)?\s*(?:id|no\.?|number)|license(?:\s*(?:no|number))?|id)"
                      r"\s*[:#]\s*([A-Za-z0-9][A-Za-z0-9\-_/]{4,})", _I)
_EXPIRY_RE = re.compile(rf"(?:expires?|expiry|expiration|valid\s+(?:till|until|through|upto|up to))"
                        rf"\s*(?:on|date)?\s*[:\-]?\s*({_DATE})", _I)
_DATE_RE = re.compile(_DATE, _I)
_BY_RE = re.compile(r"\b(?i:issued\s+by|offered\s+by|by|from|via)\s+([A-Z][A-Za-z0-9&.'\u2019 \-]{1,40}?)"
                    rf"\s*(?=[,|;(\u2013\u2014]|\s-\s|\s+{_YEAR}\b|$)")
CERT_HINT_RE = re.compile(r"\bcertified\b|\bcertification\b|\bcertificate\b", _I)
_COURSE_RE = re.compile(r"\b(?:course|bootcamp|training|workshop|nanodegree|specialization|masterclass)\b", _I)


def _ym(token):
    parsed = parse_date(token)
    return f"{parsed[0]:04d}-{parsed[1]:02d}" if parsed else None


def tag_certification(name, issuer=None):
    """Relevance categories for a certification: {"categories": [...], "primary_category": str}."""
    for pattern, _n, _i, cats, _l in CERT_CATALOG:
        if pattern.search(name):
            return {"categories": list(cats), "primary_category": cats[0]}
    text = f"{name} {issuer or ''}"
    hits = [(len(p.findall(text)), cat) for cat, p in CATEGORY_KEYWORDS.items() if p.search(text)]
    hits.sort(key=lambda h: -h[0])                  # most keyword hits first (stable: keeps dict order on ties)
    cats = [c for _n, c in hits] or ["other"]
    return {"categories": cats, "primary_category": cats[0]}


def _issuer_info(text):
    for pattern, canonical, kind in ISSUERS:
        if pattern.search(text or ""):
            return canonical, kind
    return None, "unknown"


def parse_certification(line, today=None):
    """One line -> certification dict, or None if the line is not a certification."""
    today = today or date.today()
    raw = line.strip()
    work = _URL_RE.sub("", raw)
    url = (_URL_RE.search(raw) or [None])[0]
    cred = _CRED_RE.search(work)
    work = _CRED_RE.sub("", work)
    expiry = _EXPIRY_RE.search(work)
    work = _EXPIRY_RE.sub("", work)
    issued = _DATE_RE.search(work)
    work = _DATE_RE.sub("", work, count=1)
    work = re.sub(r"\b(?:issued|completed|earned|awarded|obtained|expires?)\b\s*(?:on|in)?\s*[:\-]?", "", work, flags=_I)
    work = re.sub(r"\(\s*[,\-\u2013\u2014]?\s*\)", "", work)

    catalog = next((c for c in CERT_CATALOG if c[0].search(raw)), None)
    issuer = level = None
    if catalog:
        _p, name, issuer, _cats, level = catalog
    else:
        by = _BY_RE.search(work)
        if by:
            issuer = by.group(1).strip()
            work = _BY_RE.sub("", work, count=1)
        known, _t = _issuer_info(raw)
        issuer = known or issuer
        segs = [s.strip(" -\u2013\u2014|,:;.\u2022") for s in re.split(r"\s[-\u2013\u2014|]\s|\||,", work)]
        segs = [s for s in segs if s]
        if not segs:
            return None
        name = segs[0]
        for seg in segs[1:]:
            if _LEVEL_SEG_RE.fullmatch(seg):
                name += " \u2013 " + seg.title()
            elif not issuer and re.match(r"[A-Z]", seg) and len(seg.split()) <= 4 and not re.search(r"\d", seg) \
                    and not CERT_HINT_RE.search(seg):
                issuer = seg
        if len(name) < 3 or not re.search(r"[A-Za-z]", name):
            return None
        for lvl, words in LEVEL_WORDS:
            if re.search(rf"\b(?:{words})\b", name, _I):
                level = lvl
                break
    canon_issuer, issuer_type = _issuer_info(issuer)
    issuer = canon_issuer or issuer
    expiry_date = _ym(expiry.group(1)) if expiry else None
    tags = tag_certification(name, issuer)
    return {
        "name": name, "issuer": issuer, "issuer_type": issuer_type,
        "issue_date": _ym(issued.group(0)) if issued else None, "expiry_date": expiry_date,
        "expired": bool(expiry_date and expiry_date < f"{today.year:04d}-{today.month:02d}"),
        "credential_id": cred.group(1) if cred else None, "url": url.rstrip(".,)") if url else None,
        "kind": "course" if issuer_type == "learning_platform" or _COURSE_RE.search(raw) else "certification",
        "level": level or "unspecified", **tags, "raw_text": raw,
    }


def parse_certifications(text, today=None):
    items = []
    for line in _lines(text):
        for part in re.split(r"\s*[;\u2022\u25cf\u25aa]\s*", line):
            part = part.strip()
            if not part or part.endswith(":") or part.lower().strip(" :") in ("certifications", "certificates"):
                continue
            if items and part[0].islower() and items[-1]["_open"]:          # wrapped line: join with the previous one
                items[-1]["text"] += " " + part
                continue
            if len(part.split()) <= 25:
                items.append({"text": part, "_open": not re.search(rf"{_YEAR}\)?$", part)})
    result, seen = [], set()
    for item in items:
        cert = parse_certification(item["text"], today)
        if cert and cert["name"].lower() not in seen:
            seen.add(cert["name"].lower())
            result.append(cert)
    return result


# =========================================================================== main entry points
def parse_education_and_certifications(education_text, certification_text="", today=None):
    """The main function: two section texts in, one structured result out."""
    education, warnings = parse_education(education_text, today)
    certifications = parse_certifications(certification_text, today)
    if not education:
        warnings.insert(0, "No education entries found.")
    return {"education": education, "certifications": certifications,
            "highest_level": highest_level(education), "warnings": warnings}


def _move_cert_lines(text):
    """No certifications section? Pull certification-looking lines out of an education/other section."""
    keep, moved = [], []
    for line in (text or "").splitlines():
        clean = _strip_bullet(line)
        if clean and CERT_HINT_RE.search(clean) and not find_degree(_plain(clean)):
            moved.append(clean)
        else:
            keep.append(line)
    return "\n".join(keep), "\n".join(moved)


def parse_from_resume_text(resume_text, today=None):
    """Whole resume text -> segment it (Day 8) -> parse education + certifications."""
    from parsers.section_classifier import segment_resume
    segmented = segment_resume(resume_text)
    sections = segmented["sections"]
    edu_text, cert_text = sections.get("education", ""), sections.get("certifications", "")
    if not cert_text:
        edu_text, cert_text = _move_cert_lines(edu_text)
        _rest, extra = _move_cert_lines(sections.get("other", ""))
        cert_text = (cert_text + "\n" + extra).strip()
    result = parse_education_and_certifications(edu_text, cert_text, today)
    if "education" not in sections:
        result["warnings"].insert(0, "No 'education' section detected.")
    return result


def parse_from_file(path, today=None):
    """PDF / DOCX file -> extract (Day 5) -> segment (Day 8) -> parse education (Day 11)."""
    from extraction.extractor import extract_resume
    extracted = extract_resume(path, save=False)
    result = parse_from_resume_text(extracted["clean_text"], today)
    result["source_file"] = extracted["source_file"]
    return result


_EDU_KEYS = ("degree", "level", "field_of_study", "institution", "start_year", "end_year", "grade")
_CERT_KEYS = ("name", "issuer", "issue_date", "expiry_date", "credential_id", "url")


def to_schema_education(result):
    """Only the `education` list, in the shape resume_schema.json allows (entries without an institution are left out)."""
    return [{k: e[k] for k in _EDU_KEYS if k != "grade" or e["grade"]} for e in result["education"] if e["institution"]]


def to_schema_certifications(result):
    return [{k: c[k] for k in _CERT_KEYS} for c in result["certifications"]]


def main(argv=None):
    import json
    args = argv if argv is not None else sys.argv[1:]
    if not args:
        print("usage: python -m parsers.education_parser <resume.pdf|resume.docx>")
        return 1
    print(json.dumps(parse_from_file(args[0]), indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
