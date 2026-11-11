"""Makes text consistent: bullets, section headings and capitalization."""
import re

# canonical heading -> all the ways resumes write it
HEADINGS = {
    "skills": ["skills", "technical skills", "key skills", "core competencies"],
    "experience": ["experience", "work experience", "employment history",
                   "professional experience", "work history"],
    "education": ["education", "academic background", "academic qualifications"],
    "projects": ["projects", "personal projects", "academic projects"],
    "certifications": ["certifications", "courses", "certificates"],
    "summary": ["summary", "profile", "objective", "professional summary",
                "career objective", "about me"],
}

# reverse lookup: "work experience" -> "experience"
_LOOKUP = {alias: key for key, aliases in HEADINGS.items() for alias in aliases}

# Symbol bullets (no space needed after them)
_SYMBOL_BULLET = re.compile(r"^[ \t]*[\u2022\u25cf\u25aa\u25a0\u25e6\u2023\u2219\u00b7\u25cb]+[ \t]*")
# '-' and '*' only count as bullets when followed by a space
_DASH_BULLET = re.compile(r"^[ \t]*[-*][ \t]+")


def normalize_bullets(text):
    """Convert every bullet style to '- '."""
    out = []
    for line in text.split("\n"):
        new = _SYMBOL_BULLET.sub("- ", line, count=1)
        if new == line:
            new = _DASH_BULLET.sub("- ", line, count=1)
        out.append(new)
    return "\n".join(out)


def detect_heading(line):
    """Return the canonical heading key (e.g. 'experience') or None."""
    s = line.strip().rstrip(":").strip()
    if not s or len(s) > 40:
        return None
    key = re.sub(r"[^a-z ]", "", s.lower())
    key = re.sub(r"\s+", " ", key).strip()
    return _LOOKUP.get(key)


def normalize_headings(text):
    """Rewrite heading lines uniformly: 'WORK EXPERIENCE:' -> 'Experience'."""
    out = []
    for line in text.split("\n"):
        key = detect_heading(line)
        out.append(key.title() if key else line)
    return "\n".join(out)


def split_sections(text):
    """Split normalized text into {'skills': '...', 'experience': '...'}.

    Text before the first heading (name, contact details) goes in 'header'.
    """
    sections = {}
    current = "header"
    buffer = []

    def flush():
        body = "\n".join(buffer).strip()
        if body:
            sections[current] = (sections[current] + "\n" + body) if current in sections else body

    for line in text.split("\n"):
        key = detect_heading(line)
        if key:
            flush()
            current, buffer = key, []
        else:
            buffer.append(line)
    flush()
    return sections


def normalize(text):
    """Full normalization. Returns (normalized_text, sections_dict)."""
    text = normalize_bullets(text)
    text = normalize_headings(text)
    return text, split_sections(text)
