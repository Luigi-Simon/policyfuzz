import hashlib

import pytest

from app.core.fakes import ScriptedLLMClient
from app.domain.models import (
    AssertionContent,
    CompilePolicyRequest,
    Effect,
    InvariantSuggestion,
    InvariantSuggestions,
    LLMResponse,
    PolicyExtraction,
    Predicate,
    RuleDraft,
    SourceSpan,
    TextRuleProvenance,
)
from app.features.policy.compiler import LLMPolicyCompiler, compile_baseline_policy
from app.features.policy.extraction import ExtractionValidationError
from app.features.policy.ingest import ingest_policy_text

TEXT = "Meals require receipts."


def _hash(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _request(*, bad_citation: bool = False) -> CompilePolicyRequest:
    document = ingest_policy_text(
        title="Development policy", text=TEXT, source_type="pasted_text"
    )
    draft = RuleDraft(
        description="Meal receipts",
        when=(),
        effects=(Effect(dimension="receipt_requirement", value="required"),),
        provenance=TextRuleProvenance(
            citation_id="citation-1",
            span=SourceSpan(
                page=1,
                start=0,
                end=len(TEXT),
                quote=TEXT,
                quote_sha256="0" * 64 if bad_citation else _hash(TEXT),
            ),
        ),
    )
    return CompilePolicyRequest(
        document=document,
        extraction=PolicyExtraction(
            document_sha256=document.document_sha256,
            rules=(draft,),
        ),
    )


def test_compile_baseline_builds_provisional_policy_ir() -> None:
    result = compile_baseline_policy(_request())

    assert result.policy.kind == "compiled_baseline"
    assert result.policy.review_status == "provisional"
    assert result.policy.base_currency == "SGD"
    assert result.policy.policy_id.startswith("policy-")
    assert len(result.policy.rules) == 1
    assert result.excluded_rule_count == 0


def test_compile_baseline_is_deterministic() -> None:
    assert compile_baseline_policy(_request()) == compile_baseline_policy(_request())


def test_compile_excludes_bad_citation_and_preserves_unsupported_clause() -> None:
    result = compile_baseline_policy(_request(bad_citation=True))

    assert result.policy.rules == ()
    assert result.excluded_rule_count == 1
    assert result.policy.unsupported_clauses[0].reason_code == "invalid_citation"


def test_compile_rejects_document_hash_mismatch() -> None:
    request = _request()
    bad = request.model_copy(
        update={
            "extraction": request.extraction.model_copy(
                update={"document_sha256": "b" * 64}
            )
        }
    )

    with pytest.raises(ExtractionValidationError, match="DOCUMENT_HASH_MISMATCH"):
        compile_baseline_policy(bad)


def _suggestions() -> InvariantSuggestions:
    return InvariantSuggestions(
        invariant_drafts=tuple(
            InvariantSuggestion(
                invariant_id=f"model-invariant-{index}",
                description=f"Suggested intent {index}",
                rationale="This is an editable, provisional suggestion.",
                when=(
                    Predicate(
                        field="expense_category",
                        operator="eq",
                        value=("meal", "hotel", "transport")[index],
                    ),
                ),
                assertion=AssertionContent(
                    assertion_id=f"model-assertion-{index}",
                    target_kind="effect_value",
                    dimension="claim_cap_minor",
                    operator="lte",
                    expected_value=(5000, 25000, 20000)[index],
                ),
            )
            for index in range(3)
        )
    )


@pytest.mark.asyncio
async def test_llm_compiler_extracts_then_returns_provisional_suggestions() -> None:
    source = _request()
    llm = ScriptedLLMClient(
        (
            LLMResponse(output=source.extraction.model_dump(mode="json")),
            LLMResponse(output=_suggestions().model_dump(mode="json")),
        )
    )

    result = await LLMPolicyCompiler(llm).compile(
        CompilePolicyRequest(document=source.document)
    )

    assert result.policy.review_status == "provisional"
    assert len(result.invariant_drafts) == 3
    assert all(item.origin == "model_suggestion" for item in result.invariant_drafts)
    assert all(
        item.invariant_id.startswith("invariant-")
        and item.assertion.assertion_id.startswith("assertion-")
        for item in result.invariant_drafts
    )
    assert [request.operation for request in llm.requests] == [
        "policy_extraction",
        "invariant_suggestion",
    ]
    assert all(
        "Meals require receipts." not in item.system_instructions
        for item in llm.requests
    )


@pytest.mark.asyncio
async def test_llm_compiler_overrides_model_suggestion_ids_deterministically() -> None:
    request = _request()
    first = ScriptedLLMClient(
        (LLMResponse(output=_suggestions().model_dump(mode="json")),)
    )
    changed_ids = _suggestions().model_copy(
        update={
            "invariant_drafts": tuple(
                item.model_copy(
                    update={
                        "invariant_id": f"other-{index}",
                        "assertion": item.assertion.model_copy(
                            update={"assertion_id": f"other-assertion-{index}"}
                        ),
                    }
                )
                for index, item in enumerate(_suggestions().invariant_drafts)
            )
        }
    )
    second = ScriptedLLMClient(
        (LLMResponse(output=changed_ids.model_dump(mode="json")),)
    )

    a = await LLMPolicyCompiler(first).compile(request)
    b = await LLMPolicyCompiler(second).compile(request)

    assert a == b


@pytest.mark.asyncio
async def test_invariant_identity_is_invariant_to_predicate_and_membership_order() -> (
    None
):
    base = _suggestions()
    predicates = (
        Predicate(
            field="expense_category",
            operator="in",
            value=("meal", "hotel"),
        ),
        Predicate(field="amount_minor", operator="gte", value=5000),
    )
    first_items = list(base.invariant_drafts)
    first_items[0] = first_items[0].model_copy(update={"when": predicates})
    second_items = list(base.invariant_drafts)
    second_items[0] = second_items[0].model_copy(
        update={
            "when": (
                predicates[1],
                predicates[0].model_copy(update={"value": ("hotel", "meal")}),
            )
        }
    )
    first = ScriptedLLMClient(
        (
            LLMResponse(
                output=InvariantSuggestions(
                    invariant_drafts=tuple(first_items)
                ).model_dump(mode="json")
            ),
        )
    )
    second = ScriptedLLMClient(
        (
            LLMResponse(
                output=InvariantSuggestions(
                    invariant_drafts=tuple(second_items)
                ).model_dump(mode="json")
            ),
        )
    )

    a = await LLMPolicyCompiler(first).compile(_request())
    b = await LLMPolicyCompiler(second).compile(_request())

    assert a.invariant_drafts[0].invariant_id == b.invariant_drafts[0].invariant_id
    assert (
        a.invariant_drafts[0].assertion.assertion_id
        == b.invariant_drafts[0].assertion.assertion_id
    )
