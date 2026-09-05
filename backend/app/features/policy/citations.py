"""Primitive citation validation independent of shared domain contracts."""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import hmac
import re
from typing import Sequence


_SHA256_PATTERN = re.compile(r"^[0-9a-f]{64}$")


class CitationValidationError(ValueError):
    """A sanitized citation failure identified only by a stable code."""

    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(code)


@dataclass(frozen=True, slots=True)
class ValidatedCitation:
    """Citation values that have been verified against normalized source text."""

    page_number: int
    start_offset: int
    end_offset: int
    quote: str
    quote_sha256: str


def validate_citation(
    *,
    pages: Sequence[str],
    page_number: int,
    start_offset: int,
    end_offset: int,
    quote: str,
    quote_sha256: str,
) -> ValidatedCitation:
    """Validate an exact page-local source citation.

    The function accepts primitive values so it can be reused by a thin
    ``PolicyDocument``/``SourceSpan`` adapter once shared contracts are frozen.
    Raised errors never contain source text or model-provided quote content.
    """

    if (
        not isinstance(page_number, int)
        or isinstance(page_number, bool)
        or page_number < 1
        or page_number > len(pages)
    ):
        raise CitationValidationError("PAGE_OUT_OF_RANGE")

    page_text = pages[page_number - 1]
    if not isinstance(page_text, str):
        raise CitationValidationError("INVALID_PAGE_TEXT")
    if (
        not isinstance(start_offset, int)
        or isinstance(start_offset, bool)
        or not isinstance(end_offset, int)
        or isinstance(end_offset, bool)
        or start_offset < 0
        or end_offset <= start_offset
        or end_offset > len(page_text)
    ):
        raise CitationValidationError("OFFSETS_OUT_OF_RANGE")
    if not isinstance(quote, str) or page_text[start_offset:end_offset] != quote:
        raise CitationValidationError("QUOTE_MISMATCH")

    expected_hash = hashlib.sha256(quote.encode("utf-8")).hexdigest()
    if (
        not isinstance(quote_sha256, str)
        or _SHA256_PATTERN.fullmatch(quote_sha256) is None
        or not hmac.compare_digest(expected_hash, quote_sha256)
    ):
        raise CitationValidationError("QUOTE_HASH_MISMATCH")

    return ValidatedCitation(
        page_number=page_number,
        start_offset=start_offset,
        end_offset=end_offset,
        quote=quote,
        quote_sha256=expected_hash,
    )
