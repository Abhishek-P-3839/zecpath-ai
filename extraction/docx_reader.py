"""Reads text out of DOCX resumes using python-docx.

In a DOCX, paragraphs and tables are different kinds of objects, so we walk
the document body in order and handle each kind.
"""
from docx import Document
from docx.table import Table
from docx.text.paragraph import Paragraph


def _table_to_lines(table):
    lines = []
    for row in table.rows:
        cells = []
        for cell in row.cells:
            text = cell.text.strip()
            # merged cells repeat the same text, so skip consecutive duplicates
            if text and (not cells or cells[-1] != text):
                cells.append(text)
        if cells:
            lines.append(" | ".join(cells))
    return lines


def read_docx_details(path):
    """Read a DOCX and return {"text", "page_count", "warnings"}."""
    doc = Document(path)
    lines = []
    for child in doc.element.body.iterchildren():
        if child.tag.endswith("}p"):
            lines.append(Paragraph(child, doc).text)
        elif child.tag.endswith("}tbl"):
            lines.extend(_table_to_lines(Table(child, doc)))
    # DOCX files do not store a reliable page count, so we leave it as None
    return {"text": "\n".join(lines), "page_count": None, "warnings": []}


def read_docx(path):
    """Simple version: just return the raw text as one string."""
    return read_docx_details(path)["text"]


if __name__ == "__main__":
    import sys
    print(read_docx(sys.argv[1]))
