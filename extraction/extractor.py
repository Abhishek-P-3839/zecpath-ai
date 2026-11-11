"""Main entry point: extract_resume(path) -> dict.

Run from the project root:
    python -m extraction.extractor data/raw_resumes/sample.pdf
    python -m extraction.extractor data/raw_resumes        (a whole folder)
"""
import argparse
import json
import logging
import sys
from pathlib import Path

from extraction.cleaner import clean_text
from extraction.docx_reader import read_docx_details
from extraction.normalizer import normalize
from extraction.pdf_reader import read_pdf_details

logger = logging.getLogger("extraction")

PROJECT_ROOT = Path(__file__).resolve().parent.parent
OUTPUT_DIR = PROJECT_ROOT / "data" / "extracted"
SUPPORTED = {".pdf": read_pdf_details, ".docx": read_docx_details}
MIN_CHARS_PER_PAGE = 30   # less than this = probably a scanned/image resume


class UnsupportedFileError(ValueError):
    """Raised when the file type is not PDF or DOCX."""


def extract_resume(path, output_dir=OUTPUT_DIR, save=True):
    """Extract, clean and normalize one resume. Returns the result dict.

    Raises:
        FileNotFoundError: the path does not exist.
        UnsupportedFileError: the file is not a .pdf or .docx.
    A corrupt or empty file does NOT raise: it returns status 'failed'
    with a warning, so one bad file never crashes a batch.
    """
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(f"File not found: {path}")
    ext = path.suffix.lower()
    if ext not in SUPPORTED:
        raise UnsupportedFileError(
            f"Unsupported file type '{ext}'. Only .pdf and .docx are supported."
        )

    result = {
        "source_file": path.name,
        "file_type": ext.lstrip("."),
        "page_count": None,
        "char_count": 0,
        "needs_ocr": False,
        "warnings": [],
        "status": "ok",
        "sections": {},
        "clean_text": "",
    }

    try:
        raw = SUPPORTED[ext](path)
    except Exception as exc:  # corrupt, empty, password-protected...
        msg = f"Could not read file: {type(exc).__name__}: {exc}"
        logger.warning("%s (%s)", msg, path.name)
        result["status"] = "failed"
        result["warnings"].append(msg)
    else:
        result["page_count"] = raw["page_count"]
        result["warnings"].extend(raw["warnings"])
        cleaned = clean_text(raw["text"])
        normalized, sections = normalize(cleaned)
        result["clean_text"] = normalized
        result["sections"] = sections
        result["char_count"] = len(normalized)

        pages = result["page_count"] or 1
        if len(normalized) < MIN_CHARS_PER_PAGE * pages:
            result["needs_ocr"] = True
            msg = "Very little text found: file may be scanned/image-only. OCR needed."
            result["warnings"].append(msg)
            logger.warning("%s (%s)", msg, path.name)

    if save:
        _save(result, Path(output_dir), path.stem)
    return result


def _save(result, output_dir, name):
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / f"{name}.txt").write_text(result["clean_text"], encoding="utf-8")
    (output_dir / f"{name}.json").write_text(
        json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8"
    )


def main(argv=None):
    parser = argparse.ArgumentParser(description="Extract clean text from resumes.")
    parser.add_argument("path", help="a .pdf/.docx file, or a folder of them")
    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")

    target = Path(args.path)
    files = sorted(p for p in target.iterdir() if p.suffix.lower() in SUPPORTED) \
        if target.is_dir() else [target]
    if not files:
        print("No .pdf or .docx files found.")
        return 1

    code = 0
    for f in files:
        try:
            r = extract_resume(f)
        except (FileNotFoundError, UnsupportedFileError) as exc:
            print(f"ERROR {f.name}: {exc}")
            code = 1
            continue
        flag = " [NEEDS OCR]" if r["needs_ocr"] else ""
        print(f"{r['status'].upper():7} {f.name}: {r['char_count']} chars, "
              f"sections={list(r['sections'])}{flag}")
    return code


if __name__ == "__main__":
    sys.exit(main())
