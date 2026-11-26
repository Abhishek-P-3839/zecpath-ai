"""Knowledge base for the resume section classifier (Day 8).

Everything here is plain Python data, so it is easy to extend:
    SECTIONS          the labels the classifier can output
    HEADING_ALIASES   all the ways a resume may write each section heading
    INLINE_SAFE       sections that may appear as "Skills: Python, SQL" on one line
    *_WORDS / *_RE    keyword lists and patterns used by the NLP (content) scorer

To teach the classifier a new heading or keyword, add it here. No other code changes.
"""
import re

# The labels we can output. "header" = name + contact details, "other" = anything else.
SECTIONS = ["header", "summary", "skills", "experience", "education",
            "certifications", "projects", "other"]

# label -> every heading text we recognise (lowercase, letters and spaces only).
HEADING_ALIASES = {
    "summary": [
        "summary", "profile", "objective", "professional summary", "career summary",
        "career objective", "about me", "about", "professional profile",
        "personal statement", "executive summary", "profile summary",
    ],
    "skills": [
        "skills", "technical skills", "key skills", "core skills", "core competencies",
        "skill set", "skillset", "technical proficiency", "technical expertise",
        "areas of expertise", "expertise", "competencies", "technologies",
        "tech stack", "tools", "tools and technologies", "technical summary",
        "professional skills", "it skills", "soft skills", "skills summary",
    ],
    "experience": [
        "experience", "work experience", "professional experience", "employment history",
        "work history", "employment", "career history", "relevant experience",
        "internships", "internship experience", "industry experience",
        "professional background", "experience summary", "work experience summary",
    ],
    "education": [
        "education", "academic background", "academic qualifications", "qualifications",
        "educational qualifications", "academics", "education and training",
        "academic profile", "educational background", "scholastic record",
        "academic credentials",
    ],
    "certifications": [
        "certifications", "certification", "certificates", "certificate", "courses",
        "licenses", "licences", "licenses and certifications", "training",
        "trainings", "professional certifications", "courses and certifications",
        "training and certifications", "online courses", "accreditations",
    ],
    "projects": [
        "projects", "project", "personal projects", "academic projects",
        "key projects", "selected projects", "project experience", "project work",
        "major projects", "side projects", "portfolio",
    ],
    "other": [
        "languages", "interests", "hobbies", "hobbies and interests", "awards",
        "achievements", "awards and honors", "honors", "publications",
        "references", "declaration", "volunteering", "volunteer experience",
        "extracurricular activities", "activities", "personal details",
        "personal information", "additional information", "strengths",
        "leadership and activities", "languages known",
    ],
}

# Only these can be written as "Label: content" on the same line.
# ("experience" is left out because "Experience: 5 years" is usually a summary line.)
INLINE_SAFE = {"skills", "education", "certifications", "projects", "summary"}

# Sub-labels that may be a heading on their own line, but must NOT switch the section when
# written inline: "Tech stack: React, Node" inside a project is still part of the project.
INLINE_BLOCKED = {"tech stack", "tools", "technologies", "tools and technologies",
                  "technical summary", "skills summary"}

# ------------------------------------------------------------------ content words

CONTACT_EMAIL_RE = re.compile(r"[\w.+-]+@[\w-]+\.[\w.]+")
CONTACT_PHONE_RE = re.compile(r"(?<!\d)(?:\+?\d{1,3}[\s-]?)?(?:\(\d{3}\)\s?|\d{3,5}[\s.-]?)\d{3,5}(?:[\s.-]?\d{3,5})?(?!\d)")  # also check >= 9 digits
CONTACT_URL_RE = re.compile(r"(?:https?://|www\.|linkedin\.com|github\.com|gitlab\.com|behance\.net)", re.I)
CITY_STATE_RE = re.compile(r"\b[A-Z][a-z]+(?: [A-Z][a-z]+)?, ?(?:[A-Z]{2}\b|[A-Z][a-z]+)")

MONTH = r"(?:jan|feb|mar|apr|may|jun|jul|aug|sep|sept|oct|nov|dec)[a-z]*\.?"
# "January 2023 - Present", "Jun 2020 - Dec 2022", "2019 - 2021", "2021 - present"
DATE_RANGE_RE = re.compile(
    rf"(?:{MONTH}\s+)?(?:19|20)\d\d\s*(?:-|to)\s*(?:(?:{MONTH}\s+)?(?:19|20)\d\d|present|current|till date|now)",
    re.I,
)
YEAR_RE = re.compile(r"\b(?:19|20)\d\d\b")

ACTION_VERBS = {
    "led", "built", "managed", "developed", "designed", "implemented", "created",
    "automated", "reduced", "increased", "improved", "coordinated", "analyzed",
    "analysed", "trained", "mentored", "architected", "collaborated", "deployed",
    "integrated", "executed", "conducted", "overhauled", "launched", "optimized",
    "optimised", "delivered", "maintained", "wrote", "fixed", "drove", "spearheaded",
    "responsible", "worked", "handled", "supported", "established", "streamlined",
    "organized", "organised", "prepared", "planned", "monitored", "performed",
    "generated", "migrated", "tested", "configured", "owned", "resolved", "supervised",
    "negotiated", "reviewed", "assisted", "participated", "contributed", "engineered",
    "lowered", "grew", "lifted", "saved", "cut", "boosted", "onboarded", "redesigned",
}

JOB_TITLE_WORDS = {
    "engineer", "developer", "manager", "analyst", "intern", "coordinator",
    "specialist", "consultant", "lead", "architect", "administrator", "executive",
    "associate", "director", "trainee", "officer", "designer", "scientist",
    "assistant", "supervisor", "head", "programmer", "tester", "recruiter",
    "accountant", "technician", "representative", "strategist", "founder",
}

COMPANY_WORDS = {
    "pvt", "ltd", "inc", "llc", "llp", "corp", "corporation", "technologies",
    "technology", "solutions", "systems", "company", "group", "labs", "services",
    "consulting", "agency", "logistics", "software", "infotech", "enterprises",
    "limited", "studio", "studios", "bank", "industries", "media",
}

# Long degree names: safe to match in any letter case.
DEGREE_RE = re.compile(
    r"\b(?:b\.?\s?tech|m\.?\s?tech|b\.?\s?sc|m\.?\s?sc|b\.?\s?com|m\.?\s?com|mba|bba|bca|mca|"
    r"ph\.?\s?d|(?:bachelor|master)(?:'?s)?\s+(?:of|in|degree)|diploma|associate degree|"
    r"high school|hsc|ssc|intermediate|cbse|icse|class (?:x|xii|10|12)|senior secondary|"
    r"undergraduate|postgraduate)\b",
    re.I,
)
# Short degree names (BE, BA, MS ...) must be UPPERCASE, or we would match the word "be".
DEGREE_SHORT_RE = re.compile(r"\b(?:B\.?E\.?|M\.?E\.?|B\.?A\.?|M\.?A\.?|B\.?S\.?|M\.?S\.?)(?=[\s,.)]|$)")
EDU_PLACE_WORDS = {"university", "college", "institute", "school", "academy", "iit", "nit", "polytechnic", "board"}
EDU_WORDS = {"gpa", "cgpa", "graduated", "graduation", "coursework", "major", "minor",
             "percentage", "grade", "marks", "semester", "dissertation", "thesis", "honours", "honors"}

CERT_WORDS = {"certified", "certification", "certifications", "certificate", "license",
              "licence", "credential", "accredited", "nanodegree", "specialization"}
CERT_PROVIDERS = {"coursera", "udemy", "edx", "nptel", "udacity", "pluralsight",
                  "comptia", "cisco", "pmi", "scrum alliance", "linkedin learning", "hackerrank"}
CERT_CODE_RE = re.compile(r"\b(?:AZ-\d{3}|PMP|CSM|CCNA|CISSP|OCJP|CKA|CKAD|SAA-C\d+|PSM)\b")

PROJECT_WORDS = {"project", "projects", "clone", "application", "app", "portal", "system",
                 "platform", "chatbot", "website", "dashboard", "tracker", "game",
                 "prototype", "bot", "extension", "api", "tool", "engine", "generator",
                 "classifier", "recommender", "recommendation", "detection", "prediction",
                 "scraper", "simulator", "converter", "calculator", "planner", "analyzer"}
PROJECT_MARKERS = ("tech stack", "technologies used", "built with", "tools used",
                   "stack:", "live demo", "source code", "github", "repo", "deployed at")

SUMMARY_PHRASES = (
    "years of experience", "results-driven", "results driven", "detail-oriented",
    "detail oriented", "motivated", "passionate", "seeking", "looking for", "proven track record",
    "dedicated", "adept", "skilled in", "experienced", "professional with", "aspiring",
    "fresher", "eager", "hardworking", "hard-working", "enthusiastic", "self-starter",
    "to leverage", "to contribute", "strong background", "expertise in", "with a passion",
    "years' experience", "seasoned", "driven",
)

OTHER_PHRASES = ("hobbies", "interests", "languages known", "i hereby declare", "declaration",
                 "references available", "date of birth", "marital status", "nationality",
                 "father's name", "available on request", "volunteer", "award", "publication")
