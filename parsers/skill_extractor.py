"""Skill extraction engine (Day 9): find every skill in a resume and describe it in a clean format.

Pipeline (each step is one small function):

    resume text
      1. segment_resume()        Day 8: tag every line with its section (skills, experience, ...)
      2. _make_units()           group wrapped lines into one bullet / sentence ("unit")
      3. _find_*_mentions()      entity recognition: find skill words in each unit
            - exact + synonym    "ReactJS", "Node", "Amazon Web Services"   -> canonical names
            - misspelling        "Pyhton", "Kubernates"                     -> known wrong spellings
            - fuzzy              "Postgresq1" in a skills list              -> closest known skill
            - ambiguous words    "Go", "R", "Excel", "Spring"               -> only with proof
            - stacks             "MERN", "MEAN"                             -> their component skills
      4. _merge()                deduplicate: all mentions of one skill become ONE record
      5. score_skill()           confidence per skill (parsers/skill_confidence.py)
      6. build output            sorted list + stacks + summary + warnings

Use it from code:
    from parsers.skill_extractor import extract_skills, extract_skills_from_file, to_schema_skills
    result = extract_skills(resume_text)
    for skill in result["skills"]:
        print(skill["normalized_name"], skill["confidence"], skill["confidence_label"])
    schema_skills = to_schema_skills(result)      # goes straight into resume_schema.json "skills"

Or from the command line:
    python -m parsers.skill_extractor data/raw_resumes/Maya.pdf
    python -m parsers.skill_extractor data/raw_resumes/Maya.pdf --json
"""
import argparse
import difflib
import json
import re
import sys
from pathlib import Path

from parsers import skill_taxonomy as tx
from parsers.jd_parser import detect_proficiency, find_years
from parsers.section_classifier import segment_resume
from parsers.skill_confidence import confidence_label, score_skill, score_stack
from utils.logger import get_logger

log = get_logger(__name__)

SCHEMA_VERSION = "1.0"
FUZZY_CUTOFF = 0.86          # how similar (0-1) a word must be to a known skill to count as a typo
FUZZY_MIN_LENGTH = 6         # short words are too risky to "correct" ("panda" is not "pandas")
EVIDENCE_LIMIT = 2           # how many example snippets are kept per skill
SNIPPET_LENGTH = 90

# resume section -> the "source" value allowed by resume_schema.json
SOURCE_BY_SECTION = {"skills": "skills_section", "experience": "experience",
                     "projects": "project", "certifications": "certification"}
SOURCE_ORDER = ["skills_section", "experience", "project", "certification"]
PROFICIENCY_ORDER = ["beginner", "intermediate", "advanced", "expert"]
_PROFICIENCY_WORDS = {"beginner": "beginner", "basic": "beginner", "familiar": "beginner",
                      "intermediate": "intermediate", "advanced": "advanced",
                      "proficient": "advanced", "expert": "expert"}

# ------------------------------------------------------------------ patterns (compiled once)

_BULLET_START = re.compile(r"^\s*(?:[-*•●▪■◦‣∙·○]+)\s+")
_MASK = re.compile(r"[\w.+-]+@[\w-]+\.[\w.]+"                       # e-mail
                   r"|(?:https?://|www\.)\S+"                       # web address
                   r"|\b(?:linkedin|github)\.com/\S*"               # profile link
                   r"|\+?\(?\d[\d\s().-]{7,}\d")                    # phone number
_ACTION = re.compile(
    r"\b(built|build|developed|develop|designed|implemented|created|deployed|automated|architected|"
    r"integrated|migrated|maintained|optimi[sz]ed|led|managed|wrote|written|using|used|utili[sz]ed|"
    r"leveraged|worked|engineered|configured|analy[sz]ed|tested|delivered|launched|improved|"
    r"coordinated|executed|conducted|administered|monitored|overhauled|scaled|refactored|set up)\b",
    re.IGNORECASE)
_LEARNING = re.compile(r"\b(learning|studying|exploring|interested in|want to learn|plan to learn|"
                       r"self-learning|currently learning)\b", re.IGNORECASE)
# "no experience with X", "not familiar with X", "without prior knowledge of X"
_NEGATION = re.compile(
    r"\b(?:no|not|without|never|lacks?|lacking|zero)\b\s+(?:\w+\s+){0,2}?"
    r"(?:experience|exposure|knowledge|familiarity|familiar|proficien\w*|skills?|background|expertise)\b"
    r"[^.;]{0,15}$", re.IGNORECASE)
_NEGATED_USE = re.compile(
    r"\b(?:did\s+not|didn't|never|have\s+not|haven't|has\s+not|hasn't)\s+(?:\w+\s+){0,1}?"
    r"(?:use|used|work|worked|touch|touched)\b[^.;]{0,15}$", re.IGNORECASE)
_PROFICIENCY_AFTER = re.compile(
    r"^\s*[\(\[\-–:,]\s*(beginner|basic|intermediate|advanced|expert|proficient|familiar)\b", re.IGNORECASE)
_YEARS_AFTER = re.compile(r"^\s*[\(\[\-–:,]?\s*(\d+(?:\.\d+)?)\s*\+?\s*(?:years?|yrs?)\b", re.IGNORECASE)
_SENTENCE_END = re.compile(r"[.;!?](?:\s|$)")
_FUZZY_TOKEN = re.compile(r"[A-Za-z][A-Za-z0-9]{%d,}" % (FUZZY_MIN_LENGTH - 1))

# English words that look like a skill name but are not skills (used only by the fuzzy step).
FUZZY_STOPWORDS = {
    "leaders", "leading", "leader", "teamwork", "managing", "manager", "analyst", "analysis",
    "marketing", "frontend", "backend", "database", "software", "hardware", "platform", "networking",
    "designer", "designing", "developer", "engineer", "testing", "reporting", "planning", "writing",
}


def _key(text):
    """Lookup key: lowercase, hyphens and repeated spaces count as one space."""
    return re.sub(r"[ -]+", " ", (text or "").strip().lower())


# ------------------------------------------------------------------ build the lookup tables

def _build_alias_index():
    """alias key -> (canonical skill, match_type). First definition wins."""
    index = {}
    for name, (_, aliases) in tx.SKILLS.items():
        index.setdefault(_key(name), (name, "exact"))
        for alias in aliases:
            index.setdefault(_key(alias), (name, "exact" if _key(alias) == _key(name) else "synonym"))
    for name, wrong_spellings in tx.MISSPELLINGS.items():
        for wrong in wrong_spellings:
            index.setdefault(_key(wrong), (name, "misspelling"))
    return index


def _alias_regex(keys, flags=re.IGNORECASE):
    """One regex for many aliases, longest first so 'react native' wins over 'react'."""
    ordered = sorted(keys, key=len, reverse=True)
    parts = ["[ \\-]+".join(re.escape(p) for p in key.split(" ")) for key in ordered]
    return re.compile(r"(?<![\w+#.])(" + "|".join(parts) + r")(?![\w+#]|\.\w)", flags)


_ALIAS_INDEX = _build_alias_index()
_TERM_RE = _alias_regex(_ALIAS_INDEX)
_AMBIGUOUS = tx.AMBIGUOUS
_EXCLUSIONS = {skill: [re.compile(p) for p in patterns] for skill, patterns in tx.CONTEXT_EXCLUSIONS.items()}

_FUZZY_TARGETS = {alias: info[0] for alias, info in _ALIAS_INDEX.items()
                  if len(alias) >= FUZZY_MIN_LENGTH and alias.isalnum() and alias not in _AMBIGUOUS}


def _build_stack_regexes():
    """Two regexes for stack names: one ignoring case, one that needs the exact capitals (MEAN)."""
    lookup, exact_lookup = {}, {}
    for stack, info in tx.STACKS.items():
        if stack not in info["exact_aliases"]:        # "MEAN"/"LAMP" are matched by exact capitals only
            lookup[_key(stack)] = stack
        for alias in info["aliases"]:
            lookup[_key(alias)] = stack
        for alias in info["exact_aliases"]:
            exact_lookup[alias] = stack
    loose = _alias_regex(lookup)
    strict = (re.compile(r"(?<![\w+#.])(" + "|".join(map(re.escape, exact_lookup)) + r")(?![\w+#.])")
              if exact_lookup else None)
    return loose, strict, lookup, exact_lookup


_STACK_RE, _STACK_EXACT_RE, _STACK_LOOKUP, _STACK_EXACT_LOOKUP = _build_stack_regexes()


# ------------------------------------------------------------------ step 2: units

def _mask(text):
    """Blank out e-mails, links and phone numbers so they can never be read as skills."""
    return _MASK.sub(lambda m: " " * len(m.group()), text)


def _is_listy(text, section):
    """True for 'Python, Java, SQL' style lines: many short items separated by commas or pipes."""
    body = re.sub(r"\([^)]*\)", "", text)
    body = re.sub(r"^[^:|]{1,40}[:|]\s*", "", body)
    if section == "skills" and len(body.split()) <= 4:
        return True
    items = [i.strip() for i in re.split(r"[,;|•/]\s*", body) if i.strip()]
    return len(items) >= 3 and sum(len(i.split()) for i in items) / len(items) <= 3.5


def _continues_skill_list(previous_text, text, section):
    """True when a short unlabelled line finishes a wrapped skills list ('..., Stakeholder' + 'Communication')."""
    return (section == "skills" and "," in previous_text and not previous_text.rstrip().endswith(".")
            and ":" not in text and "|" not in text and len(text.split()) <= 4)


def _make_units(line_tags):
    """Group wrapped lines into one 'unit' (a bullet or a line) so a sentence is not cut in half."""
    units = []
    for tag in line_tags:
        text = tag["text"].strip()
        if tag.get("is_heading"):
            inline = re.search(r"[:|]\s*(\S.*)$", text)     # "Skills: Python, SQL" keeps its content
            if not inline:
                continue
            text = inline.group(1)
        is_bullet = bool(_BULLET_START.match(text))
        text = _BULLET_START.sub("", text)
        if not text:
            continue
        previous = units[-1] if units else None
        wrapped = (not is_bullet and not tag.get("is_heading") and previous is not None
                   and previous["section"] == tag["section"]
                   and (tag.get("method") == "wrap" or text[:1].islower()
                        or _continues_skill_list(previous["text"], text, tag["section"])))
        if wrapped:
            previous["text"] += " " + text
        else:
            units.append({"id": len(units), "section": tag["section"], "text": text})
    for unit in units:
        unit["text"] = _mask(unit["text"])
        unit["in_list"] = _is_listy(unit["text"], unit["section"])
    return units


# ------------------------------------------------------------------ step 3: entity recognition

def _clause_spans(text):
    """Sentence-like pieces of a unit: [(start, end), ...]."""
    cuts = [0] + [m.end() for m in _SENTENCE_END.finditer(text)] + [len(text)]
    return [(a, b) for a, b in zip(cuts, cuts[1:]) if b > a]


def _clause_of(spans, position):
    for start, end in spans:
        if start <= position < end:
            return start, end
    return spans[-1]


def _has_word(text_lower, word):
    return re.search(r"(?<![\w])" + re.escape(word) + r"(?![\w])", text_lower) is not None


def _ambiguous_ok(info, surface, unit, next_to_skill):
    """A risky short word ("Go", "R", "Excel") is accepted only with proof:

    1. a cue word in the same bullet ("R programming", "Excel ... pivot"), or
    2. it is written exactly right ("Excel", not "excel") and it sits in a skills list, or
       in the middle of a sentence right beside a sure skill ("dashboards in Excel and Tableau").
    """
    lowered = unit["text"].lower()
    if any(_has_word(lowered, cue) for cue in info["cues"]):
        return True
    return surface == info["form"] and (unit["in_list"] or next_to_skill)


def _snippet(clause):
    clause = re.sub(r"\s+", " ", clause).strip()
    return clause if len(clause) <= SNIPPET_LENGTH else clause[:SNIPPET_LENGTH - 3].rstrip() + "..."


def _mention(unit, skill, surface, match_type, clause, **extra):
    """One mention record (the keys that skill_confidence.py expects)."""
    mention = {"skill": skill, "surface": surface, "section": unit["section"], "unit_id": unit["id"],
               "match_type": match_type, "similarity": 1.0, "in_list": unit["in_list"],
               "action": bool(_ACTION.search(clause)), "learning": bool(_LEARNING.search(clause)),
               "ambiguous": False, "proficiency": None, "years": None, "snippet": _snippet(clause)}
    mention.update(extra)
    return mention


def _find_exact_mentions(unit):
    """Exact names, synonyms, known misspellings and trusted ambiguous words."""
    text = unit["text"]
    spans = _clause_spans(text)
    all_matches = list(_TERM_RE.finditer(text))
    solid = {_clause_of(spans, m.start()) for m in all_matches if _key(m.group(1)) not in _AMBIGUOUS}
    raw = []
    for match in all_matches:
        surface = match.group(1)
        skill, match_type = _ALIAS_INDEX[_key(surface)]
        info = _AMBIGUOUS.get(_key(surface))
        start, end = _clause_of(spans, match.start())
        if info:
            mid_sentence = bool(text[start:match.start()].strip())   # not the first word of a sentence
            if not _ambiguous_ok(info, surface, unit, mid_sentence and (start, end) in solid):
                continue
        clause = text[start:end]
        before = text[start:match.start()]
        if _NEGATION.search(before) or _NEGATED_USE.search(before):   # "no experience with Java"
            continue
        if any(p.search(text[start:end].lower()) for p in _EXCLUSIONS.get(skill, [])):
            continue                                            # "(SQL)" = sales qualified lead
        raw.append((match, skill, surface, match_type, (start, end), clause, bool(info)))

    per_clause = {}
    for item in raw:
        per_clause[item[4]] = per_clause.get(item[4], 0) + 1
    mentions = []
    for match, skill, surface, match_type, bounds, clause, ambiguous in raw:
        after = text[match.end():match.end() + 25]
        level = _PROFICIENCY_AFTER.match(after)
        years = _YEARS_AFTER.match(after)
        proficiency = _PROFICIENCY_WORDS[level.group(1).lower()] if level else None
        years_used = float(years.group(1)) if years else None
        if per_clause[bounds] == 1 and tx.SKILLS[skill][0] != "soft_skill":   # one skill in the clause
            proficiency = proficiency or detect_proficiency(clause)
            if years_used is None:
                found = find_years(clause)
                years_used = float(found[0]) if found else None
        if years_used is not None and years_used.is_integer():
            years_used = int(years_used)
        mentions.append(_mention(unit, skill, surface, match_type, clause, ambiguous=ambiguous,
                                 proficiency=proficiency, years=years_used))
    return mentions, all_matches


def _find_fuzzy_mentions(unit, taken_spans):
    """Spelling variations we have never seen: only inside skills lists, only very close matches."""
    if not (unit["in_list"] or unit["section"] == "skills"):
        return []
    text = unit["text"]
    spans = _clause_spans(text)
    mentions = []
    for token in _FUZZY_TOKEN.finditer(text):
        word = token.group().lower()
        if word in FUZZY_STOPWORDS or word in _ALIAS_INDEX:
            continue
        if any(a < token.end() and token.start() < b for a, b in taken_spans):
            continue
        close = difflib.get_close_matches(word, _FUZZY_TARGETS, n=1, cutoff=FUZZY_CUTOFF)
        if not close or close[0][0] != word[0] or abs(len(close[0]) - len(word)) > 2:
            continue
        similarity = round(difflib.SequenceMatcher(None, word, close[0]).ratio(), 2)
        start, end = _clause_of(spans, token.start())
        mentions.append(_mention(unit, _FUZZY_TARGETS[close[0]], token.group(), "fuzzy",
                                 text[start:end], similarity=similarity))
    return mentions


def _find_stack_mentions(unit):
    """'MERN stack' -> (stack name, written text). Components are added later in _merge."""
    text = unit["text"]
    hits = [(m, _STACK_LOOKUP[_key(m.group(1))]) for m in _STACK_RE.finditer(text)]
    if _STACK_EXACT_RE:
        hits += [(m, _STACK_EXACT_LOOKUP[m.group(1)]) for m in _STACK_EXACT_RE.finditer(text)]
    return [{"stack": name, "surface": m.group(1), "section": unit["section"], "unit_id": unit["id"],
                          "snippet": _snippet(text)} for m, name in hits]


# ------------------------------------------------------------------ step 4: merge (deduplicate)

def _merge(units):
    """Collect every mention; one record per canonical skill (this is the deduplication)."""
    found, stack_hits = {}, []
    for unit in units:
        exact, spans = _find_exact_mentions(unit)
        taken = [m.span() for m in spans]
        for mention in exact + _find_fuzzy_mentions(unit, taken):
            found.setdefault(mention["skill"], []).append(mention)
        stack_hits.extend(_find_stack_mentions(unit))
    for hit in stack_hits:                                      # MERN -> mongodb, express, ...
        for skill in tx.STACKS[hit["stack"]]["components"]:
            unit = {"id": hit["unit_id"], "section": hit["section"], "in_list": True}
            found.setdefault(skill, []).append(
                _mention(unit, skill, hit["surface"], "stack", hit["snippet"]))
    return found, stack_hits


# ------------------------------------------------------------------ step 5/6: build the output

def _best(values, order):
    """Highest value of `values` according to `order` (a list from low to high), or None."""
    values = [v for v in values if v in order]
    return max(values, key=order.index) if values else None


def _build_skill(skill, mentions):
    """One output record for one canonical skill."""
    score, reasons = score_skill(mentions)
    real = [m for m in mentions if m["match_type"] != "stack"]
    pool = real or mentions
    sections = list(dict.fromkeys(m["section"] for m in pool))
    sources = [SOURCE_BY_SECTION[s] for s in sections if s in SOURCE_BY_SECTION] if real else []
    years = [m["years"] for m in pool if m["years"] is not None]
    seen, evidence = set(), []
    for m in pool:
        if m["snippet"] not in seen and len(evidence) < EVIDENCE_LIMIT:
            seen.add(m["snippet"])
            evidence.append(m["snippet"])
    match_types = {m["match_type"] for m in pool}
    category = tx.SKILLS[skill][0]
    label = confidence_label(score)
    return {
        "name": pool[0]["surface"],
        "normalized_name": skill,
        "category": category,
        "domain": tx.domain_of(skill),
        "proficiency": _best([m["proficiency"] for m in pool], PROFICIENCY_ORDER),
        "years_used": max(years) if years else None,
        "source": min(sources, key=SOURCE_ORDER.index) if sources else "inferred",
        "confidence": score,
        "confidence_label": label,
        "match_type": "stack" if not real else min(match_types, key=_match_rank),
        "mentions": len({m["unit_id"] for m in pool}),
        "sections": sections,
        "aliases_found": sorted({m["surface"] for m in pool}, key=str.lower),
        "evidence": evidence,
        "reasons": reasons,
        "needs_review": label == "low" or "fuzzy" in match_types,
    }


def _match_rank(match_type):
    return ["exact", "synonym", "misspelling", "fuzzy", "stack"].index(match_type)


def _build_stacks(stack_hits, skills):
    """Stacks written in the resume, plus stacks whose parts are all listed ('MERN' never written)."""
    stacks, seen = [], set()
    for hit in stack_hits:
        if hit["stack"] in seen:
            continue
        seen.add(hit["stack"])
        stacks.append({"name": hit["stack"], "found_as": hit["surface"],
                       "components": tx.STACKS[hit["stack"]]["components"],
                       "confidence": score_stack(hit["section"]),
                       "inferred_from_components": False})
    by_name = {s["normalized_name"]: s for s in skills if s["match_type"] != "stack"}
    for name, info in tx.STACKS.items():
        if name in seen or not all(c in by_name for c in info["components"]):
            continue
        weakest = min(by_name[c]["confidence"] for c in info["components"])
        stacks.append({"name": name, "found_as": None, "components": info["components"],
                       "confidence": round(weakest * 0.8, 2), "inferred_from_components": True})
    return sorted(stacks, key=lambda s: -s["confidence"])


def _summary(skills):
    def count(field):
        out = {}
        for s in skills:
            out[s[field]] = out.get(s[field], 0) + 1
        return dict(sorted(out.items()))
    return {"total": len(skills), "by_domain": count("domain"), "by_category": count("category"),
            "by_confidence": count("confidence_label"),
            "needs_review": sum(1 for s in skills if s["needs_review"])}


def extract_skills_from_segments(segmented):
    """Extract skills from the result of segment_resume() (Day 8). Returns the structured output."""
    units = _make_units(segmented.get("line_tags", []))
    found, stack_hits = _merge(units)
    skills = [_build_skill(skill, mentions) for skill, mentions in found.items()]
    skills.sort(key=lambda s: (-s["confidence"], s["normalized_name"]))
    stacks = _build_stacks(stack_hits, skills)

    warnings = []
    if not units:
        warnings.append("Empty text: no skills to extract.")
    else:
        if "skills" not in segmented.get("sections", {}):
            warnings.append("No skills section detected: skills come from other sections only.")
        if not skills:
            warnings.append("No skills found. Is the file scanned (needs OCR) or in an unusual language?")
    review = [s["normalized_name"] for s in skills if s["needs_review"]]
    if review:
        warnings.append(f"{len(review)} skill(s) need review (low confidence or spelling guessed).")
    summary = _summary(skills)
    log.info("Extracted %d skills (%s), %d stack(s)", len(skills),
             ", ".join(f"{k}={v}" for k, v in summary["by_confidence"].items()) or "none", len(stacks))
    return {"schema_version": SCHEMA_VERSION, "skills": skills, "stacks": stacks,
            "summary": summary, "warnings": warnings}


def extract_skills(text, mode="hybrid"):
    """Extract skills from plain resume text (segments it first, using Day 8)."""
    return extract_skills_from_segments(segment_resume(text or "", mode))


def extract_skills_from_file(path, mode="hybrid"):
    """Extract skills from a .pdf, .docx or .txt resume."""
    path = Path(path)
    if path.suffix.lower() == ".txt":
        result = extract_skills(path.read_text(encoding="utf-8"), mode)
        result["source_file"] = path.name
        return result
    from extraction.extractor import extract_resume      # pdfplumber is only needed for real files
    extracted = extract_resume(path, save=False)
    result = extract_skills(extracted["clean_text"], mode)
    result["source_file"] = extracted["source_file"]
    if extracted["needs_ocr"]:
        result["warnings"].append("File looks scanned (needs OCR): skill extraction is unreliable.")
    return result


def to_schema_skills(result, min_confidence=0.0):
    """Convert the result into the `skills` list of data/schemas/resume_schema.json."""
    return [{"name": s["name"], "normalized_name": s["normalized_name"], "category": s["category"],
             "proficiency": s["proficiency"], "years_used": s["years_used"], "source": s["source"],
             "confidence": s["confidence"]}
            for s in result["skills"] if s["confidence"] >= min_confidence]


# ------------------------------------------------------------------ command line

def main(argv=None):
    parser = argparse.ArgumentParser(description="Extract skills from a resume (.pdf/.docx/.txt).")
    parser.add_argument("path")
    parser.add_argument("--json", action="store_true", help="print the full result as JSON")
    args = parser.parse_args(argv)
    result = extract_skills_from_file(args.path)
    if args.json:
        print(json.dumps(result, indent=2, ensure_ascii=False))
        return 0
    print(f"{'SKILL':24}{'CATEGORY':22}{'CONF':>6}  {'LEVEL':8}FOUND IN")
    for s in result["skills"]:
        flag = "  <- review" if s["needs_review"] else ""
        print(f"{s['normalized_name']:24}{s['category']:22}{s['confidence']:>6}  "
              f"{s['confidence_label']:8}{', '.join(s['sections'])}{flag}")
    for stack in result["stacks"]:
        how = "implied by its parts" if stack["inferred_from_components"] else f"written as {stack['found_as']}"
        print(f"STACK {stack['name']}: {', '.join(stack['components'])} ({how}, conf {stack['confidence']})")
    for warning in result["warnings"]:
        print("WARNING:", warning)
    return 0


if __name__ == "__main__":
    sys.exit(main())
