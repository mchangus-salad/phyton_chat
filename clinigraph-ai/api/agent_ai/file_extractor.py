"""
File text extractor for patient-case document uploads.

Supported formats: .txt, .pdf, .docx, .csv, .json
Image formats:     .jpg, .jpeg, .png, .webp, .tiff, .tif, .bmp

PDF and DOCX support requires optional libraries (pypdf, python-docx).
Image OCR uses two strategies (configurable):
  - 'vision'  : OpenAI GPT-4o Vision API (rich clinical interpretation; requires OPENAI_API_KEY)
  - 'ocr'     : Local Tesseract via pytesseract (no data leaves the server; requires tesseract-ocr)
  - 'auto'    : tries Vision first, falls back to local OCR, then raises ValueError.

The module degrades gracefully and raises ValueError with install
instructions when those libraries are missing.
"""

from __future__ import annotations

import base64
import csv
import io
import json
import os

SUPPORTED_EXTENSIONS: frozenset[str] = frozenset(
    {".txt", ".pdf", ".docx", ".csv", ".json",
     ".jpg", ".jpeg", ".png", ".webp", ".tiff", ".tif", ".bmp"}
)

IMAGE_EXTENSIONS: frozenset[str] = frozenset(
    {".jpg", ".jpeg", ".png", ".webp", ".tiff", ".tif", ".bmp"}
)

# Hard cap — prevents runaway memory usage on huge uploads.
# The PHI de-identifier and LLM context window both benefit from a sane limit.
_MAX_CHARS = 100_000

# Image size cap (20 MB) — matches nginx mobile-gateway client_max_body_size.
_MAX_IMAGE_BYTES = 20 * 1024 * 1024


def extract_text(filename: str, content: bytes, image_strategy: str = "auto") -> str:
    """
    Extract plain text from the raw bytes of an uploaded file.

    Args:
        filename:        Original file name (used only to determine format).
        content:         Raw bytes of the file.
        image_strategy:  For image files: 'auto' | 'vision' | 'ocr'.
                         Ignored for non-image formats.

    Returns:
        Extracted text (at most ``_MAX_CHARS`` characters).

    Raises:
        ValueError: Unsupported file type, oversized image, or extraction failure.
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
    elif ext in IMAGE_EXTENSIONS:
        return _read_image(filename, content, strategy=image_strategy)
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


# ── Image extraction ──────────────────────────────────────────────────────────

_VISION_PROMPT = (
    "You are a medical document transcription assistant. "
    "Transcribe ALL visible text from this clinical image exactly as written, "
    "preserving line breaks and structure. "
    "If the image is a medical scan or diagnostic image (X-ray, CT, MRI, pathology slide), "
    "describe the visible clinical findings in plain text. "
    "Do not interpret, diagnose, or add information not present in the image."
)

_MIME_MAP: dict[str, str] = {
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".png": "image/png",
    ".webp": "image/webp",
    ".tiff": "image/tiff",
    ".tif": "image/tiff",
    ".bmp": "image/bmp",
}


def _read_image(filename: str, content: bytes, strategy: str = "auto") -> str:
    """
    Extract text from a clinical image using OCR or Vision AI.

    Strategy priority for 'auto':
      1. OpenAI GPT-4o Vision (if OPENAI_API_KEY is configured)
      2. Local pytesseract OCR (if tesseract-ocr is installed)
      3. Raise ValueError with setup instructions.

    All extracted text is returned as-is; PHI de-identification MUST be
    applied by the calling view before any further processing.

    Args:
        filename:  Original file name (for MIME type detection).
        content:   Raw image bytes.
        strategy:  'auto' | 'vision' | 'ocr'.

    Returns:
        Extracted / transcribed text string.

    Raises:
        ValueError: Image too large, extraction failed, no engine available.
    """
    if len(content) > _MAX_IMAGE_BYTES:
        raise ValueError(
            f"Image file is too large ({len(content) // (1024 * 1024)} MB). "
            "Maximum allowed size is 20 MB."
        )

    ext = os.path.splitext(filename)[1].lower()

    errors: list[str] = []

    if strategy in ("auto", "vision"):
        try:
            return _vision_api_extract(content, ext)
        except Exception as exc:
            errors.append(f"Vision API: {exc}")
            if strategy == "vision":
                raise ValueError(
                    f"Vision API extraction failed: {exc}. "
                    "Ensure OPENAI_API_KEY is set and the model has vision capability."
                ) from exc

    if strategy in ("auto", "ocr"):
        try:
            return _tesseract_extract(content)
        except Exception as exc:
            errors.append(f"Local OCR: {exc}")
            if strategy == "ocr":
                raise ValueError(
                    f"Local OCR extraction failed: {exc}. "
                    "Install tesseract-ocr and the 'pytesseract' Python package."
                ) from exc

    # Both failed or no engine is configured.
    raise ValueError(
        "No image extraction engine is available. "
        "Either set OPENAI_API_KEY for Vision API support, or install "
        "tesseract-ocr + pytesseract for local OCR. "
        f"Details: {'; '.join(errors)}"
    )


def _vision_api_extract(content: bytes, ext: str) -> str:
    """
    Use OpenAI GPT-4o Vision to transcribe or describe the image.

    Sends the image as a base64 data URL. Requires OPENAI_API_KEY.
    Only the transcription prompt and base64 image are sent — no patient
    metadata is transmitted beyond what is visible in the image pixels.
    """
    api_key = os.environ.get("OPENAI_API_KEY", "")
    if not api_key:
        raise RuntimeError("OPENAI_API_KEY is not set.")

    try:
        import openai  # type: ignore[import]
    except ImportError:
        raise RuntimeError(
            "The 'openai' package is required for Vision API extraction. "
            "Install it with: pip install openai"
        )

    mime = _MIME_MAP.get(ext, "image/jpeg")
    b64 = base64.b64encode(content).decode("ascii")
    data_url = f"data:{mime};base64,{b64}"

    client = openai.OpenAI(api_key=api_key)
    response = client.chat.completions.create(
        model=os.environ.get("OPENAI_VISION_MODEL", "gpt-4o"),
        messages=[
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": _VISION_PROMPT},
                    {"type": "image_url", "image_url": {"url": data_url, "detail": "high"}},
                ],
            }
        ],
        max_tokens=4096,
    )
    text = response.choices[0].message.content or ""
    if not text.strip():
        raise ValueError("Vision API returned an empty response.")
    return _truncate(text.strip())


def _tesseract_extract(content: bytes) -> str:
    """
    Use local Tesseract OCR (via pytesseract) to extract text from an image.

    No data leaves the server. Requires:
      - System package: tesseract-ocr (apt install tesseract-ocr)
      - Python package:  pytesseract + Pillow
    """
    try:
        import pytesseract  # type: ignore[import]
        from PIL import Image  # type: ignore[import]
    except ImportError:
        raise RuntimeError(
            "Local OCR requires 'pytesseract' and 'Pillow'. "
            "Install with: pip install pytesseract Pillow\n"
            "Also install the Tesseract binary: https://github.com/tesseract-ocr/tesseract"
        )

    image = Image.open(io.BytesIO(content))
    text = pytesseract.image_to_string(image, lang="eng")
    if not text.strip():
        raise ValueError(
            "Tesseract could not extract any text from the image. "
            "The image may be too low-resolution or contain only graphical content."
        )
    return _truncate(text.strip())
