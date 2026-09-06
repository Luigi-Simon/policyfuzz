import pytest
from pydantic import ValidationError

from app.domain.models import EffectDimension, OverrideRef, Predicate, UnsupportedClause
from app.features.evaluation.engine import (
    DeterministicEvaluationEngine,
    evaluate_scenario,
)
from app.features.evaluation.predicates import evaluate_predicate
from app.features.evaluation.rule_validation import validate_rule_set


@pytest.mark.parametrize(
    "field,operator,value,actual,expected",
    [
        ("employee_role", "eq", "manager", "manager", True),
        ("employee_role", "neq", "manager", "employee", True),
        ("expense_category", "in", ("meal", "hotel"), "meal", True),
        ("expense_category", "not_in", ("meal", "hotel"), "meal", False),
        ("amount_minor", "lt", 5000, 4999, True),
        ("amount_minor", "lte", 5000, 5000, True),
        ("amount_minor", "gt", 5000, 5000, False),
        ("amount_minor", "gte", 5000, 5000, True),
        (
            "approval_roles_present",
            "contains",
            "manager",
            frozenset({"director"}),
            False,
        ),
        ("receipt_present", "eq", True, False, False),
    ],
)
def test_typed_operator(facts, field, operator, value, actual, expected):
    assert (
        evaluate_predicate(
            Predicate(field=field, operator=operator, value=value),
            facts.model_copy(update={field: actual}),
        ).matched
        is expected
    )


@pytest.mark.parametrize("actual", [True, 2.5, "5000", None])
def test_no_fact_coercion(facts, actual):
    with pytest.raises((ValueError, TypeError, ValidationError)):
        evaluate_predicate(
            Predicate(field="amount_minor", operator="eq", value=5000),
            facts.model_copy(update={"amount_minor": actual}),
        )


def test_unsatisfiable_rejected(policy_factory, rule_factory):
    rule = rule_factory(
        when=(
            Predicate(field="amount_minor", operator="gt", value=5000),
            Predicate(field="amount_minor", operator="lte", value=5000),
        )
    )
    with pytest.raises(ValueError, match="UNSATISFIABLE"):
        validate_rule_set(policy_factory([rule]))


def test_conflict_and_simultaneous_override(
    policy_factory, rule_factory, contract, scenario_factory
):
    rules = [rule_factory("a", value="allow"), rule_factory("b", value="deny")]
    result = evaluate_scenario(policy_factory(rules), contract, scenario_factory())
    assert result.trace.resolved_effects[0].status == "CONFLICT"
    rules[0] = rules[0].model_copy(
        update={
            "overrides": (OverrideRef(dimension="eligibility", target_rule_id="b"),)
        }
    )
    result = evaluate_scenario(policy_factory(rules), contract, scenario_factory())
    assert result.trace.resolved_effects[0].value == "allow"
    assert result.trace.resolved_effects[0].overridden_rule_ids == ("b",)


def test_replay_and_order_and_no_short_circuit(
    request_factory, rule_factory, policy_factory
):
    p = policy_factory(
        [
            rule_factory(
                when=(
                    Predicate(field="amount_minor", operator="gt", value=6000),
                    Predicate(field="receipt_present", operator="eq", value=False),
                )
            )
        ]
    )
    request = request_factory(p)
    reports = [DeterministicEvaluationEngine().evaluate(request) for _ in range(3)]
    assert reports[0] == reports[1] == reports[2]
    trace = reports[0].results[0].trace
    assert [d.dimension for d in trace.resolved_effects] == [
        d.value for d in EffectDimension
    ]
    assert len(trace.predicate_results) == 2
    assert trace.resolved_effects[0].status == "GAP"
    assert reports[0].coverage.covered_predicate_branches == 2


def test_receipt_compliance_does_not_deny(
    policy_factory, rule_factory, contract, scenario_factory
):
    result = evaluate_scenario(
        policy_factory(
            [rule_factory(), rule_factory("r2", "receipt_requirement", "required")]
        ),
        contract,
        scenario_factory(),
    )
    assert result.trace.resolved_effects[0].value == "allow"
    assert result.trace.compliance_values[0].status == "NONCOMPLIANT"


def test_anchor_rejected(request_factory):
    request = request_factory()
    request = request.model_copy(
        update={"inputs": request.inputs.model_copy(update={"suite_sha256": "f" * 64})}
    )
    with pytest.raises(ValueError, match="HASH_MISMATCH"):
        DeterministicEvaluationEngine().evaluate(request)


def test_unsupported_hint_scope(
    policy_factory, rule_factory, contract, scenario_factory
):
    clause = UnsupportedClause(
        clause_id="u1",
        span=rule_factory().provenance.span,
        reason_code="ambiguous_language",
        affected_dimensions=frozenset({"eligibility"}),
        when_hint=(Predicate(field="expense_category", operator="eq", value="hotel"),),
    )
    policy = policy_factory(unsupported_clauses=(clause,))
    assert (
        evaluate_scenario(policy, contract, scenario_factory())
        .trace.resolved_effects[0]
        .status
        == "VALUE"
    )
    policy = policy.model_copy(
        update={"unsupported_clauses": (clause.model_copy(update={"when_hint": None}),)}
    )
    assert (
        evaluate_scenario(policy, contract, scenario_factory())
        .trace.resolved_effects[0]
        .status
        == "INCONCLUSIVE"
    )


@pytest.mark.parametrize(
    "dimension,value,updates,expected",
    [
        (
            "approval_requirement",
            "manager",
            {"approval_roles_present": frozenset({"director"})},
            "COMPLIANT",
        ),
        (
            "approval_requirement",
            "finance",
            {"approval_roles_present": frozenset({"director"})},
            "NONCOMPLIANT",
        ),
        ("claim_cap_minor", 5000, {}, "COMPLIANT"),
        ("claim_cap_minor", 4999, {}, "NONCOMPLIANT"),
        (
            "daily_category_cap_minor",
            10000,
            {"prior_same_day_category_spend_minor": 5001},
            "NONCOMPLIANT",
        ),
        (
            "daily_category_cap_minor",
            10000,
            {"prior_same_day_category_spend_minor": 5000},
            "COMPLIANT",
        ),
    ],
)
def test_compliance_boundaries(facts, dimension, value, updates, expected):
    from app.features.evaluation.compliance import derive_compliance

    assert (
        derive_compliance(dimension, value, facts.model_copy(update=updates)).status
        == expected
    )


def test_override_chain_removes_simultaneously(
    policy_factory, rule_factory, contract, scenario_factory
):
    rules = [
        rule_factory(
            "a",
            value="allow",
            overrides=(OverrideRef(dimension="eligibility", target_rule_id="b"),),
        ),
        rule_factory(
            "b",
            value="deny",
            overrides=(OverrideRef(dimension="eligibility", target_rule_id="c"),),
        ),
        rule_factory("c", value="deny"),
    ]
    result = evaluate_scenario(policy_factory(rules), contract, scenario_factory())
    assert result.trace.resolved_effects[0].value == "allow"
    assert result.trace.resolved_effects[0].overridden_rule_ids == ("b", "c")


def test_malformed_scenario_visible_error(
    policy_factory, contract, scenario_factory, facts
):
    scenario = scenario_factory().model_copy(
        update={"facts": facts.model_copy(update={"amount_minor": True})}
    )
    result = evaluate_scenario(policy_factory(), contract, scenario)
    assert result.verdict == "ERROR"
    assert all(d.status == "ERROR" for d in result.trace.resolved_effects)


@pytest.mark.parametrize(
    "operator,expected_value,status",
    [
        ("eq", 5000, "PASS"),
        ("neq", 5000, "FAIL"),
        ("lte", 4999, "FAIL"),
        ("gte", 5000, "PASS"),
    ],
)
def test_assertion_operators(operator, expected_value, status):
    from app.domain.models import Assertion, DimensionResult
    from app.features.evaluation.assertions import evaluate_assertion

    assertion = Assertion(
        assertion_id="a",
        target_kind="effect_value",
        dimension="claim_cap_minor",
        operator=operator,
        expected_value=expected_value,
        origin="gold",
        gold_label_id="g",
    )
    result = evaluate_assertion(
        assertion,
        (DimensionResult(dimension="claim_cap_minor", status="VALUE", value=5000),),
    )
    assert result.status == status
