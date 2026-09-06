import pytest
from pydantic import ValidationError

from app.domain.models import (
    Effect,
    EffectDimension,
    PolicyDocument,
    PolicyIR,
    PolicyPage,
    Predicate,
    Rule,
    SessionRevisionProvenance,
    SourceSpan,
)

from .factories import (
    HASH,
    make_assertion,
    make_invariant,
    make_policy,
    make_policy_contract,
    make_rule,
)


@pytest.mark.parametrize(
    "field,operator,value",
    [
        ("amount_minor", "contains", 100),
        ("amount_minor", "gte", True),
        ("amount_minor", "gte", 100.0),
        ("amount_minor", "eq", 10_000_001),
        ("booking_days_before", "lt", 366),
        ("receipt_present", "eq", 1),
        ("employee_role", "eq", "finance"),
        ("employee_role", "in", ("employee", "finance")),
        ("employee_role", "in", ()),
        ("approval_roles_present", "contains", "executive"),
        ("daily_category_total_minor", "eq", 20_000_001),
        ("unknown", "eq", "x"),
    ],
)
def test_predicate_rejects_wrong_domain_operator_or_scalar_type(field, operator, value):
    with pytest.raises(ValidationError):
        Predicate(field=field, operator=operator, value=value)


@pytest.mark.parametrize(
    "field,operator,value",
    [
        ("amount_minor", "gte", 5000),
        ("booking_days_before", "lte", 365),
        ("receipt_present", "eq", True),
        ("employee_role", "in", ("employee", "director")),
        ("approval_roles_present", "contains", "finance"),
        ("daily_category_total_minor", "eq", 20_000_000),
    ],
)
def test_predicate_accepts_typed_vocabulary_and_round_trips(field, operator, value):
    predicate = Predicate(field=field, operator=operator, value=value)
    assert Predicate.model_validate_json(predicate.model_dump_json()) == predicate


@pytest.mark.parametrize(
    "dimension,value",
    [
        ("eligibility", "required"),
        ("claim_cap_minor", True),
        ("claim_cap_minor", 1.0),
        ("daily_category_cap_minor", -1),
        ("approval_requirement", "executive"),
    ],
)
def test_effect_rejects_incompatible_value(dimension, value):
    with pytest.raises(ValidationError):
        Effect(dimension=dimension, value=value)


def test_effect_exported_enum_and_string_constructors_agree():
    assert Effect(dimension=EffectDimension.ELIGIBILITY, value="allow") == Effect(
        dimension="eligibility", value="allow"
    )


@pytest.mark.parametrize("count", [0, 2, 6])
def test_policy_contract_requires_three_to_five_invariants(count):
    with pytest.raises(ValidationError):
        make_policy_contract(invariants=tuple(make_invariant(i) for i in range(count)))


def test_derived_daily_total_is_invariant_only():
    condition = Predicate(field="daily_category_total_minor", operator="gt", value=5000)
    assert make_invariant(when=(condition,)).when == (condition,)
    with pytest.raises(ValidationError):
        make_rule(when=(condition,))


def test_baseline_rejects_session_revision_provenance():
    provenance = SessionRevisionProvenance(
        proposal_id="p1",
        operation_index=0,
        confirmed_at="2026-09-06T00:00:00Z",
        baseline_citation_ids=("citation-meal",),
    )
    rule = make_rule(provenance=provenance, revision=1)
    with pytest.raises(ValidationError):
        make_policy(rules=(rule,))
    assert make_policy(kind="structured_revision", rules=(rule,)).rules == (rule,)


@pytest.mark.parametrize(
    "operator,value", [("lte", "allow"), ("eq", True), ("eq", 1.5)]
)
def test_assertion_rejects_incompatible_effect_assertion(operator, value):
    with pytest.raises(ValidationError):
        make_assertion(dimension="eligibility", operator=operator, expected_value=value)


def test_compliance_assertions_have_finite_values_and_dimensions():
    assertion = make_assertion(
        target_kind="compliance_value", operator="eq", expected_value="COMPLIANT"
    )
    assert assertion.expected_value == "COMPLIANT"
    with pytest.raises(ValidationError):
        make_assertion(
            target_kind="compliance_value",
            dimension="eligibility",
            operator="eq",
            expected_value="COMPLIANT",
        )


def test_scored_assertion_requires_independent_reference():
    with pytest.raises(ValidationError):
        make_assertion(source_invariant_id=None)
    with pytest.raises(ValidationError):
        make_assertion(origin="llm_exploratory")


def test_source_spans_and_pages_validate_ranges_without_hashing():
    span = SourceSpan(page=1, start=5, end=8, quote="abc", quote_sha256=HASH)
    assert span.section is None
    with pytest.raises(ValidationError):
        SourceSpan(page=1, start=8, end=5, quote="abc", quote_sha256=HASH)
    with pytest.raises(ValidationError):
        PolicyPage(page=1, text="abc", start=8, end=5)
    with pytest.raises(ValidationError):
        PolicyDocument(
            document_id="d",
            title="Title",
            source_type="pdf",
            pages=(),
            document_sha256=HASH,
        )


def test_nested_contracts_are_immutable_and_forbid_unknown_fields():
    policy = make_policy()
    assert isinstance(policy.rules, tuple)
    assert (
        Rule.model_validate_json(policy.rules[0].model_dump_json()) == policy.rules[0]
    )
    with pytest.raises(ValidationError):
        policy.rules[0].description = "changed"
    with pytest.raises(ValidationError):
        make_rule(confidence_percent=95.5)
    with pytest.raises(ValidationError):
        make_rule(unchecked={"anything": []})
    assert (
        make_policy_contract().model_validate_json(
            make_policy_contract().model_dump_json()
        )
        == make_policy_contract()
    )


def test_rule_set_rejects_dangling_cross_dimension_and_cyclic_overrides():
    from app.domain.models import OverrideRef

    with pytest.raises(ValidationError):
        make_policy(
            rules=(
                make_rule(
                    overrides=(
                        OverrideRef(
                            dimension="claim_cap_minor", target_rule_id="missing"
                        ),
                    )
                ),
            )
        )
    with pytest.raises(ValidationError):
        make_rule(
            overrides=(
                OverrideRef(dimension="eligibility", target_rule_id="rule-other"),
            )
        )
    first = make_rule(
        overrides=(
            OverrideRef(dimension="claim_cap_minor", target_rule_id="rule-other"),
        )
    )
    second = make_rule(
        rule_id="rule-other",
        overrides=(
            OverrideRef(dimension="claim_cap_minor", target_rule_id="rule-meal"),
        ),
    )
    with pytest.raises(ValidationError):
        make_policy(rules=(first, second))
    valid = make_policy(rules=(first, make_rule(rule_id="rule-other")))
    assert valid.model_validate_json(valid.model_dump_json()) == valid


def test_policy_rejects_duplicate_rule_invariant_and_assertion_ids():
    with pytest.raises(ValidationError):
        make_policy(rules=(make_rule(), make_rule()))
    with pytest.raises(ValidationError):
        make_policy_contract(invariants=(make_invariant(),) * 3)
    with pytest.raises(ValidationError):
        make_policy_contract(
            invariants=tuple(
                make_invariant(
                    i, assertion=make_assertion(source_invariant_id=f"invariant-{i}")
                )
                for i in range(3)
            )
        )


def test_structured_revision_provenance_requires_aware_timestamp_and_citations():
    for changes in (
        {"confirmed_at": "2026-09-06T00:00:00"},
        {"baseline_citation_ids": ()},
        {"operation_index": 3},
    ):
        values = {
            "proposal_id": "p1",
            "operation_index": 0,
            "confirmed_at": "2026-09-06T00:00:00Z",
            "baseline_citation_ids": ("c1",),
        }
        with pytest.raises(ValidationError):
            SessionRevisionProvenance(**(values | changes))


@pytest.mark.parametrize("kind", ["compiled_baseline", "structured_revision"])
def test_policy_rule_budget_applies_to_baseline_and_revision(kind):
    rules = tuple(make_rule(rule_id=f"rule-{index}") for index in range(13))
    assert len(make_policy(kind=kind, rules=rules[:12]).rules) == 12
    with pytest.raises(ValidationError):
        make_policy(kind=kind, rules=rules)
    assert PolicyIR.model_json_schema()["properties"]["rules"]["maxItems"] == 12
