import hashlib
import json

import pytest

from app.domain.models import (
    Effect,
    PolicyDocument,
    PolicyExtraction,
    PolicyPage,
    RuleDraft,
    SourceSpan,
    TextRuleProvenance,
    UnsupportedClause,
)
from app.features.policy.extraction import (
    ExtractionValidationError,
    parse_and_validate_policy_extraction,
    validate_policy_extraction,
)
from app.features.policy.model_output import ModelOutputValidationError


TEXT = "Meals require receipts.\nClaims above SGD 50 require manager approval."
HASH = "a" * 64


def _sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _document() -> PolicyDocument:
    return PolicyDocument(
        document_id="document-1",
        title="Development policy",
        source_type="pasted_text",
        pages=(PolicyPage(page=1, text=TEXT, start=0, end=len(TEXT)),),
        document_sha256=HASH,
    )


def _span(quote: str) -> SourceSpan:
    start = TEXT.index(quote)
    return SourceSpan(
        page=1,
        start=start,
        end=start + len(quote),
        quote=quote,
        quote_sha256=_sha256(quote),
    )


def _draft(index: int = 0, *, span: SourceSpan | None = None) -> RuleDraft:
    return RuleDraft(
        description=f"Receipt rule {index}",
        when=(),
        effects=(Effect(dimension="receipt_requirement", value="required"),),
        provenance=TextRuleProvenance(
            citation_id=f"citation-{index}",
            span=span or _span("Meals require receipts."),
        ),
    )


def test_valid_rules_and_unsupported_clauses_are_preserved() -> None:
    unsupported = UnsupportedClause(
        clause_id="clause-1",
        span=_span("Claims above SGD 50"),
        reason_code="ambiguous_language",
        affected_dimensions=frozenset({"approval_requirement"}),
    )
    extraction = PolicyExtraction(
        document_sha256=HASH,
        rules=(_draft(),),
        unsupported_clauses=(unsupported,),
    )

    result = validate_policy_extraction(_document(), extraction)

    assert result.extraction.rules == extraction.rules
    assert result.extraction.unsupported_clauses == (unsupported,)
    assert result.excluded_rule_count == 0


def test_document_hash_mismatch_is_rejected_without_exposing_values() -> None:
    extraction = PolicyExtraction(document_sha256="b" * 64, rules=())

    with pytest.raises(ExtractionValidationError) as exc_info:
        validate_policy_extraction(_document(), extraction)

    assert exc_info.value.code == "DOCUMENT_HASH_MISMATCH"
    assert "a" * 64 not in str(exc_info.value)
    assert "b" * 64 not in str(exc_info.value)


def test_invalid_rule_citation_is_excluded_and_preserved_as_unsupported() -> None:
    bad_span = _span("Meals require receipts.").model_copy(
        update={"quote_sha256": "0" * 64}
    )
    extraction = PolicyExtraction(document_sha256=HASH, rules=(_draft(span=bad_span),))

    result = validate_policy_extraction(_document(), extraction)

    assert result.extraction.rules == ()
    assert result.excluded_rule_count == 1
    assert len(result.extraction.unsupported_clauses) == 1
    clause = result.extraction.unsupported_clauses[0]
    assert clause.reason_code == "invalid_citation"
    assert clause.span.quote == "Meals require receipts."
    assert clause.span.quote_sha256 == _sha256(clause.span.quote)
    assert clause.affected_dimensions == frozenset({"receipt_requirement"})


def test_rule_limit_keeps_first_twelve_and_counts_excluded_rules() -> None:
    extraction = PolicyExtraction(
        document_sha256=HASH,
        rules=tuple(_draft(index) for index in range(14)),
    )

    result = validate_policy_extraction(_document(), extraction)

    assert len(result.extraction.rules) == 12
    assert result.excluded_rule_count == 2


def test_invalid_existing_unsupported_clause_citation_is_rejected() -> None:
    unsupported = UnsupportedClause(
        clause_id="clause-1",
        span=_span("Claims above SGD 50").model_copy(update={"quote": "wrong"}),
        reason_code="ambiguous_language",
        affected_dimensions=frozenset({"approval_requirement"}),
    )
    extraction = PolicyExtraction(
        document_sha256=HASH,
        rules=(),
        unsupported_clauses=(unsupported,),
    )

    with pytest.raises(
        ExtractionValidationError, match="INVALID_UNSUPPORTED_CITATION"
    ):
        validate_policy_extraction(_document(), extraction)


@pytest.mark.parametrize(
    "invalid_effect",
    [
        {"dimension": "receipt_requirement", "value": "director"},
        {"dimension": "unknown_dimension", "value": "required"},
    ],
)
def test_raw_proposals_reject_invalid_effects(
    invalid_effect: dict[str, object],
) -> None:
    payload = json.loads(
        PolicyExtraction(
            document_sha256=HASH,
            rules=(_draft(),),
        ).model_dump_json()
    )
    payload["rules"][0]["effects"] = [invalid_effect]

    with pytest.raises(ModelOutputValidationError, match="SCHEMA_VALIDATION_FAILED"):
        parse_and_validate_policy_extraction(
            _document(),
            json.dumps(payload),
        )


def test_raw_proposals_reject_unsupported_predicate_fields() -> None:
    payload = json.loads(
        PolicyExtraction(
            document_sha256=HASH,
            rules=(_draft(),),
        ).model_dump_json()
    )
    payload["rules"][0]["when"] = [
        {"field": "student_age", "operator": "gte", "value": 18}
    ]

    with pytest.raises(ModelOutputValidationError, match="SCHEMA_VALIDATION_FAILED"):
        parse_and_validate_policy_extraction(
            _document(),
            json.dumps(payload),
        )
