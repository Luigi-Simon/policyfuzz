"""Contract-first citation tests; enabled once Person 1 publishes SourceSpan models."""

import hashlib

import pytest


citations = pytest.importorskip("app.features.policy.citations")
if not hasattr(citations, "SourceSpan"):
    pytest.skip(
        "waiting for Person 1's shared SourceSpan contract and adapter",
        allow_module_level=True,
    )


def _span(page: int, text: str, start: int, end: int):
    return citations.SourceSpan(
        page=page,
        start=start,
        end=end,
        quote=text[start:end],
        quote_sha256=hashlib.sha256(text[start:end].encode("utf-8")).hexdigest(),
    )


def test_exact_quote_and_offsets_are_accepted(policy_document):
    page = policy_document.pages[0].text
    citations.validate_source_span(policy_document, _span(1, page, 0, 12))


@pytest.mark.parametrize(
    "page,start,end,quote",
    [(2, 0, 4, "Meal"), (1, -1, 4, "Meal"), (1, 0, 999, "Meal"), (1, 0, 4, "WRONG")],
)
def test_invalid_page_or_offsets_are_rejected(policy_document, page, start, end, quote):
    bad = citations.SourceSpan(
        page=page,
        start=start,
        end=end,
        quote=quote,
        quote_sha256="0" * 64,
    )
    with pytest.raises(citations.CitationValidationError):
        citations.validate_source_span(policy_document, bad)


def test_invalid_quote_hash_is_rejected(policy_document):
    page = policy_document.pages[0].text
    bad = _span(1, page, 0, 12).model_copy(update={"quote_sha256": "0" * 64})
    with pytest.raises(citations.CitationValidationError, match="QUOTE_HASH_MISMATCH"):
        citations.validate_source_span(policy_document, bad)


def test_quote_is_recomputed_from_offsets_not_trusted_from_model(policy_document):
    page = policy_document.pages[0].text
    bad = _span(1, page, 0, 12).model_copy(update={"quote": "model supplied text"})
    with pytest.raises(citations.CitationValidationError, match="QUOTE_MISMATCH"):
        citations.validate_source_span(policy_document, bad)
