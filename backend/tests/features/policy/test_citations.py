import hashlib
import json
from pathlib import Path

import pytest

from app.features.policy.citations import (
    CitationValidationError,
    validate_citation,
)

PAGES = (
    "Meals are capped at SGD 80 per day.\nReceipts are required.",
    "Claims above SGD 50 require manager approval.",
)


def _hash(quote: str) -> str:
    return hashlib.sha256(quote.encode("utf-8")).hexdigest()


def test_exact_quote_offsets_page_and_hash_are_accepted() -> None:
    quote = "Receipts are required."
    start = PAGES[0].index(quote)

    citation = validate_citation(
        pages=PAGES,
        page_number=1,
        start_offset=start,
        end_offset=start + len(quote),
        quote=quote,
        quote_sha256=_hash(quote),
    )

    assert citation.page_number == 1
    assert citation.start_offset == start
    assert citation.end_offset == start + len(quote)
    assert citation.quote == quote
    assert citation.quote_sha256 == _hash(quote)


@pytest.mark.parametrize("page_number", [0, 3, -1])
def test_invalid_page_number_is_rejected(page_number: int) -> None:
    with pytest.raises(CitationValidationError, match="PAGE_OUT_OF_RANGE"):
        validate_citation(
            pages=PAGES,
            page_number=page_number,
            start_offset=0,
            end_offset=5,
            quote="Meals",
            quote_sha256=_hash("Meals"),
        )


@pytest.mark.parametrize(
    ("start", "end"),
    [(-1, 5), (0, len(PAGES[0]) + 1), (4, 4), (5, 4)],
)
def test_invalid_offsets_are_rejected(start: int, end: int) -> None:
    with pytest.raises(CitationValidationError, match="OFFSETS_OUT_OF_RANGE"):
        validate_citation(
            pages=PAGES,
            page_number=1,
            start_offset=start,
            end_offset=end,
            quote="Meals",
            quote_sha256=_hash("Meals"),
        )


def test_quote_that_does_not_match_source_is_rejected() -> None:
    with pytest.raises(CitationValidationError, match="QUOTE_MISMATCH"):
        validate_citation(
            pages=PAGES,
            page_number=1,
            start_offset=0,
            end_offset=5,
            quote="Hotel",
            quote_sha256=_hash("Hotel"),
        )


@pytest.mark.parametrize("bad_hash", ["0" * 64, "not-a-hash", "A" * 64])
def test_invalid_or_incorrect_hash_is_rejected(bad_hash: str) -> None:
    with pytest.raises(CitationValidationError, match="QUOTE_HASH_MISMATCH"):
        validate_citation(
            pages=PAGES,
            page_number=1,
            start_offset=0,
            end_offset=5,
            quote="Meals",
            quote_sha256=bad_hash,
        )


def test_error_does_not_include_private_policy_text() -> None:
    private_text = "PRIVATE-policy-value-123"
    with pytest.raises(CitationValidationError) as exc_info:
        validate_citation(
            pages=(private_text,),
            page_number=1,
            start_offset=0,
            end_offset=7,
            quote="private",
            quote_sha256="0" * 64,
        )

    assert private_text not in str(exc_info.value)
    assert "private" not in str(exc_info.value)


def test_development_fixture_citations_match_sample_policy() -> None:
    repository_root = Path(__file__).parents[4]
    policy_text = (
        repository_root / "samples/policies/development-policy.txt"
    ).read_text(encoding="utf-8")
    expected = json.loads(
        (
            repository_root / "team/person-2-policy/expected-extracted-rules.json"
        ).read_text(encoding="utf-8")
    )

    assert (
        expected["source_sha256"]
        == hashlib.sha256(policy_text.encode("utf-8")).hexdigest()
    )

    for rule in expected["rules"]:
        citation = rule["citation"]
        validate_citation(
            pages=(policy_text,),
            page_number=citation["page"],
            start_offset=citation["start"],
            end_offset=citation["end"],
            quote=citation["quote"],
            quote_sha256=citation["quote_sha256"],
        )

    for clause in expected["unsupported_clauses"]:
        citation = clause["citation"]
        validate_citation(
            pages=(policy_text,),
            page_number=citation["page"],
            start_offset=citation["start"],
            end_offset=citation["end"],
            quote=clause["text"],
            quote_sha256=citation["quote_sha256"],
        )
