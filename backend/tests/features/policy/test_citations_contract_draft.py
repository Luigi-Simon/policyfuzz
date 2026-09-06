import hashlib

import pytest

from app.domain.models import PolicyDocument, PolicyPage, SourceSpan
from app.features.policy.citations import (
    CitationValidationError,
    validate_source_span,
)


def _hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


@pytest.fixture
def policy_document() -> PolicyDocument:
    first = "Meals require receipts."
    second = "Claims above SGD 50 require manager approval."
    return PolicyDocument(
        document_id="document-1",
        title="Development policy",
        source_type="pasted_text",
        pages=(
            PolicyPage(page=1, text=first, start=0, end=len(first)),
            PolicyPage(
                page=2,
                text=second,
                start=len(first) + 1,
                end=len(first) + 1 + len(second),
            ),
        ),
        document_sha256="a" * 64,
    )


def test_exact_quote_and_global_offsets_are_accepted(
    policy_document: PolicyDocument,
) -> None:
    page = policy_document.pages[1]
    quote = "SGD 50"
    start = page.start + page.text.index(quote)
    span = SourceSpan(
        page=page.page,
        start=start,
        end=start + len(quote),
        quote=quote,
        quote_sha256=_hash(quote),
    )

    validated = validate_source_span(policy_document, span)

    assert validated.start_offset == span.start
    assert validated.end_offset == span.end


def test_span_cannot_cross_a_page_boundary(policy_document: PolicyDocument) -> None:
    first = policy_document.pages[0]
    span = SourceSpan(
        page=1,
        start=first.end - 2,
        end=first.end + 2,
        quote="ts.X",
        quote_sha256=_hash("ts.X"),
    )

    with pytest.raises(CitationValidationError, match="OFFSETS_OUT_OF_RANGE"):
        validate_source_span(policy_document, span)


def test_wrong_page_is_rejected_even_when_offsets_exist(
    policy_document: PolicyDocument,
) -> None:
    span = SourceSpan(
        page=1,
        start=policy_document.pages[1].start,
        end=policy_document.pages[1].start + 6,
        quote="Claims",
        quote_sha256=_hash("Claims"),
    )

    with pytest.raises(CitationValidationError, match="OFFSETS_OUT_OF_RANGE"):
        validate_source_span(policy_document, span)


def test_invalid_quote_hash_is_rejected(policy_document: PolicyDocument) -> None:
    span = SourceSpan(
        page=1,
        start=0,
        end=5,
        quote="Meals",
        quote_sha256="0" * 64,
    )

    with pytest.raises(CitationValidationError, match="QUOTE_HASH_MISMATCH"):
        validate_source_span(policy_document, span)


def test_quote_is_recomputed_from_offsets(policy_document: PolicyDocument) -> None:
    span = SourceSpan(
        page=1,
        start=0,
        end=5,
        quote="Hotel",
        quote_sha256=_hash("Hotel"),
    )

    with pytest.raises(CitationValidationError, match="QUOTE_MISMATCH"):
        validate_source_span(policy_document, span)
