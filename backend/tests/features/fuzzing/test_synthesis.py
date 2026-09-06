"""Deterministic mechanical scenario synthesis."""

import pytest

from app.domain.models import Predicate
from app.features.fuzzing.synthesis import (
    build_initial_mechanical_candidates,
    numeric_triplet,
    satisfy_conditions,
)
from tests.domain.factories import (
    make_invariant,
    make_policy,
    make_policy_contract,
    make_rule,
)


def test_numeric_triplet_is_exact_and_ordered() -> None:
    assert numeric_triplet(5_000, minimum=0, maximum=10_000_000) == (
        4_999,
        5_000,
        5_001,
    )


def test_numeric_triplet_omits_out_of_domain_values_instead_of_clamping() -> None:
    assert numeric_triplet(0, minimum=0, maximum=365) == (0, 1)
    assert numeric_triplet(365, minimum=0, maximum=365) == (364, 365)


def test_satisfy_conditions_solves_typed_fields_and_rejects_conflicts() -> None:
    facts = satisfy_conditions(
        (
            Predicate(field="expense_category", operator="eq", value="hotel"),
            Predicate(field="amount_minor", operator="gte", value=5_000),
            Predicate(
                field="approval_roles_present", operator="contains", value="finance"
            ),
        ),
        seed=42,
    )
    assert facts is not None
    assert facts.expense_category == "hotel"
    assert facts.amount_minor >= 5_000
    assert facts.approval_roles_present == frozenset({"finance"})

    impossible = satisfy_conditions(
        (
            Predicate(field="receipt_present", operator="eq", value=True),
            Predicate(field="receipt_present", operator="eq", value=False),
        ),
        seed=42,
    )
    assert impossible is None


def test_initial_candidates_include_all_exact_numeric_boundaries() -> None:
    rule = make_rule(
        rule_id="rule-threshold",
        when=(Predicate(field="amount_minor", operator="lte", value=5_000),),
    )
    policy = make_policy(rules=(rule,))
    candidates = build_initial_mechanical_candidates(
        policy, make_policy_contract(), seed=42
    )
    values = {
        candidate.facts.amount_minor
        for candidate in candidates
        if candidate.category == "boundary"
        and "rule-threshold" in candidate.target_rule_ids
    }
    assert values == {4_999, 5_000, 5_001}
    assert all(
        candidate.facts.model_fields_set
        == {
            "employee_role",
            "expense_category",
            "amount_minor",
            "destination_type",
            "booking_days_before",
            "receipt_present",
            "approval_roles_present",
            "prior_same_day_category_spend_minor",
        }
        for candidate in candidates
    )


def test_daily_total_witness_uses_both_amount_fields() -> None:
    invariant = make_invariant(
        0,
        invariant_id="daily-meal-limit",
        when=(
            Predicate(field="daily_category_total_minor", operator="gt", value=10_000),
        ),
        assertion=make_invariant(0).assertion.model_copy(
            update={"source_invariant_id": "daily-meal-limit"}
        ),
    )
    contract = make_policy_contract(
        invariants=(invariant, make_invariant(1), make_invariant(2))
    )
    candidates = build_initial_mechanical_candidates(make_policy(), contract, seed=42)
    witness = next(
        case for case in candidates if "daily-meal-limit" in case.target_invariant_ids
    )
    assert (
        witness.facts.amount_minor + witness.facts.prior_same_day_category_spend_minor
        > 10_000
    )
    assert witness.assertions == (invariant.assertion,)
    assert witness.protected is True


def test_invariant_boundary_neighbors_do_not_carry_out_of_scope_assertions() -> None:
    invariant = make_invariant(
        0,
        when=(Predicate(field="amount_minor", operator="eq", value=5_000),),
    )
    contract = make_policy_contract(
        invariants=(invariant, make_invariant(1), make_invariant(2))
    )
    candidates = build_initial_mechanical_candidates(make_policy(), contract, seed=42)

    neighbors = [
        item
        for item in candidates
        if item.category == "boundary"
        and "invariant-0" in item.target_invariant_ids
        and item.facts.amount_minor != 5_000
    ]
    assert {item.facts.amount_minor for item in neighbors} == {4_999, 5_001}
    assert all(item.assertions == () and item.protected is False for item in neighbors)


@pytest.mark.parametrize(
    ("conditions", "expected_total"),
    (
        (
            (
                Predicate(field="amount_minor", operator="lt", value=6_000_000),
                Predicate(
                    field="prior_same_day_category_spend_minor",
                    operator="lt",
                    value=10_000_000,
                ),
                Predicate(
                    field="daily_category_total_minor",
                    operator="eq",
                    value=15_000_000,
                ),
            ),
            15_000_000,
        ),
        (
            (
                Predicate(field="amount_minor", operator="gte", value=5_000_000),
                Predicate(
                    field="prior_same_day_category_spend_minor",
                    operator="gte",
                    value=10_000_000,
                ),
                Predicate(
                    field="daily_category_total_minor",
                    operator="lt",
                    value=15_000_001,
                ),
            ),
            15_000_000,
        ),
        (
            (
                Predicate(field="amount_minor", operator="gt", value=5_000_000),
                Predicate(
                    field="prior_same_day_category_spend_minor",
                    operator="gte",
                    value=9_999_999,
                ),
                Predicate(
                    field="daily_category_total_minor",
                    operator="lte",
                    value=15_000_000,
                ),
            ),
            15_000_000,
        ),
    ),
)
def test_coupled_daily_total_solver_handles_component_constraints(
    conditions: tuple[Predicate, ...], expected_total: int
) -> None:
    facts = satisfy_conditions(conditions, seed=42)

    assert facts is not None
    assert (
        facts.amount_minor + facts.prior_same_day_category_spend_minor == expected_total
    )
