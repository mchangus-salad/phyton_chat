import csv
import json
from pathlib import Path


def load_oncology_corpus(file_path: str) -> list[dict]:
    path = Path(file_path)
    suffix = path.suffix.lower()

    if suffix == ".json":
        return _load_json(path)
    if suffix == ".csv":
        return _load_csv(path)
    if suffix == ".txt":
        return _load_txt(path)

    raise ValueError(f"Unsupported corpus format: {suffix}")


def load_oncology_corpus_content(filename: str, content: bytes | str) -> list[dict]:
    suffix = Path(filename).suffix.lower()
    text = content.decode("utf-8") if isinstance(content, bytes) else content

    if suffix == ".json":
        return _load_json_text(text)
    if suffix == ".csv":
        return _load_csv_text(text)
    if suffix == ".txt":
        return _load_txt_text(text, Path(filename).stem)

    raise ValueError(f"Unsupported corpus format: {suffix}")


def _load_json(path: Path) -> list[dict]:
    return _load_json_text(path.read_text(encoding="utf-8"))


def _load_json_text(text: str) -> list[dict]:
    data = json.loads(text)
    if isinstance(data, dict):
        data = data.get("documents", [])
    if not isinstance(data, list):
        raise ValueError("JSON corpus must be a list of documents or an object with a 'documents' list")
    return [_normalize_document(item, index + 1) for index, item in enumerate(data)]


def _load_csv(path: Path) -> list[dict]:
    return _load_csv_text(path.read_text(encoding="utf-8"))


def _load_csv_text(text: str) -> list[dict]:
    reader = csv.DictReader(text.splitlines())
    return [_normalize_document(row, index + 1) for index, row in enumerate(reader)]


def _load_txt(path: Path) -> list[dict]:
    return _load_txt_text(path.read_text(encoding="utf-8"), path.stem)


def _load_txt_text(text: str, stem: str) -> list[dict]:
    chunks = [chunk.strip() for chunk in text.split("\n---\n") if chunk.strip()]
    documents = []
    for index, chunk in enumerate(chunks or [text.strip()], start=1):
        if not chunk:
            continue
        documents.append(
            {
                "source": f"{stem}-{index}",
                "title": f"{stem} section {index}",
                "text": chunk,
                "condition": "",
                "markers": [],
                "biomarkers": [],
            }
        )
    return documents


def _normalize_document(item: dict, index: int) -> dict:
    biomarkers = item.get("biomarkers", [])
    if isinstance(biomarkers, str):
        biomarkers = [part.strip() for part in biomarkers.split("|") if part.strip()]

    markers = item.get("markers", [])
    if isinstance(markers, str):
        markers = [part.strip() for part in markers.split("|") if part.strip()]

    publication_year = item.get("publication_year")
    if publication_year in ("", None):
        publication_year = None
    elif isinstance(publication_year, str):
        publication_year = int(publication_year)

    return {
        "source": item.get("source") or f"document-{index}",
        "title": item.get("title", ""),
        "text": item.get("text", ""),
        "subdomain": item.get("subdomain", ""),
        "condition": item.get("condition") or item.get("cancer_type", ""),
        "markers": markers or biomarkers,
        "cancer_type": item.get("cancer_type", ""),
        "biomarkers": biomarkers,
        "evidence_type": item.get("evidence_type", ""),
        "publication_year": publication_year,
        "created_at": item.get("created_at"),
    }