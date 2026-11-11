"""Reads text out of PDF resumes using pdfplumber.

Why this is tricky: a PDF is not a text file. It stores words at x/y
positions on a page, so the reading order has to be guessed. Two-column
resumes are the classic problem: a plain read mixes left and right columns
on the same line. We detect that case and read each column separately.
"""
import logging

import pdfplumber

logger = logging.getLogger("extraction")

MIN_WORDS_FOR_COLUMN_CHECK = 20   # too few words = not enough evidence
MIN_COLUMN_SHARE = 0.20           # each side needs at least 20% of the words


def _is_two_column(page):
    """True if the page has a clear empty gap down the middle."""
    words = page.extract_words()
    if len(words) < MIN_WORDS_FOR_COLUMN_CHECK:
        return False
    mid = page.width / 2
    band = page.width * 0.03      # empty strip around the middle
    left = right = crossing = 0
    for w in words:
        if w["x1"] <= mid - band:
            left += 1
        elif w["x0"] >= mid + band:
            right += 1
        else:
            crossing += 1         # word touches the middle strip
    total = len(words)
    return (
        crossing == 0
        and left / total >= MIN_COLUMN_SHARE
        and right / total >= MIN_COLUMN_SHARE
    )


def _read_page(page):
    """Read one page. Returns (text, was_two_column)."""
    if _is_two_column(page):
        mid = page.width / 2
        left = page.crop((0, 0, mid, page.height)).extract_text() or ""
        right = page.crop((mid, 0, page.width, page.height)).extract_text() or ""
        return left + "\n" + right, True
    return page.extract_text() or "", False


def read_pdf_details(path):
    """Read a PDF and return {"text", "page_count", "warnings"}.

    Table text is included automatically, because table cells are just
    positioned words and extract_text() returns them row by row.
    """
    warnings = []
    pages = []
    with pdfplumber.open(path) as pdf:
        page_count = len(pdf.pages)
        for number, page in enumerate(pdf.pages, start=1):
            text, two_col = _read_page(page)
            if two_col:
                msg = f"Page {number}: two-column layout detected, columns read separately"
                warnings.append(msg)
                logger.info(msg)
            pages.append(text)
    return {"text": "\n".join(pages), "page_count": page_count, "warnings": warnings}


def read_pdf(path):
    """Simple version: just return the raw text as one string."""
    return read_pdf_details(path)["text"]


if __name__ == "__main__":
    import sys
    print(read_pdf(sys.argv[1]))
