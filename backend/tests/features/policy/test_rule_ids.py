import hashlib

import pytest

from app.core.hashing import canonical_sha256
from app.domain.models import (
    Effect,
    OverrideRef,
    PolicyDocument,
    PolicyPage,
    Predicate,
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

    base_signature = {
        "when": draft.when,
        "effects": draft.effects,
        "source": {
            "page": draft.provenance.span.page,
            "start": draft.provenance.span.start,
            "end": draft.provenance.span.end,
            "quote_sha256": draft.provenance.span.quote_sha256,
        },
    }
    semantic_signature = {"rule": base_signature, "overrides": ()}
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
    different_source = _draft(quote="Claims above SGD 50 require manager approval.")

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


def test_untrusted_section_does_not_change_rule_identity_or_artifact() -> None:
    first = _draft()
    second = first.model_copy(
        update={
            "provenance": first.provenance.model_copy(
                update={
                    "span": first.provenance.span.model_copy(
                        update={"section": "PRIVATE_MODEL_SECTION"}
                    )
                }
            )
        }
    )

    first_rule = assign_baseline_rule_ids(_document(), (first,))[0]
    second_rule = assign_baseline_rule_ids(_document(), (second,))[0]

    assert first_rule.rule_id == second_rule.rule_id
    assert second_rule.provenance.span.section is None


def _override_graph(*, permuted: bool = False) -> tuple[RuleDraft, ...]:
    target_a = _draft(citation_id="target-a").model_copy(
        update={
            "description": "No approval",
            "effects": (Effect(dimension="approval_requirement", value="none"),),
        }
    )
    target_b = _draft(
        quote="Claims above SGD 50 require manager approval.",
        citation_id="target-b",
    ).model_copy(
        update={
            "description": "Manager approval",
            "effects": (Effect(dimension="approval_requirement", value="manager"),),
        }
    )
    predicates = (
        Predicate(
            field="employee_role",
            operator="in",
            value=("manager", "employee") if not permuted else ("employee", "manager"),
        ),
        Predicate(field="amount_minor", operator="gte", value=5000),
    )
    effects = (
        Effect(dimension="eligibility", value="allow"),
        Effect(dimension="approval_requirement", value="director"),
    )
    overrides = (
        OverrideRef(dimension="approval_requirement", target_rule_id="target-a"),
        OverrideRef(dimension="approval_requirement", target_rule_id="target-b"),
    )
    source = _draft(citation_id="source").model_copy(
        update={
            "description": "Director exception",
            "when": tuple(reversed(predicates)) if permuted else predicates,
            "effects": tuple(reversed(effects)) if permuted else effects,
            "overrides": tuple(reversed(overrides)) if permuted else overrides,
        }
    )
    return (target_a, target_b, source)


def test_rule_identity_is_invariant_to_semantic_collection_order() -> None:
    first = assign_baseline_rule_ids(_document(), _override_graph())
    second = assign_baseline_rule_ids(_document(), _override_graph(permuted=True))
    first_ids = {rule.provenance.citation_id: rule.rule_id for rule in first}
    second_ids = {rule.provenance.citation_id: rule.rule_id for rule in second}

    assert first_ids == second_ids


def test_override_references_reject_missing_cross_dimension_and_cycles() -> None:
    target, _, source = _override_graph()
    missing = source.model_copy(
        update={
            "overrides": (
                OverrideRef(dimension="approval_requirement", target_rule_id="missing"),
            )
        }
    )
    with pytest.raises(ExtractionValidationError, match="UNKNOWN_OVERRIDE_REFERENCE"):
        assign_baseline_rule_ids(_document(), (target, missing))

    wrong_dimension = target.model_copy(
        update={"effects": (Effect(dimension="eligibility", value="allow"),)}
    )
    cross_source = source.model_copy(
        update={
            "overrides": (
                OverrideRef(
                    dimension="approval_requirement", target_rule_id="target-a"
                ),
            )
        }
    )
    with pytest.raises(ExtractionValidationError, match="INVALID_OVERRIDE_DIMENSION"):
        assign_baseline_rule_ids(_document(), (wrong_dimension, cross_source))

    left = target.model_copy(
        update={
            "provenance": target.provenance.model_copy(update={"citation_id": "left"}),
            "overrides": (
                OverrideRef(dimension="approval_requirement", target_rule_id="right"),
            ),
        }
    )
    right = source.model_copy(
        update={
            "provenance": source.provenance.model_copy(update={"citation_id": "right"}),
            "effects": (Effect(dimension="approval_requirement", value="manager"),),
            "overrides": (
                OverrideRef(dimension="approval_requirement", target_rule_id="left"),
            ),
        }
    )
    with pytest.raises(ExtractionValidationError, match="CYCLIC_OVERRIDE_REFERENCE"):
        assign_baseline_rule_ids(_document(), (left, right))


def test_override_references_reject_ambiguous_local_aliases() -> None:
    target_a, target_b, source = _override_graph()
    target_a = target_a.model_copy(
        update={
            "provenance": target_a.provenance.model_copy(
                update={"citation_id": "duplicate-handle"}
            )
        }
    )
    target_b = target_b.model_copy(
        update={
            "provenance": target_b.provenance.model_copy(
                update={"citation_id": "duplicate-handle"}
            )
        }
    )
    source = source.model_copy(
        update={
            "overrides": (
                OverrideRef(
                    dimension="approval_requirement",
                    target_rule_id="duplicate-handle",
                ),
            )
        }
    )

    with pytest.raises(ExtractionValidationError, match="AMBIGUOUS_OVERRIDE_REFERENCE"):
        assign_baseline_rule_ids(_document(), (target_a, target_b, source))
