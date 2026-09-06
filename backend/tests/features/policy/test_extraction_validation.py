import hashlib
import json

import pytest

from app.core.fakes import ScriptedLLMClient
from app.domain.models import (
    CompilePolicyRequest,
    Effect,
    LLMResponse,
    OverrideRef,
    PolicyDocument,
    PolicyExtraction,
    PolicyPage,
    RuleDraft,
    SourceSpan,
    TextRuleProvenance,
    UnsupportedClause,
)
from app.features.policy.citations import build_citation_catalog
from app.features.policy.compiler import compile_baseline_policy
from app.features.policy.extraction import (
    ExtractionValidationError,
    extract_policy,
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


def test_rule_depending_on_invalidly_cited_rule_is_preserved_as_unsupported() -> None:
    target = _draft(index=1).model_copy(
        update={
            "description": "Normal approval rule",
            "effects": (Effect(dimension="approval_requirement", value="none"),),
            "provenance": TextRuleProvenance(
                citation_id="normal-approval",
                span=_span("Meals require receipts.").model_copy(
                    update={"quote_sha256": "0" * 64}
                ),
            ),
        }
    )
    dependent = _draft(index=2, span=_span("Claims above SGD 50")).model_copy(
        update={
            "description": "Manager approval exception",
            "effects": (Effect(dimension="approval_requirement", value="manager"),),
            "overrides": (
                OverrideRef(
                    dimension="approval_requirement",
                    target_rule_id="normal-approval",
                ),
            ),
        }
    )
    extraction = PolicyExtraction(
        document_sha256=HASH,
        rules=(target, dependent),
    )

    result = validate_policy_extraction(_document(), extraction)
    compiled = compile_baseline_policy(
        CompilePolicyRequest(document=_document(), extraction=result.extraction)
    )

    assert compiled.policy.rules == ()
    assert result.excluded_rule_count == 2
    assert {clause.reason_code for clause in result.extraction.unsupported_clauses} == {
        "invalid_citation",
        "unsupported_logic",
    }


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

    with pytest.raises(ExtractionValidationError, match="INVALID_UNSUPPORTED_CITATION"):
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


def test_validated_spans_discard_untrusted_section_metadata() -> None:
    hostile = "PRIVATE_MODEL_SECTION"
    span = _span("Meals require receipts.").model_copy(update={"section": hostile})
    unsupported = UnsupportedClause(
        clause_id="clause-1",
        span=_span("Claims above SGD 50").model_copy(update={"section": hostile}),
        reason_code="ambiguous_language",
        affected_dimensions=frozenset({"approval_requirement"}),
    )
    extraction = PolicyExtraction(
        document_sha256=HASH,
        rules=(_draft(span=span),),
        unsupported_clauses=(unsupported,),
    )

    result = validate_policy_extraction(_document(), extraction)

    assert result.extraction.rules[0].provenance.span.section is None
    assert result.extraction.unsupported_clauses[0].span.section is None


def test_invalid_citation_replacement_discards_untrusted_section_metadata() -> None:
    hostile = "PRIVATE_MODEL_SECTION"
    bad = _span("Meals require receipts.").model_copy(
        update={"quote_sha256": "0" * 64, "section": hostile}
    )

    result = validate_policy_extraction(
        _document(), PolicyExtraction(document_sha256=HASH, rules=(_draft(span=bad),))
    )

    assert result.extraction.unsupported_clauses[0].span.section is None


@pytest.mark.asyncio
async def test_provider_local_rule_handles_compile_to_final_override_ids() -> None:
    document = _document()
    normal = _draft(index=1, span=_span("Meals require receipts.")).model_copy(
        update={
            "description": "Approval normally not required",
            "effects": (Effect(dimension="approval_requirement", value="none"),),
        }
    )
    exception = _draft(index=2, span=_span("Claims above SGD 50")).model_copy(
        update={
            "description": "Manager approval exception",
            "effects": (Effect(dimension="approval_requirement", value="manager"),),
            "overrides": (
                OverrideRef(
                    dimension="approval_requirement",
                    target_rule_id="normal-approval",
                ),
            ),
        }
    )
    payload = PolicyExtraction(
        document_sha256=HASH,
        rules=(normal, exception),
    ).model_dump(mode="json")
    payload["rules"][0]["rule_handle"] = "normal-approval"
    payload["rules"][1]["rule_handle"] = "manager-exception"
    catalog = build_citation_catalog(document)
    for rule, entry in zip(payload["rules"], catalog.entries, strict=True):
        rule.pop("provenance")
        rule["citation_handle"] = entry.citation_handle
    llm = ScriptedLLMClient((LLMResponse(output=payload), LLMResponse(output=payload)))

    extracted = await extract_policy(llm, CompilePolicyRequest(document=document))
    compiled = compile_baseline_policy(
        CompilePolicyRequest(document=document, extraction=extracted)
    )
    rules = {rule.description: rule for rule in compiled.policy.rules}

    assert rules["Manager approval exception"].overrides[0].target_rule_id == (
        rules["Approval normally not required"].rule_id
    )
    assert len(llm.requests) == 1
