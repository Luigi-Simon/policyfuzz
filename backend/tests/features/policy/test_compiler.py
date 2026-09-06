import hashlib

import pytest

from app.domain.models import (
    CompilePolicyRequest,
    Effect,
    PolicyExtraction,
    RuleDraft,
    SourceSpan,
    TextRuleProvenance,
)
from app.features.policy.compiler import compile_baseline_policy
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
