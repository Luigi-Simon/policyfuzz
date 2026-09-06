import hashlib

import pytest

from app.domain.models import (
    CompilePolicyRequest,
    Effect,
    OverrideRef,
    PolicyDocument,
    PolicyExtraction,
    PolicyPage,
    Predicate,
    RuleDraft,
    SourceSpan,
    TextRuleProvenance,
    UnsupportedClause,
)
from app.features.policy.compiler import compile_baseline_policy
from app.features.policy.extraction import validate_policy_extraction


def _extraction(rule_count: int) -> tuple[PolicyDocument, PolicyExtraction]:
    lines = [
        f"Meals over SGD {index + 1} require receipts."
        for index in range(rule_count - 1)
    ] + ["Airfare requires receipts and director approval."]
    text = "\n".join(lines)
    document = PolicyDocument(
        document_id="rule-limit-document",
        title="Synthetic rule limit policy",
        source_type="pasted_text",
        pages=(PolicyPage(page=1, text=text, start=0, end=len(text)),),
        document_sha256=hashlib.sha256(text.encode()).hexdigest(),
    )
    rules = []
    for index, line in enumerate(lines):
        airfare = index == rule_count - 1
        start = text.index(line)
        rules.append(
            RuleDraft(
                description=line,
                when=(
                    (
                        Predicate(
                            field="expense_category", operator="eq", value="airfare"
                        ),
                    )
                    if airfare
                    else (
                        Predicate(
                            field="expense_category", operator="eq", value="meal"
                        ),
                        Predicate(
                            field="amount_minor", operator="gt", value=(index + 1) * 100
                        ),
                    )
                ),
                effects=(Effect(dimension="receipt_requirement", value="required"),)
                + (
                    (Effect(dimension="approval_requirement", value="director"),)
                    if airfare
                    else ()
                ),
                provenance=TextRuleProvenance(
                    citation_id=f"citation-{index + 1}",
                    span=SourceSpan(
                        page=1,
                        start=start,
                        end=start + len(line),
                        quote=line,
                        quote_sha256=hashlib.sha256(line.encode()).hexdigest(),
                    ),
                ),
            )
        )
    return document, PolicyExtraction(
        document_sha256=document.document_sha256,
        rules=tuple(rules),
    )


def test_thirteenth_cited_rule_remains_in_public_unsupported_review() -> None:
    document, extraction = _extraction(13)
    existing = UnsupportedClause(
        clause_id="unsupported-logic-13",
        span=extraction.rules[0].provenance.span,
        reason_code="ambiguous_language",
        affected_dimensions=frozenset({"receipt_requirement"}),
    )
    extraction = extraction.model_copy(update={"unsupported_clauses": (existing,)})

    result = validate_policy_extraction(document, extraction)

    assert result.extraction.rules == extraction.rules[:12]
    assert result.excluded_rule_count == 1
    assert len(result.extraction.unsupported_clauses) == 2
    assert result.extraction.unsupported_clauses[0] == existing
    clause = result.extraction.unsupported_clauses[1]
    assert clause.clause_id == "unsupported-logic-13-2"
    assert clause.span == extraction.rules[12].provenance.span
    assert clause.reason_code == "unsupported_logic"
    assert clause.affected_dimensions == frozenset(
        {"receipt_requirement", "approval_requirement"}
    )
    assert clause.when_hint == (
        Predicate(field="expense_category", operator="eq", value="airfare"),
    )
    assert clause.review_status == "provisional"

    repeated = validate_policy_extraction(document, extraction)
    revalidated = validate_policy_extraction(document, result.extraction)
    assert repeated == result
    assert revalidated.extraction == result.extraction
    compiled = compile_baseline_policy(
        CompilePolicyRequest(document=document, extraction=result.extraction)
    )
    capped = compile_baseline_policy(
        CompilePolicyRequest(
            document=document,
            extraction=extraction.model_copy(update={"rules": extraction.rules[:12]}),
        )
    )
    assert compiled.policy.unsupported_clauses == result.extraction.unsupported_clauses
    assert compiled.policy.rules == capped.policy.rules


@pytest.mark.parametrize("max_rules", [4, 12])
def test_rule_cap_preserves_excluded_override_chain_and_closes_retained_graph(
    max_rules: int,
) -> None:
    document, extraction = _extraction(max_rules + 1)
    rules = list(extraction.rules)
    for source, target in (
        (0, 1),
        (max_rules - 2, max_rules - 1),
        (max_rules - 1, max_rules),
    ):
        rules[source] = rules[source].model_copy(
            update={
                "overrides": (
                    OverrideRef(
                        dimension="receipt_requirement",
                        target_rule_id=rules[target].provenance.citation_id,
                    ),
                )
            }
        )
    extraction = extraction.model_copy(update={"rules": tuple(rules)})

    result = validate_policy_extraction(document, extraction, max_rules=max_rules)

    assert len(result.extraction.rules) == max_rules - 2
    assert result.excluded_rule_count == 3
    clauses = result.extraction.unsupported_clauses
    assert len(clauses) == 3
    assert {clause.span for clause in clauses} == {
        rule.provenance.span for rule in rules[-3:]
    }
    assert all(clause.reason_code == "unsupported_logic" for clause in clauses)
    assert all(clause.review_status == "provisional" for clause in clauses)
    for clause in clauses:
        original = next(rule for rule in rules if rule.provenance.span == clause.span)
        assert clause.when_hint == original.when
        assert clause.affected_dimensions == frozenset(
            effect.dimension for effect in original.effects
        )
    compiled = compile_baseline_policy(
        CompilePolicyRequest(document=document, extraction=result.extraction)
    )
    assert compiled.policy.rules[0].overrides[0].target_rule_id == (
        compiled.policy.rules[1].rule_id
    )
    assert compiled.policy.unsupported_clauses == clauses
