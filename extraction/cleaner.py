"""Removes noise from raw extracted text, using regular expressions (re)."""
import re

# Invisible characters that PDFs/Word files often contain
ZERO_WIDTH = re.compile(r"[\u200b\u200c\u200d\u2060\ufeff\u00ad]")
# Control characters except newline (\n) and tab (\t)
CONTROL_CHARS = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")
# "Page 1 of 2", "Page 1", "- 2 -" on a line of their own
PAGE_NUMBER = re.compile(
    r"^\s*(?:page\s+\d+(?:\s*(?:of|/)\s*\d+)?|-\s*\d+\s*-)\s*$",
    re.IGNORECASE | re.MULTILINE,
)
# a word split by a hyphen at the end of a line:  "develop-\nment"
HYPHEN_BREAK = re.compile(r"([A-Za-z])-\n\s*([a-z])")

# Fancy characters -> plain ones
REPLACEMENTS = {
    "\u00a0": " ",    # non-breaking space
    "\u2018": "'", "\u2019": "'",
    "\u201c": '"', "\u201d": '"',
    "\u2013": "-", "\u2014": "-",
    "\u2026": "...",
    "\uf0b7": "\u2022", "\uf0a7": "\u2022", "\uf076": "\u2022",  # Word bullet glyphs
    "\ufffd": "",     # broken-character marker
}


def clean_text(text):
    """Return cleaned text. Safe to call with None or an empty string."""
    if not text:
        return ""
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    for old, new in REPLACEMENTS.items():
        text = text.replace(old, new)
    text = ZERO_WIDTH.sub("", text)
    text = CONTROL_CHARS.sub("", text)
    text = HYPHEN_BREAK.sub(r"\1\2", text)           # join split words
    text = PAGE_NUMBER.sub("", text)                 # drop page-number lines
    text = re.sub(r"[ \t]+", " ", text)              # collapse spaces/tabs
    text = re.sub(r" *\n *", "\n", text)             # trim around newlines
    text = re.sub(r"\n{3,}", "\n\n", text)           # max one blank line
    return text.strip()
