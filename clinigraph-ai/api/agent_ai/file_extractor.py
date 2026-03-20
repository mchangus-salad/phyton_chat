"""
File text extractor for patient-case document uploads.

Supported formats: .txt, .pdf, .docx, .csv, .json

PDF and DOCX support requires optional libraries (pypdf, python-docx).
The module degrades gracefully and raises ValueError with install
instructions when those libraries are missing.
"""

from __future__ import annotations

import csv
import io
import json
import os

SUPPORTED_EXTENSIONS: frozenset[str] = frozenset(
    {".txt", ".pdf", ".docx", ".csv", ".json"}
)

# Hard cap — prevents runaway memory usage on huge uploads.
# The PHI de-identifier and LLM context window both benefit from a sane limit.
_MAX_CHARS = 100_000


def extract_text(filename: str, content: bytes) -> str:
    """
    Extract plain text from the raw bytes of an uploaded file.

    Args:
        filename: Original file name (used only to determine format).
        content:  Raw bytes of the file.

    Returns:
        Extracted text (at most ``_MAX_CHARS`` characters).

    Raises:
        ValueError: Unsupported file type, or extraction failure.
    """
    ext = os.path.splitext(filename)[1].lower()

    if ext == ".txt":
        return _read_text(content)
    elif ext == ".pdf":
        return _read_pdf(content)
    elif ext == ".docx":
        return _read_docx(content)
    elif ext == ".csv":
        return _read_csv(content)
    elif ext == ".json":
        return _read_json(content)
    else:
        raise ValueError(
            f"Unsupported file type '{ext}'. "
            f"Accepted: {', '.join(sorted(SUPPORTED_EXTENSIONS))}"
        )


# ── private helpers ───────────────────────────────────────────────────────────


def _truncate(text: str) -> str:
    if len(text) > _MAX_CHARS:
        return text[:_MAX_CHARS] + "\n\n[Document truncated at 100,000 characters]"
    return text


def _read_text(content: bytes) -> str:
    try:
        text = content.decode("utf-8")
    except UnicodeDecodeError:
        text = content.decode("latin-1", errors="replace")
    return _truncate(text.strip())


def _read_pdf(content: bytes) -> str:
    try:
        import pypdf  # type: ignore[import]
    except ImportError:
        try:
            import PyPDF2 as pypdf  # type: ignore[import, no-redef]
        except ImportError:
            raise ValueError(
                "PDF extraction requires the 'pypdf' package. "
                "Install it with: pip install pypdf"
            )

    reader = pypdf.PdfReader(io.BytesIO(content))
    parts: list[str] = []
    for page in reader.pages:
        page_text = page.extract_text() or ""
        if page_text.strip():
            parts.append(page_text.strip())

    if not parts:
        raise ValueError(
            "Could not extract any text from the PDF. "
            "The file may be scanned (image-only) or encrypted."
        )
    return _truncate("\n\n".join(parts))


def _read_docx(content: bytes) -> str:
    try:
        import docx  # type: ignore[import]
    except ImportError:
        raise ValueError(
            "DOCX extraction requires the 'python-docx' package. "
            "Install it with: pip install python-docx"
        )

    doc = docx.Document(io.BytesIO(content))
    parts: list[str] = [p.text.strip() for p in doc.paragraphs if p.text.strip()]

    if not parts:
        raise ValueError("Could not extract any text from the DOCX file.")
    return _truncate("\n".join(parts))


def _read_csv(content: bytes) -> str:
    try:
        decoded = content.decode("utf-8")
    except UnicodeDecodeError:
        decoded = content.decode("latin-1", errors="replace")

    reader = csv.reader(io.StringIO(decoded))
    rows = [", ".join(row) for row in reader if any(cell.strip() for cell in row)]
    return _truncate("\n".join(rows))


def _read_json(content: bytes) -> str:
    try:
        data = json.loads(content.decode("utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise ValueError(f"Invalid JSON file: {exc}") from exc
    return _truncate(json.dumps(data, indent=2, ensure_ascii=False))
