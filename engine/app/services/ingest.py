"""PDF / text ingestion with page-level citations."""

from __future__ import annotations

from pathlib import Path

import fitz

from app.contracts.policy import PolicyDocument

SUPPORTED_TYPES = {
    ".pdf": "application/pdf",
    ".txt": "text/plain",
    ".md": "text/markdown",
}


class IngestError(ValueError):
    pass


def ingest_bytes(filename: str, payload: bytes) -> PolicyDocument:
    suffix = Path(filename).suffix.lower()
    if suffix not in SUPPORTED_TYPES:
        raise IngestError(f"Unsupported file type: {suffix or 'unknown'}")
    if suffix == ".pdf":
        return _ingest_pdf(filename, payload)
    text = payload.decode("utf-8", errors="replace")
    pages = [text] if text.strip() else []
    return PolicyDocument(
        filename=filename,
        media_type=SUPPORTED_TYPES[suffix],
        page_count=len(pages),
        text=text,
        pages=pages,
    )


def ingest_path(path: str | Path) -> PolicyDocument:
    file_path = Path(path)
    return ingest_bytes(file_path.name, file_path.read_bytes())


def _ingest_pdf(filename: str, payload: bytes) -> PolicyDocument:
    try:
        doc = fitz.open(stream=payload, filetype="pdf")
    except Exception as error:
        raise IngestError(f"Could not read PDF: {error}") from error

    pages: list[str] = []
    with doc:
        for page in doc:
            pages.append(page.get_text("text").strip())
    text = "\n\n".join(
        f"[Page {index}]\n{page_text}" for index, page_text in enumerate(pages, start=1)
    )
    return PolicyDocument(
        filename=filename,
        media_type="application/pdf",
        page_count=len(pages),
        text=text,
        pages=pages,
    )
