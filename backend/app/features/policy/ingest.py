"""Safe preparation of policy text and contract-backed page mapping.

This module deliberately stops before constructing a ``PolicyDocument`` because
document identity and canonical hashing are a separate integration boundary.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Iterable
import unicodedata

from app.domain.models import PolicyPage


MAX_POLICY_CHARS = 50_000
MAX_PDF_PAGES = 20


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
