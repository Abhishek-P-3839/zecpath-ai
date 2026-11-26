"""Job description parser (Day 6).

Turns raw employer job description text into a structured job object that follows
data/schemas/job_schema.json, plus a small flat "AI profile" for matching and prompts.

Pipeline:
    raw text -> normalize_jd_text -> split into sections -> extract fields -> job dict
    job dict -> build_ai_profile -> AI-friendly profile

Usage:
    from parsers.jd_parser import parse_job_description, build_ai_profile
    job = parse_job_description(text, job_id="job_0002", company_id="comp_0001")
    profile = build_ai_profile(job)

    python -m parsers.jd_parser data/job_descriptions/jd_mern_developer.txt
"""
import hashlib
import html
import json
import re
import sys
import unicodedata

from extraction.normalizer import normalize_bullets
from parsers.jd_taxonomy import EDUCATION, FIELDS, LEVEL_KEYWORDS, ROLES, SKILLS
from utils.logger import get_logger

log = get_logger(__name__)

SCHEMA_VERSION = "1.0"
TECHNICAL_CATEGORIES = {"programming_language", "framework", "database", "cloud_devops"}

# ---------------------------------------------------------------- text normalization

_PUNCT_MAP = str.maketrans({
    "\u2013": "-", "\u2014": "-", "\u2212": "-",   # dashes
    "\u2018": "'", "\u2019": "'", "\u201c": '"', "\u201d": '"',  # smart quotes
    "\u200b": "", "\ufeff": "",                     # invisible characters
})
_HTML_TAG = re.compile(r"</?[a-zA-Z][^>]*>")
_NUMBERED_ITEM = re.compile(r"^[ \t]*\d{1,2}[.)][ \t]+", re.MULTILINE)


def normalize_jd_text(text):
    """Return clean JD text: no HTML, one bullet style, tidy spaces and quotes."""
    text = html.unescape(unicodedata.normalize("NFKC", text or ""))
    text = text.translate(_PUNCT_MAP).replace("\r\n", "\n").replace("\r", "\n")
    text = re.sub(r"<li[^>]*>", "\n- ", text, flags=re.IGNORECASE)
    text = re.sub(r"<br\s*/?>|</p>|</div>|</h\d>|</li>|</ul>", "\n", text, flags=re.IGNORECASE)
    text = _HTML_TAG.sub(" ", text)
    text = _NUMBERED_ITEM.sub("- ", normalize_bullets(text))
    lines = [re.sub(r"[ \t]+", " ", line).strip() for line in text.split("\n")]
    return re.sub(r"\n{3,}", "\n\n", "\n".join(lines)).strip()


# ---------------------------------------------------------------- sections

JD_HEADINGS = {
    "responsibilities": ["responsibilities", "key responsibilities", "roles and responsibilities",
                         "role and responsibilities", "what you will do", "what youll do",
                         "your responsibilities", "duties", "job responsibilities"],
    "requirements": ["requirements", "required skills", "qualifications", "required qualifications",
                     "must have", "must-have", "what we are looking for", "what you need",
                     "skills required", "mandatory skills", "key skills", "eligibility",
                     "who you are", "skills and qualifications"],
    "preferred": ["preferred", "preferred skills", "preferred qualifications", "nice to have",
                  "good to have", "good-to-have", "bonus", "bonus points", "desirable",
                  "plus points", "added advantage"],
    "about": ["about the role", "about the job", "job description", "overview", "role overview",
              "about us", "who we are", "about the company"],
    "benefits": ["benefits", "perks", "what we offer", "why join us", "compensation and benefits"],
}
_HEADING_LOOKUP = {alias: key for key, aliases in JD_HEADINGS.items() for alias in aliases}


def detect_jd_heading(line):
    """Return the section key (e.g. 'requirements') if the line is a heading, else None."""
    stripped = line.strip().rstrip(":").strip()
    if not stripped or len(stripped) > 40 or stripped.startswith("- "):
        return None
    key = re.sub(r"[^a-z\- ]", "", stripped.lower())
    return _HEADING_LOOKUP.get(re.sub(r"\s+", " ", key).strip())


def split_jd_sections(text):
    """Split normalized JD text into {'header': ..., 'requirements': ..., ...}.

    A heading with text on the same line ("Required Skills: Python, Java") also works.
    """
    sections, current, buffer = {}, "header", []

    def flush():
        body = "\n".join(buffer).strip()
        if body:
            sections[current] = (sections[current] + "\n" + body) if current in sections else body

    for line in text.split("\n"):
        key, inline = detect_jd_heading(line), None
        if key is None and ":" in line:
            left, right = line.split(":", 1)
            if detect_jd_heading(left) and right.strip():
                key, inline = detect_jd_heading(left), right.strip()
        if key:
            flush()
            current, buffer = key, ([inline] if inline else [])
        else:
            buffer.append(line)
    flush()
    return sections


# ---------------------------------------------------------------- synonyms

def _key(text):
    """Lookup key for an alias: lowercase, hyphens and repeated spaces treated as one space."""
    return re.sub(r"[ -]+", " ", (text or "").strip().lower())


def _boundary_regex(aliases):
    """One regex for many aliases: longest first, so 'react native' beats 'react'.

    A space and a hyphen inside an alias match each other ('front end' also finds 'front-end').
    """
    ordered = sorted(aliases, key=len, reverse=True)
    pattern = "|".join("[ -]".join(re.escape(part) for part in re.split(r"[ -]", a)) for a in ordered)
    return re.compile(r"(?<![\w+#])(" + pattern + r")(?![\w+#])", re.IGNORECASE)


_ALIAS_TO_SKILL = {_key(alias): name for name, (_, aliases) in SKILLS.items() for alias in aliases}
_ALIAS_TO_ROLE = {_key(alias): name for name, (_, aliases) in ROLES.items() for alias in aliases}
_SKILL_RE = _boundary_regex(_ALIAS_TO_SKILL)
_ROLE_RE = _boundary_regex(_ALIAS_TO_ROLE)


def normalize_skill(name):
    """Return the canonical skill name for any spelling ('ReactJS' -> 'react'), or None."""
    return _ALIAS_TO_SKILL.get(_key(name))


def normalize_role(title):
    """Return the canonical role found in a title ('MERN Stack Developer' -> 'full stack developer')."""
    match = _ROLE_RE.search(title or "")
    return _ALIAS_TO_ROLE[_key(match.group(1))] if match else None


# ---------------------------------------------------------------- skills

_PREFERRED_CUE = re.compile(
    r"\b(preferred|nice to have|good to have|good-to-have|bonus|a plus|plus points?|desirable|"
    r"added advantage|an advantage|optional)\b", re.IGNORECASE)
_PROFICIENCY_CUES = [
    ("expert", re.compile(r"\b(expert|expertise)\b", re.IGNORECASE)),
    ("advanced", re.compile(r"\b(strong|advanced|proficient|proficiency|solid|deep)\b", re.IGNORECASE)),
    ("intermediate", re.compile(r"\b(working knowledge|hands-on|hands on|good knowledge|intermediate)\b",
                                re.IGNORECASE)),
    ("beginner", re.compile(r"\b(basic|beginner|familiar|familiarity|exposure)\b", re.IGNORECASE)),
]
_YEARS_RANGE = re.compile(
    r"(\d+(?:\.\d+)?)\s*(?:-|to)\s*(\d+(?:\.\d+)?)\s*\+?\s*(?:years?|yrs?)", re.IGNORECASE)
_YEARS_UP_TO = re.compile(
    r"(?:up\s*to|upto|maximum(?:\s+of)?)\s+(\d+(?:\.\d+)?)\s*\+?\s*(?:years?|yrs?)", re.IGNORECASE)
_YEARS_MIN = re.compile(r"(\d+(?:\.\d+)?)\s*\+?\s*(?:years?|yrs?)", re.IGNORECASE)


def _to_number(value):
    number = float(value)
    return int(number) if number.is_integer() else number


def find_years(line):
    """Return (min_years, max_years) in a line: '3-5 years' -> (3, 5), '5+ years' -> (5, None),
    'up to 1 year' -> (0, 1)."""
    match = _YEARS_RANGE.search(line)
    if match:
        low, high = sorted((_to_number(match.group(1)), _to_number(match.group(2))))
        return low, high
    match = _YEARS_UP_TO.search(line)
    if match:
        return 0, _to_number(match.group(1))
    match = _YEARS_MIN.search(line)
    return (_to_number(match.group(1)), None) if match else None


def detect_proficiency(line):
    """Return beginner / intermediate / advanced / expert from words like 'strong', or None."""
    for level, pattern in _PROFICIENCY_CUES:
        if pattern.search(line):
            return level
    return None


def _clauses(line):
    """Split a line into small parts so 'Python; AWS is a plus' is judged part by part."""
    return [c for c in re.split(r"(?<=[.;])\s+|;", line) if c.strip()]


def _merge_skill(found, skill):
    """Add a skill, or upgrade the existing one (must_have wins, empty fields get filled)."""
    old = found.get(skill["normalized_name"])
    if old is None:
        found[skill["normalized_name"]] = skill
        return
    if skill["importance"] == "must_have":
        old["importance"] = "must_have"
    for field in ("min_years", "proficiency"):
        if old[field] is None:
            old[field] = skill[field]


def extract_skills(sections):
    """Return a list of job_skill objects (schema format), must_have first."""
    found = {}
    for section, body in sections.items():
        if section == "benefits":
            continue
        for line in body.split("\n"):
            for clause in _clauses(line):
                matches = list(_SKILL_RE.finditer(clause))
                preferred = section == "preferred" or bool(_PREFERRED_CUE.search(clause))
                years = find_years(clause) if len(matches) == 1 else None
                for match in matches:
                    canonical = _ALIAS_TO_SKILL[_key(match.group(1))]
                    category = SKILLS[canonical][0]
                    _merge_skill(found, {
                        "name": match.group(1),
                        "normalized_name": canonical,
                        "category": category,
                        "importance": "good_to_have" if preferred else "must_have",
                        "min_years": years[0] if years else None,
                        "proficiency": None if category == "soft_skill" else detect_proficiency(clause),
                    })
    skills = list(found.values())
    return sorted(skills, key=lambda s: s["importance"] != "must_have")  # stable sort


# ---------------------------------------------------------------- title, role, level

_LABELLED_TITLE = re.compile(
    r"^(?:job\s+title|position|designation|role)\s*[:\-]\s*(.+)$", re.IGNORECASE)
_HIRING_PREFIX = re.compile(
    r"^(?:we\s+are\s+hiring|we're\s+hiring|now\s+hiring|hiring|job\s+opening|vacancy|opening\s+for)"
    r"\s*[:\-]?\s*(?:an?\s+)?", re.IGNORECASE)
_META_LINE = re.compile(r"^[A-Za-z ]{2,25}:\s")
_LEVEL_WORDS = re.compile(
    r"(?<![\w])(senior|sr\.?|junior|jr\.?|lead|associate|trainee)(?![\w])", re.IGNORECASE)


def _clean_title(raw):
    """Cut ' - Kochi', ' | Company' and similar tails from a title line."""
    return re.split(r"\s+[|@-]\s+|\s*\|\s*", raw.strip(" -:*#"))[0].strip()[:100]


def extract_title(text):
    """Return the job title: a 'Job Title:' label if present, else the first title-like line."""
    lines = [line for line in text.split("\n") if line.strip()][:15]
    for line in lines:
        match = _LABELLED_TITLE.match(line)
        if match:
            return _clean_title(match.group(1))
    for line in lines:
        candidate = _HIRING_PREFIX.sub("", line).strip()
        if detect_jd_heading(candidate) or candidate.startswith("- ") or len(candidate) > 80:
            continue
        if candidate and not _META_LINE.match(candidate):
            return _clean_title(candidate)
    match = _ROLE_RE.search(text[:500])
    return match.group(1).title() if match else "Untitled Role"


def normalize_title(title):
    """Canonical role if known, else the title in lowercase without level words ('senior' etc.)."""
    role = normalize_role(title)
    if role:
        return role
    cleaned = re.sub(r"\s+", " ", _LEVEL_WORDS.sub(" ", title)).strip(" -,.").lower()
    return cleaned or None


def detect_level(title, min_years, employment_type):
    """Pick intern..manager from the title words, else guess from the minimum years."""
    if employment_type == "internship":
        return "intern"
    lowered = title.lower().replace("lead generation", "")
    for level, words in LEVEL_KEYWORDS:
        pattern = r"(?<![\w])(?:" + "|".join(re.escape(w.strip()) for w in words) + r")(?![\w])"
        if re.search(pattern, lowered):
            return level
    if min_years == 0:
        return "fresher"
    return "junior" if min_years < 2 else "mid" if min_years < 5 else "senior"


def detect_role_category(canonical_role, title, skills):
    """'technical' or 'non_technical' from the known role, the title words, or the skills."""
    if canonical_role in ROLES:
        return ROLES[canonical_role][0]
    if re.search(r"\b(developer|engineer|programmer|devops|tester|architect|scientist)\b", title, re.I):
        return "technical"
    technical = [s for s in skills if s["category"] in TECHNICAL_CATEGORIES]
    return "technical" if len(technical) >= 2 else "non_technical"


# ---------------------------------------------------------------- employment, mode, location

_EMPLOYMENT_TYPES = [
    ("internship", re.compile(r"\binterns?(?:hip)?\b", re.IGNORECASE)),
    ("freelance", re.compile(r"\bfreelanc(?:e|er|ing)\b", re.IGNORECASE)),
    ("contract", re.compile(r"\bcontract(?:ual)?\b", re.IGNORECASE)),
    ("part_time", re.compile(r"\bpart[- ]time\b", re.IGNORECASE)),
    ("full_time", re.compile(r"\bfull[- ]time\b|\bpermanent\b", re.IGNORECASE)),
]
_WORK_MODES = [
    ("hybrid", re.compile(r"\bhybrid\b", re.IGNORECASE)),
    ("remote", re.compile(r"\bremote\b|\bwork from home\b|\bwfh\b", re.IGNORECASE)),
    ("onsite", re.compile(r"\bon-?site\b|\bwork from office\b|\bin-office\b|\bin office\b",
                          re.IGNORECASE)),
]
_TYPE_LABEL = re.compile(r"^(?:employment|job)\s+type\s*[:\-]\s*(.+)$", re.IGNORECASE | re.MULTILINE)
_MODE_LABEL = re.compile(r"^(?:work\s*(?:mode|type|model|location)|mode of work)\s*[:\-]\s*(.+)$",
                         re.IGNORECASE | re.MULTILINE)
_LOCATION_LABEL = re.compile(r"^(?:job\s+)?location\s*[:\-]\s*(.+)$", re.IGNORECASE | re.MULTILINE)
COUNTRIES = {"india", "usa", "united states", "uk", "united kingdom", "canada", "uae",
             "singapore", "australia", "germany"}


def _first_match(options, *scopes):
    """Return the key of the first option whose pattern matches in the first non-empty scope."""
    for scope in scopes:
        if not scope:
            continue
        for key, pattern in options:
            if pattern.search(scope):
                return key
    return None


def _label_value(pattern, text):
    match = pattern.search(text)
    return match.group(1) if match else None


def extract_employment_type(text, title):
    """full_time / part_time / internship / contract / freelance (label, title, top lines, default)."""
    top_lines = "\n".join(text.split("\n")[:5])
    label = _label_value(_TYPE_LABEL, text)
    return _first_match(_EMPLOYMENT_TYPES, label, title, top_lines) or "full_time"


def extract_work_mode(text):
    """onsite / remote / hybrid from a Work Mode or Location line, else the top lines, else None."""
    top_lines = "\n".join(text.split("\n")[:8])
    return _first_match(_WORK_MODES, _label_value(_MODE_LABEL, text),
                        _label_value(_LOCATION_LABEL, text), top_lines)


def extract_location(text):
    """Return {'city', 'state', 'country'} from a 'Location:' line (missing parts are None)."""
    location = {"city": None, "state": None, "country": None}
    value = _label_value(_LOCATION_LABEL, text)
    if not value:
        return location
    value = re.sub(r"\(.*?\)", "", value)
    value = re.sub(r"\b(remote|hybrid|on-?site)\b", "", value, flags=re.IGNORECASE)
    parts = [p.strip() for p in value.split(",") if p.strip(" -/")]
    if parts and parts[-1].lower() in COUNTRIES:
        location["country"] = parts.pop().strip()
    if parts:
        location["city"] = parts[0]
    if len(parts) > 1:
        location["state"] = parts[1]
    return location


def extract_openings(text):
    """Return the number of vacancies mentioned ('2 openings', 'Vacancies: 3'), default 1."""
    match = re.search(
        r"(\d+)\s+(?:openings?|vacanc(?:y|ies)|positions?)\b|"
        r"\b(?:openings?|vacanc(?:y|ies)|no\.? of positions)\s*[:\-]\s*(\d+)", text, re.IGNORECASE)
    count = int(match.group(1) or match.group(2)) if match else 1
    return max(count, 1)


def extract_responsibilities(sections):
    """Return the responsibility lines as plain strings.

    Without a Responsibilities heading, the bullet lines above the first heading are used.
    """
    body = sections.get("responsibilities")
    if body is None:
        header = sections.get("header", "")
        body = "\n".join(l for l in header.split("\n") if l.startswith("- "))
    return [re.sub(r"^- ", "", line).strip() for line in body.split("\n") if line.strip()]


# ---------------------------------------------------------------- experience, education, extras

def extract_experience(text, title, employment_type):
    """Return {'min_years', 'max_years', 'level'}.

    Looks at lines that mention 'experience'. Lines without a named skill are preferred,
    because '3 years of React' is skill experience, not total experience.
    """
    lines = [l for l in text.split("\n") if re.search(r"\bexperience\b|\bexp\b", l, re.IGNORECASE)]
    general = [l for l in lines if not _SKILL_RE.search(l)]
    years = next((y for y in map(find_years, general + lines) if y), None)
    if years is None:
        years = (0, None)  # nothing stated (or "fresher / entry level"): no experience needed
    return {
        "min_years": years[0],
        "max_years": years[1],
        "level": detect_level(title, years[0], employment_type),
    }


_EDUCATION_RES = [(level, _boundary_regex(words)) for level, words in EDUCATION]
_FIELD_RES = [(name, _boundary_regex(words)) for name, words in FIELDS.items()]
_LEVEL_ORDER = [level for level, _ in EDUCATION]
_ANY_DEGREE = re.compile(r"\bany\s+(?:\w+\s+)?(?:degree|graduate)\b|\bgraduates?\b", re.IGNORECASE)
_DEGREE_WORD = re.compile(
    r"\b(?:a|relevant|college|university)\s+degree\b|\bdegree\s+in\b", re.IGNORECASE)


def extract_education(text):
    """Return {'min_level', 'preferred_fields'}. min_level is the lowest degree level that is accepted.

    'any degree' counts as bachelor even if a master's is also named ('MBA or any degree').
    """
    levels = {level for level, pattern in _EDUCATION_RES if pattern.search(text)}
    if _ANY_DEGREE.search(text) or (not levels and _DEGREE_WORD.search(text)):
        levels.add("bachelor")
    fields = sorted(((m.start(), name) for name, p in _FIELD_RES for m in [p.search(text)] if m))
    min_level = min(levels, key=_LEVEL_ORDER.index) if levels else None
    return {"min_level": min_level, "preferred_fields": [n for _, n in fields]}


_CERT_PATTERNS = [
    re.compile(r"\b((?:[A-Z][\w.+#-]*\s+){0,4}Certified(?:\s+[A-Z][\w.+#-]*){1,4})"),
    re.compile(r"\b((?:[A-Z][\w.+#-]*\s+){1,4}Certification)\b"),
]
_GENERIC_CERT_START = {"Relevant", "Any", "Professional", "Industry", "The", "A", "Valid"}
LANGUAGES = ["english", "hindi", "malayalam", "tamil", "telugu", "kannada", "arabic", "french", "german"]
_LANGUAGE_CUE = re.compile(
    r"\b(language|languages|fluent|fluency|speak|spoken|verbal|written)\b", re.IGNORECASE)


def extract_certifications(text):
    """Return [{'name', 'required'}] for phrases like 'AWS Certified Solutions Architect'."""
    certs = {}
    for line in text.split("\n"):
        for pattern in _CERT_PATTERNS:
            for match in pattern.finditer(line):
                name = match.group(1).strip()
                if name.split()[0] not in _GENERIC_CERT_START:
                    certs.setdefault(name, not _PREFERRED_CUE.search(line))
    return [{"name": name, "required": required} for name, required in certs.items()]


def extract_languages(text):
    """Return spoken languages named on lines that talk about language skills."""
    found = []
    for line in text.split("\n"):
        if _LANGUAGE_CUE.search(line):
            found += [l.title() for l in LANGUAGES if re.search(r"\b" + l + r"\b", line, re.IGNORECASE)]
    return list(dict.fromkeys(found))


# ---------------------------------------------------------------- main entry points

def parse_job_description(text, job_id=None, company_id=None):
    """Parse raw JD text into a job dict that follows data/schemas/job_schema.json."""
    clean = normalize_jd_text(text)
    if not clean:
        raise ValueError("Job description text is empty")

    sections = split_jd_sections(clean)
    skills = extract_skills(sections)
    title = extract_title(clean)
    employment_type = extract_employment_type(clean, title)
    experience = extract_experience(clean, title, employment_type)
    canonical_role = normalize_role(title)

    job = {
        "schema_version": SCHEMA_VERSION,
        "job_id": job_id or "job_" + hashlib.sha1(clean.encode("utf-8")).hexdigest()[:8],
        "company_id": company_id or "comp_unknown",
        "title": title,
        "normalized_title": normalize_title(title),
        "department": None,
        "role_category": detect_role_category(canonical_role, title, skills),
        "employment_type": employment_type,
        "work_mode": extract_work_mode(clean),
        "location": extract_location(clean),
        "openings": extract_openings(clean),
        "description": sections.get("about"),
        "responsibilities": extract_responsibilities(sections),
        "requirements": {
            "skills": skills,
            "experience": experience,
            "education": extract_education(clean),
            "certifications": extract_certifications(clean),
            "languages": extract_languages(clean),
        },
        "status": "draft",
    }
    log.info("Parsed JD '%s': %d skills, %s-%s years", title, len(skills),
             experience["min_years"], experience["max_years"])
    return job


def build_ai_profile(job):
    """Flatten a parsed job into a small AI-friendly profile (for matching, search and prompts)."""
    req = job["requirements"]
    skills = req["skills"]
    must = [s["normalized_name"] for s in skills if s["importance"] == "must_have"]
    good = [s["normalized_name"] for s in skills if s["importance"] == "good_to_have"]
    exp, edu = req["experience"], req["education"]

    if exp["max_years"] is not None:
        years = f"{exp['min_years']}-{exp['max_years']} years"
    else:
        years = f"{exp['min_years']}+ years" if exp["min_years"] else "no prior experience required"
    role = job["normalized_title"] or job["title"]
    summary = f"{exp['level']} {role} ({job['role_category']}); experience: {years}."
    if must:
        summary += " Must have: " + ", ".join(must) + "."
    if good:
        summary += " Good to have: " + ", ".join(good) + "."
    if edu["min_level"]:
        summary += " Education: " + edu["min_level"] + (" in " + " / ".join(edu["preferred_fields"])
                                                       if edu["preferred_fields"] else "") + "."

    keywords = list(dict.fromkeys([role] + must + good + [f.lower() for f in edu["preferred_fields"]]))
    return {
        "job_id": job["job_id"],
        "title": job["title"],
        "normalized_title": job["normalized_title"],
        "role_category": job["role_category"],
        "level": exp["level"],
        "min_years": exp["min_years"],
        "max_years": exp["max_years"],
        "must_have_skills": must,
        "good_to_have_skills": good,
        "education_min_level": edu["min_level"],
        "preferred_fields": edu["preferred_fields"],
        "keywords": keywords,
        "summary": summary,
    }


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("Usage: python -m parsers.jd_parser <job_description.txt>")
        sys.exit(2)
    with open(sys.argv[1], encoding="utf-8") as f:
        parsed = parse_job_description(f.read())
    output = {"job": parsed, "ai_profile": build_ai_profile(parsed)}
    print(json.dumps(output, indent=2, ensure_ascii=False))
