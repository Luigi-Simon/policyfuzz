"""Safe preparation and contract-backed construction of policy documents."""

from __future__ import annotations

import hashlib
import unicodedata
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Literal

from app.domain.models import PolicyDocument, PolicyPage


MAX_POLICY_CHARS = 50_000
MAX_PDF_PAGES = 20
SourceType = Literal["pasted_text", "bundled_sample"]


class PolicyIngestionError(ValueError):
    """A sanitized, stable ingestion failure safe to expose to callers."""

    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(code)


@dataclass(frozen=True, slots=True)
class PreparedPolicyPage:
    """Normalized page text with offsets into the combined normalized text."""

    page_number: int
    text: str
    start_offset: int
    end_offset: int


@dataclass(frozen=True, slots=True)
class PreparedPolicyText:
    """Validated policy text awaiting conversion to the shared contract."""

    text: str
    pages: tuple[PreparedPolicyPage, ...]
    character_count: int


def _normalize(text: str) -> str:
    if not isinstance(text, str):
        raise PolicyIngestionError("INVALID_POLICY_TEXT_TYPE")
    normalized_newlines = text.replace("\r\n", "\n").replace("\r", "\n")
    return unicodedata.normalize("NFC", normalized_newlines)


def prepare_policy_text(
    text: str,
    *,
    max_characters: int = MAX_POLICY_CHARS,
) -> PreparedPolicyText:
    """Normalize and validate a pasted or bundled single-page policy."""

    return prepare_policy_pages((text,), max_characters=max_characters, max_pages=1)


def prepare_policy_pages(
    pages: Iterable[str],
    *,
    max_characters: int = MAX_POLICY_CHARS,
    max_pages: int = MAX_PDF_PAGES,
) -> PreparedPolicyText:
    """Prepare already-extracted page text without depending on a PDF library.

    A single newline separates pages in the combined representation. Page
    offsets point only to page content and exclude that separator.
    """

    if max_characters < 1 or max_pages < 1:
        raise ValueError("ingestion limits must be positive")

    raw_pages = tuple(pages)
    if not raw_pages:
        raise PolicyIngestionError("EMPTY_POLICY")
    if len(raw_pages) > max_pages:
        raise PolicyIngestionError("TOO_MANY_PAGES")

    normalized_pages: list[str] = []
    for raw_page in raw_pages:
        normalized = _normalize(raw_page)
        if not normalized.strip():
            if len(raw_pages) == 1:
                raise PolicyIngestionError("EMPTY_POLICY")
            raise PolicyIngestionError("EMPTY_PAGE")
        normalized_pages.append(normalized)

    combined = "\n".join(normalized_pages)
    if len(combined) > max_characters:
        raise PolicyIngestionError("POLICY_TOO_LARGE")

    prepared_pages: list[PreparedPolicyPage] = []
    start_offset = 0
    for page_number, normalized in enumerate(normalized_pages, start=1):
        end_offset = start_offset + len(normalized)
        prepared_pages.append(
            PreparedPolicyPage(
                page_number=page_number,
                text=normalized,
                start_offset=start_offset,
                end_offset=end_offset,
            )
        )
        start_offset = end_offset + 1

    return PreparedPolicyText(
        text=combined,
        pages=tuple(prepared_pages),
        character_count=len(combined),
    )


def load_bundled_policy_text(path: Path) -> PreparedPolicyText:
    """Read a UTF-8 policy file without leaking its path in raised errors."""

    if not path.is_file():
        raise PolicyIngestionError("POLICY_FILE_NOT_FOUND")
    try:
        text = path.read_text(encoding="utf-8")
    except UnicodeDecodeError as exc:
        raise PolicyIngestionError("INVALID_UTF8") from exc
    except OSError as exc:
        raise PolicyIngestionError("POLICY_FILE_READ_FAILED") from exc
    return prepare_policy_text(text)


def to_policy_pages(prepared: PreparedPolicyText) -> tuple[PolicyPage, ...]:
    """Map validated prepared pages into Person 1's immutable page contract."""

    return tuple(
        PolicyPage(
            page=page.page_number,
            text=page.text,
            start=page.start_offset,
            end=page.end_offset,
        )
        for page in prepared.pages
    )


def _document_from_prepared(
    *,
    title: str,
    prepared: PreparedPolicyText,
    source_type: SourceType,
) -> PolicyDocument:
    if not isinstance(title, str) or not title.strip():
        raise PolicyIngestionError("EMPTY_POLICY_TITLE")
    if source_type not in ("pasted_text", "bundled_sample"):
        raise PolicyIngestionError("UNSUPPORTED_SOURCE_TYPE")

    normalized_title = _normalize(title)
    document_sha256 = hashlib.sha256(prepared.text.encode("utf-8")).hexdigest()
    return PolicyDocument(
        document_id=f"document-{document_sha256}",
        title=normalized_title,
        source_type=source_type,
        pages=to_policy_pages(prepared),
        document_sha256=document_sha256,
    )


def ingest_policy_text(
    *,
    title: str,
    text: str,
    source_type: SourceType,
) -> PolicyDocument:
    """Normalize bounded text and create Person 1's document contract."""

    if source_type not in ("pasted_text", "bundled_sample"):
        raise PolicyIngestionError("UNSUPPORTED_SOURCE_TYPE")
    return _document_from_prepared(
        title=title,
        prepared=prepare_policy_text(text),
        source_type=source_type,
    )


def load_bundled_policy(path: Path) -> PolicyDocument:
    """Load a UTF-8 sample and create a deterministically identified document."""

    return _document_from_prepared(
        title=path.stem,
        prepared=load_bundled_policy_text(path),
        source_type="bundled_sample",
    )
