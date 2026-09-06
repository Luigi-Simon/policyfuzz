"""Coverage derives only from evaluator-produced evidence."""

from app.domain.models import CoverageEvidence, Predicate
from app.features.fuzzing.coverage import (
    adaptation_lift,
    analyze_coverage,
    required_coverage_complete,
)
from tests.domain.factories import make_policy, make_policy_contract, make_rule


def test_declared_targets_do_not_count_as_measured_coverage() -> None:
    policy = make_policy(
        rules=(
            make_rule(
                when=(Predicate(field="amount_minor", operator="gte", value=5_000),)
            ),
        )
    )
    snapshot = analyze_coverage(policy, make_policy_contract(), ())

    assert snapshot.covered_rules == 0
    assert snapshot.covered_invariants == 0
    assert snapshot.covered_predicate_branches == 0
    assert snapshot.missing_rule_ids == ("rule-meal",)
    assert required_coverage_complete(snapshot) is False


def test_measured_evidence_is_deduplicated_and_invalid_coordinates_ignored() -> None:
    policy = make_policy(
        rules=(
            make_rule(
                when=(Predicate(field="amount_minor", operator="gte", value=5_000),)
            ),
        )
    )
    evidence = (
        CoverageEvidence(
            target_kind="rule", target_id="rule-meal", scenario_ids=("s1",)
        ),
        CoverageEvidence(
            target_kind="rule", target_id="rule-meal", scenario_ids=("s2",)
        ),
        CoverageEvidence(
            target_kind="invariant", target_id="invariant-0", scenario_ids=("s1",)
        ),
        CoverageEvidence(
            target_kind="predicate_branch",
            target_id="rule-meal",
            predicate_index=0,
            predicate_outcome=True,
            scenario_ids=("s1",),
        ),
        CoverageEvidence(
            target_kind="predicate_branch",
            target_id="rule-meal",
            predicate_index=3,
            predicate_outcome=False,
            scenario_ids=("s1",),
        ),
    )
    snapshot = analyze_coverage(policy, make_policy_contract(), evidence)

    assert snapshot.covered_rules == 1
    assert snapshot.covered_invariants == 1
    assert snapshot.covered_predicate_branches == 1
    rule_evidence = next(
        item for item in snapshot.evidence if item.target_kind == "rule"
    )
    assert rule_evidence.scenario_ids == ("s1", "s2")


def test_complete_coverage_and_adaptation_lift_count_required_targets() -> None:
    policy = make_policy()
    contract = make_policy_contract()
    initial = analyze_coverage(
        policy,
        contract,
        (
            CoverageEvidence(
                target_kind="rule", target_id="rule-meal", scenario_ids=("s1",)
            ),
        ),
    )
    final = analyze_coverage(
        policy,
        contract,
        (
            CoverageEvidence(
                target_kind="rule", target_id="rule-meal", scenario_ids=("s1",)
            ),
            *(
                CoverageEvidence(
                    target_kind="invariant",
                    target_id=f"invariant-{index}",
                    scenario_ids=(f"s{index + 2}",),
                )
                for index in range(3)
            ),
        ),
    )

    assert required_coverage_complete(final) is True
    assert final.status == "satisfied"
    assert adaptation_lift(initial, final) == 3
