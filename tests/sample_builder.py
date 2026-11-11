"""Builds small DUMMY resumes (PDF + DOCX) with no extra libraries.

Used by the tests, and also to create sample files for data/raw_resumes:
    python -m tests.sample_builder
"""
from pathlib import Path

from docx import Document


def _esc(text):
    return text.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")


def build_pdf(path, pages):
    """pages = list of pages; each page = list of (x, y, text).
    A page with an empty list is a blank page (like a scanned resume)."""
    n = len(pages)
    page_ids = [4 + 2 * i for i in range(n)]
    objs = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        f"<< /Type /Pages /Kids [{' '.join(f'{i} 0 R' for i in page_ids)}] /Count {n} >>".encode(),
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
    ]
    for i, items in enumerate(pages):
        objs.append(
            f"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] "
            f"/Contents {page_ids[i] + 1} 0 R "
            f"/Resources << /Font << /F1 3 0 R >> >> >>".encode()
        )
        stream = "BT\n/F1 11 Tf\n" + "".join(
            f"1 0 0 1 {x} {y} Tm ({_esc(t)}) Tj\n" for x, y, t in items
        ) + "ET"
        data = stream.encode("latin-1")
        objs.append(b"<< /Length %d >>\nstream\n" % len(data) + data + b"\nendstream")

    out = bytearray(b"%PDF-1.4\n")
    offsets = []
    for num, body in enumerate(objs, start=1):
        offsets.append(len(out))
        out += f"{num} 0 obj\n".encode() + body + b"\nendobj\n"
    xref = len(out)
    out += f"xref\n0 {len(objs) + 1}\n0000000000 65535 f \n".encode()
    for off in offsets:
        out += f"{off:010d} 00000 n \n".encode()
    out += (f"trailer\n<< /Size {len(objs) + 1} /Root 1 0 R >>\n"
            f"startxref\n{xref}\n%%EOF\n").encode()
    Path(path).write_bytes(bytes(out))


def single_column(lines):
    return [(50, 740 - 16 * i, t) for i, t in enumerate(lines)]


def two_column(left, right):
    return ([(50, 740 - 16 * i, t) for i, t in enumerate(left)]
            + [(330, 740 - 16 * i, t) for i, t in enumerate(right)])


SIMPLE_LINES = [
    "Rahul Kumar", "rahul@example.com | 99999 00000", "",
    "PROFILE:", "Fresher Python developer.", "",
    "TECHNICAL SKILLS", "Python, SQL, Git", "",
    "Work Experience", "Intern at Demo Corp", "Page 1 of 1",
]
LEFT = ["Skills", "Python and SQL", "Git and Linux", "React basics", "Django REST",
        "Education", "B.Tech Computer Science", "Demo University 2025"]
RIGHT = ["Experience", "Intern at Demo Corp", "Built small REST APIs", "Fixed many bugs",
         "Projects", "Resume parser project", "Job portal clone", "Chat application"]


def build_docx(path):
    doc = Document()
    doc.add_paragraph("Priya Nair")
    doc.add_paragraph("EXPERIENCE")
    doc.add_paragraph("\u2022 Built REST APIs with Flask")
    doc.add_paragraph("\u25cf Wrote unit tests")
    doc.add_paragraph("* Deployed on AWS")
    doc.add_paragraph("EDUCATION:")
    table = doc.add_table(rows=2, cols=2)
    table.rows[0].cells[0].text = "Degree"
    table.rows[0].cells[1].text = "University"
    table.rows[1].cells[0].text = "B.Sc Computer Science"
    table.rows[1].cells[1].text = "Kerala University"
    doc.save(str(path))


def build_all(folder):
    folder = Path(folder)
    folder.mkdir(parents=True, exist_ok=True)
    build_pdf(folder / "sample_simple.pdf", [single_column(SIMPLE_LINES)])
    build_pdf(folder / "sample_two_column.pdf", [two_column(LEFT, RIGHT)])
    build_pdf(folder / "sample_scanned.pdf", [[]])   # no text = like a scan
    build_docx(folder / "sample_bullets_table.docx")


if __name__ == "__main__":
    build_all(Path(__file__).resolve().parent.parent / "data" / "raw_resumes")
    print("Sample resumes created in data/raw_resumes")
