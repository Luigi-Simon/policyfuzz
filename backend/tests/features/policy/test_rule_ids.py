import hashlib

import pytest

from app.core.hashing import canonical_sha256
from app.domain.models import (
    Effect,
    PolicyDocument,
    PolicyPage,
    RuleDraft,
    SourceSpan,
    TextRuleProvenance,
)
from app.features.policy.citations import CitationValidationError
from app.features.policy.extraction import (
    ExtractionValidationError,
    assign_baseline_rule_ids,
)


TEXT = "Meals require receipts.\nClaims above SGD 50 require manager approval."


def _hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _document() -> PolicyDocument:
    return PolicyDocument(
        document_id="document-1",
        title="Development policy",
        source_type="pasted_text",
        pages=(PolicyPage(page=1, text=TEXT, start=0, end=len(TEXT)),),
        document_sha256=_hash(TEXT),
    )


def _draft(
    *,
    quote: str = "Meals require receipts.",
    description: str = "Meal receipt rule",
    citation_id: str = "citation-1",
    confidence_percent: int | None = 90,
    effect_value: str = "required",
) -> RuleDraft:
    start = TEXT.index(quote)
    return RuleDraft(
        description=description,
        when=(),
        effects=(Effect(dimension="receipt_requirement", value=effect_value),),
        provenance=TextRuleProvenance(
            citation_id=citation_id,
            span=SourceSpan(
                page=1,
                start=start,
                end=start + len(quote),
                quote=quote,
                quote_sha256=_hash(quote),
            ),
        ),
        confidence_percent=confidence_percent,
    )


def test_rule_id_uses_canonical_semantics_and_source_span_hash() -> None:
    draft = _draft()

    rule = assign_baseline_rule_ids(_document(), (draft,))[0]

    semantic_signature = {
        "when": draft.when,
        "effects": draft.effects,
        "overrides": draft.overrides,
        "source_span_sha256": canonical_sha256(draft.provenance.span),
    }
    assert rule.rule_id == f"rule-{canonical_sha256(semantic_signature)}"
    assert rule.revision == 0


def test_display_description_confidence_and_citation_id_do_not_change_rule_id() -> None:
    first = _draft()
    second = _draft(
        description="Plain-language wording changed",
        citation_id="different-display-id",
        confidence_percent=12,
    )

    first_rule = assign_baseline_rule_ids(_document(), (first,))[0]
    second_rule = assign_baseline_rule_ids(_document(), (second,))[0]

    assert first_rule.rule_id == second_rule.rule_id


def test_semantic_or_source_changes_produce_different_rule_ids() -> None:
    first = _draft()
    different_source = _draft(
        quote="Claims above SGD 50 require manager approval."
    )

    first_rule = assign_baseline_rule_ids(_document(), (first,))[0]
    source_rule = assign_baseline_rule_ids(_document(), (different_source,))[0]

    assert first_rule.rule_id != source_rule.rule_id


def test_rule_id_assignment_rejects_unverified_citation() -> None:
    bad = _draft().model_copy(
        update={
            "provenance": _draft().provenance.model_copy(
                update={
                    "span": _draft().provenance.span.model_copy(
                        update={"quote_sha256": "0" * 64}
                    )
                }
            )
        }
    )

    with pytest.raises(CitationValidationError, match="QUOTE_HASH_MISMATCH"):
        assign_baseline_rule_ids(_document(), (bad,))


def test_duplicate_semantics_and_span_are_rejected() -> None:
    with pytest.raises(ExtractionValidationError, match="DUPLICATE_RULE_ID"):
        assign_baseline_rule_ids(_document(), (_draft(), _draft(citation_id="c2")))
