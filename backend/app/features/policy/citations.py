"""Exact citation validation for primitives and public policy contracts."""

from __future__ import annotations

import hashlib
import hmac
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from math import ceil
from types import MappingProxyType

from app.core.hashing import canonical_sha256
from app.domain.models import PolicyDocument, SourceSpan
from app.features.policy.ingest import PolicyIngestionError, prepare_policy_pages

_SHA256_PATTERN = re.compile(r"^[0-9a-f]{64}$")
_CATALOG_LINE_BUDGET = 512


class CitationValidationError(ValueError):
    """A sanitized citation failure identified only by a stable code."""

    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(code)


@dataclass(frozen=True, slots=True)
class CitationCatalogEntry:
    """One source-derived citation; the handle is bound to document and location."""

    citation_handle: str
    span: SourceSpan


@dataclass(frozen=True, slots=True)
class CitationCatalog:
    """Private immutable source catalog, never accepted from a provider."""

    entries: tuple[CitationCatalogEntry, ...]
    _by_handle: Mapping[str, SourceSpan] = field(init=False, repr=False, compare=False)

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "_by_handle",
            MappingProxyType(
                {entry.citation_handle: entry.span for entry in self.entries}
            ),
        )

    def resolve(self, handle: str) -> SourceSpan:
        """Resolve exact membership only, without quote searches or fallback spans."""

        try:
            return self._by_handle[handle]
        except KeyError:
            raise CitationValidationError("UNKNOWN_CITATION_HANDLE") from None


def build_citation_catalog(document: PolicyDocument) -> CitationCatalog:
    """Partition bounded normalized source into exact, nonoverlapping citations.

    Ordinary inputs retain one nonempty line per entry. Above 512 nonempty
    lines, adjacent lines are grouped in source order without crossing pages or
    dropping tail text. At most 512 + 20 entries cover a 50,000-character input.
    Grouping is structural and never interprets or rewrites policy semantics.
    """

    try:
        prepared = prepare_policy_pages(page.text for page in document.pages)
    except PolicyIngestionError as exc:
        raise CitationValidationError(exc.code) from None
    for page, normalized in zip(document.pages, prepared.pages, strict=True):
        if (
            page.text != normalized.text
            or page.start != normalized.start_offset
            or page.end != normalized.end_offset
        ):
            raise CitationValidationError("INVALID_DOCUMENT_LAYOUT")

    lines_by_page = []
    for page in document.pages:
        lines = []
        local_start = 0
        for line in page.text.split("\n"):
            if line.strip():
                lines.append((local_start, local_start + len(line)))
            local_start += len(line) + 1
        lines_by_page.append(lines)
    group_size = max(1, ceil(sum(map(len, lines_by_page)) / _CATALOG_LINE_BUDGET))
    # Include the actual page layout/content, not merely the declared hash.
    document_binding = canonical_sha256(
        {
            "document_sha256": document.document_sha256,
            "pages": document.pages,
        }
    )
    entries = []
    for page, lines in zip(document.pages, lines_by_page, strict=True):
        for index in range(0, len(lines), group_size):
            group = lines[index : index + group_size]
            start, end = group[0][0], group[-1][1]
            quote = page.text[start:end]
            span = SourceSpan(
                page=page.page,
                start=page.start + start,
                end=page.start + end,
                quote=quote,
                quote_sha256=hashlib.sha256(quote.encode("utf-8")).hexdigest(),
            )
            canonical = canonical_source_span(document, span)
            handle = "cite-" + canonical_sha256(
                {
                    "document": document_binding,
                    "page": canonical.page,
                    "start": canonical.start,
                    "end": canonical.end,
                    "quote_sha256": canonical.quote_sha256,
                }
            )
            entries.append(CitationCatalogEntry(citation_handle=handle, span=canonical))
    return CitationCatalog(entries=tuple(entries))


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


def validate_source_span(
    document: PolicyDocument,
    span: SourceSpan,
) -> ValidatedCitation:
    """Verify a public source span against its declared document page.

    ``SourceSpan`` offsets are document-global while ``validate_citation`` uses
    page-local offsets.  This adapter performs that conversion and returns the
    verified values in document-global coordinates.
    """

    page = next((item for item in document.pages if item.page == span.page), None)
    if page is None:
        raise CitationValidationError("PAGE_OUT_OF_RANGE")
    if page.end - page.start != len(page.text):
        raise CitationValidationError("INVALID_PAGE_RANGE")
    if span.start < page.start or span.end > page.end:
        raise CitationValidationError("OFFSETS_OUT_OF_RANGE")

    local_start = span.start - page.start
    local_end = span.end - page.start
    validated = validate_citation(
        pages=(page.text,),
        page_number=1,
        start_offset=local_start,
        end_offset=local_end,
        quote=span.quote,
        quote_sha256=span.quote_sha256,
    )
    return ValidatedCitation(
        page_number=page.page,
        start_offset=page.start + validated.start_offset,
        end_offset=page.start + validated.end_offset,
        quote=validated.quote,
        quote_sha256=validated.quote_sha256,
    )


def canonical_source_span(
    document: PolicyDocument,
    span: SourceSpan,
) -> SourceSpan:
    """Return only citation fields verified against source-controlled text."""

    validated = validate_source_span(document, span)
    return SourceSpan(
        page=validated.page_number,
        start=validated.start_offset,
        end=validated.end_offset,
        quote=validated.quote,
        quote_sha256=validated.quote_sha256,
        section=None,
    )
