"""Skill confidence scoring (Day 9).

Question answered here: "How sure are we that the candidate really has this skill?"

The score is built by simple ADDITION of clues, so every number can be explained to a recruiter.
Each clue also writes a short reason ("listed in skills section (+0.25)") that is saved with the
skill, so you can always see WHY a skill got its score.

    score = how well the word matched          (MATCH_BASE)
          + where it was found                 (SECTION_BONUS)
          + found in more than one section     (+0.10 per extra section, max +0.15)
          + mentioned again and again          (+0.03 per repeat, max +0.06)
          + used in a sentence about real work (+0.10)
          + a level or years was given         (+0.05)
          - "learning X" / "interested in X"   (-0.20)
          - risky short word like "Go" or "R"  (-0.05)

The result is kept between 0.05 and 0.99 and given a label: high / medium / low.
All the numbers are constants at the top, so the team can tune them in one place.

This module has no regex or NLP in it: it only does arithmetic on "mention" dicts that
parsers/skill_extractor.py builds. That makes it easy to read and to unit test.

A mention is a dict with these keys:
    section      section the word was found in (skills, experience, ...)
    match_type   exact | synonym | misspelling | fuzzy | stack
    unit_id      which bullet/line it came from (to count repeats)
    action       True if the sentence describes doing work ("built ... using Python")
    learning     True if the sentence says the person is only learning it
    ambiguous    True if the word is also normal English ("Go", "R")
    proficiency  'beginner' / ... / None
    years        number or None
"""

# How trustworthy the way of matching is. A skill written correctly beats a guessed spelling.
MATCH_BASE = {
    "exact": 0.50,        # the skill's own name: "python"
    "synonym": 0.45,      # a known other name: "reactjs" -> react
    "misspelling": 0.40,  # a known wrong spelling: "pyhton" -> python
    "fuzzy": 0.30,        # an unknown spelling that is very close: "postgresq1"
    "stack": 0.30,        # not written at all, implied by a stack name: MERN -> react
}

# Where the word was found. Real work and a skills list are stronger evidence than a summary line.
SECTION_BONUS = {
    "skills": 0.25,
    "experience": 0.20,
    "certifications": 0.20,
    "projects": 0.15,
    "summary": 0.10,
    "education": 0.05,
    "other": 0.05,
    "header": 0.05,
}

EXTRA_SECTION_BONUS = 0.10     # per additional section that also mentions the skill
EXTRA_SECTION_MAX = 0.15
REPEAT_BONUS = 0.03            # per additional bullet/line that mentions the skill
REPEAT_MAX = 0.06
ACTION_BONUS = 0.10            # "Built an API using Python"  (only in experience/projects/certs)
DETAIL_BONUS = 0.05            # "Python (3 years)", "advanced SQL", "Skilled in AWS"
LEARNING_PENALTY = 0.20
AMBIGUOUS_PENALTY = 0.05

MIN_SCORE = 0.05
MAX_SCORE = 0.99               # never 1.0: a text parser is never 100% sure

HIGH = 0.85
MEDIUM = 0.65

ACTION_SECTIONS = {"experience", "projects", "certifications"}


def confidence_label(score):
    """Turn a number into 'high' (>= 0.85), 'medium' (>= 0.65) or 'low'."""
    if score >= HIGH:
        return "high"
    if score >= MEDIUM:
        return "medium"
    return "low"


def _best_section(mentions):
    """The section with the biggest bonus among these mentions."""
    return max((m["section"] for m in mentions), key=lambda s: SECTION_BONUS.get(s, 0.05))


def score_skill(mentions):
    """Score one skill from all of its mentions. Returns (score, reasons).

    If the skill was written in the resume at all, only those real mentions count.
    If it was only implied by a stack name (MERN), the score stays low on purpose.
    """
    real = [m for m in mentions if m["match_type"] != "stack"]
    if not real:                                    # implied by a stack only
        section = _best_section(mentions)
        score = MATCH_BASE["stack"] + SECTION_BONUS.get(section, 0.05) / 2
        reason = f"implied by a stack name in the {section} section (+{score:.2f})"
        return round(min(score, MAX_SCORE), 2), [reason]

    reasons = []
    best_match = max((m["match_type"] for m in real), key=lambda t: MATCH_BASE[t])
    score = MATCH_BASE[best_match]
    reasons.append(f"{best_match} match (+{score:.2f})")

    sections = sorted({m["section"] for m in real}, key=lambda s: -SECTION_BONUS.get(s, 0.05))
    top = sections[0]
    score += SECTION_BONUS.get(top, 0.05)
    reasons.append(f"found in {top} section (+{SECTION_BONUS.get(top, 0.05):.2f})")

    if len(sections) > 1:
        extra = min(EXTRA_SECTION_BONUS * (len(sections) - 1), EXTRA_SECTION_MAX)
        score += extra
        reasons.append(f"also in {len(sections) - 1} other section(s) (+{extra:.2f})")

    units = {m["unit_id"] for m in real}
    if len(units) > 1:
        repeat = min(REPEAT_BONUS * (len(units) - 1), REPEAT_MAX)
        score += repeat
        reasons.append(f"mentioned {len(units)} times (+{repeat:.2f})")

    if any(m["action"] and m["section"] in ACTION_SECTIONS for m in real):
        score += ACTION_BONUS
        reasons.append(f"used in a work sentence (+{ACTION_BONUS:.2f})")

    if any(m["proficiency"] or m["years"] for m in real):
        score += DETAIL_BONUS
        reasons.append(f"level or years given (+{DETAIL_BONUS:.2f})")

    if all(m["learning"] for m in real):
        score -= LEARNING_PENALTY
        reasons.append(f"only 'learning/interested' wording (-{LEARNING_PENALTY:.2f})")

    if all(m["ambiguous"] for m in real):
        score -= AMBIGUOUS_PENALTY
        reasons.append(f"short word that is also normal English (-{AMBIGUOUS_PENALTY:.2f})")

    return round(max(MIN_SCORE, min(score, MAX_SCORE)), 2), reasons


STACK_BASE = 0.55


def score_stack(section):
    """Confidence that the candidate really names this stack (e.g. 'MERN'): base + section bonus."""
    return round(min(STACK_BASE + SECTION_BONUS.get(section, 0.05), MAX_SCORE), 2)
