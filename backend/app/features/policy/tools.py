"""Bounded deterministic retrieval tools for the Policy Compiler Agent."""

from __future__ import annotations

import re
from dataclasses import dataclass

from app.features.policy.ingest import PreparedPolicyPage, PreparedPolicyText

MAX_PAGE_READ_CHARS = 5_000
MAX_SEARCH_QUERY_CHARS = 200
MAX_SEARCH_RESULTS = 5
MAX_SEARCH_CONTEXT_CHARS = 120
MAX_SECTION_CHARS = 3_000


class PolicyToolError(ValueError):
    """A sanitized tool failure containing no source-policy content."""

    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(code)


@dataclass(frozen=True, slots=True)
class PageExcerpt:
    page_number: int
    text: str
    start_offset: int
    end_offset: int
    truncated: bool


@dataclass(frozen=True, slots=True)
class SearchHit:
    page_number: int
    start_offset: int
    end_offset: int
    quote: str
    context: str
    context_start_offset: int
    context_end_offset: int


@dataclass(frozen=True, slots=True)
class SectionExcerpt:
    section_name: str
    page_number: int
    text: str
    start_offset: int
    end_offset: int
    truncated: bool


def _page(policy: PreparedPolicyText, page_number: int) -> PreparedPolicyPage:
    if (
        not isinstance(page_number, int)
        or isinstance(page_number, bool)
        or page_number < 1
        or page_number > len(policy.pages)
    ):
        raise PolicyToolError("PAGE_OUT_OF_RANGE")
    return policy.pages[page_number - 1]


def _positive_limit(value: int, *, code: str) -> int:
    if not isinstance(value, int) or isinstance(value, bool) or value < 1:
        raise PolicyToolError(code)
    return value


def read_page(
    policy: PreparedPolicyText,
    *,
    page_number: int,
    max_characters: int = MAX_PAGE_READ_CHARS,
) -> PageExcerpt:
    """Return a bounded prefix of one normalized policy page."""

    limit = _positive_limit(max_characters, code="INVALID_RESULT_LIMIT")
    page = _page(policy, page_number)
    text = page.text[:limit]
    return PageExcerpt(
        page_number=page.page_number,
        text=text,
        start_offset=page.start_offset,
        end_offset=page.start_offset + len(text),
        truncated=len(text) < len(page.text),
    )


def search_policy(
    policy: PreparedPolicyText,
    query: str,
    *,
    max_results: int = MAX_SEARCH_RESULTS,
    context_characters: int = MAX_SEARCH_CONTEXT_CHARS,
) -> tuple[SearchHit, ...]:
    """Find bounded, case-insensitive literal matches across policy pages."""

    if (
        not isinstance(query, str)
        or not query.strip()
        or len(query) > MAX_SEARCH_QUERY_CHARS
    ):
        raise PolicyToolError("INVALID_SEARCH_QUERY")
    result_limit = _positive_limit(max_results, code="INVALID_RESULT_LIMIT")
    if (
        not isinstance(context_characters, int)
        or isinstance(context_characters, bool)
        or context_characters < 0
    ):
        raise PolicyToolError("INVALID_CONTEXT_LIMIT")

    pattern = re.compile(re.escape(query), flags=re.IGNORECASE)
    hits: list[SearchHit] = []
    for page in policy.pages:
        for match in pattern.finditer(page.text):
            context_start = max(0, match.start() - context_characters)
            context_end = min(len(page.text), match.end() + context_characters)
            hits.append(
                SearchHit(
                    page_number=page.page_number,
                    start_offset=page.start_offset + match.start(),
                    end_offset=page.start_offset + match.end(),
                    quote=match.group(0),
                    context=page.text[context_start:context_end],
                    context_start_offset=page.start_offset + context_start,
                    context_end_offset=page.start_offset + context_end,
                )
            )
            if len(hits) == result_limit:
                return tuple(hits)
    return tuple(hits)


_HEADING_PATTERN = re.compile(
    r"(?m)^[ \t]*(?:\d+(?:\.\d+)*|\d+\([A-Za-z0-9]+\))[.)]?[ \t]+\S.*$"
)


def find_section(
    policy: PreparedPolicyText,
    section_name: str,
    *,
    max_characters: int = MAX_SECTION_CHARS,
) -> SectionExcerpt:
    """Return one numbered section up to the next numbered heading."""

    if (
        not isinstance(section_name, str)
        or not section_name.strip()
        or len(section_name) > 50
    ):
        raise PolicyToolError("INVALID_SECTION_NAME")
    limit = _positive_limit(max_characters, code="INVALID_RESULT_LIMIT")
    escaped = re.escape(section_name.strip())
    requested_heading = re.compile(
        rf"(?m)^[ \t]*{escaped}(?:[.)](?=[ \t])|(?=[ \t]))[ \t]+\S.*$"
    )

    for page in policy.pages:
        heading = requested_heading.search(page.text)
        if heading is None:
            continue
        next_heading = _HEADING_PATTERN.search(page.text, heading.end())
        raw_end = next_heading.start() if next_heading else len(page.text)
        section_text = page.text[heading.start() : raw_end].rstrip()
        full_end = heading.start() + len(section_text)
        returned_text = section_text[:limit]
        return SectionExcerpt(
            section_name=section_name.strip(),
            page_number=page.page_number,
            text=returned_text,
            start_offset=page.start_offset + heading.start(),
            end_offset=page.start_offset + heading.start() + len(returned_text),
            truncated=len(returned_text) < (full_end - heading.start()),
        )
    raise PolicyToolError("SECTION_NOT_FOUND")


def get_clause_context(
    policy: PreparedPolicyText,
    *,
    page_number: int,
    start_offset: int,
    end_offset: int,
    context_characters: int = MAX_SEARCH_CONTEXT_CHARS,
) -> PageExcerpt:
    """Return bounded context around page-local clause offsets."""

    page = _page(policy, page_number)
    if (
        not isinstance(start_offset, int)
        or isinstance(start_offset, bool)
        or not isinstance(end_offset, int)
        or isinstance(end_offset, bool)
        or start_offset < 0
        or end_offset <= start_offset
        or end_offset > len(page.text)
    ):
        raise PolicyToolError("OFFSETS_OUT_OF_RANGE")
    if (
        not isinstance(context_characters, int)
        or isinstance(context_characters, bool)
        or context_characters < 0
    ):
        raise PolicyToolError("INVALID_CONTEXT_LIMIT")

    context_start = max(0, start_offset - context_characters)
    context_end = min(len(page.text), end_offset + context_characters)
    return PageExcerpt(
        page_number=page.page_number,
        text=page.text[context_start:context_end],
        start_offset=page.start_offset + context_start,
        end_offset=page.start_offset + context_end,
        truncated=context_start > 0 or context_end < len(page.text),
    )
