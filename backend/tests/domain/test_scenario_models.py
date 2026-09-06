import pytest
from pydantic import ValidationError

from app.domain.models import ScenarioSuite

from .factories import (
    make_assertion,
    make_facts,
    make_scenario,
    make_scenario_candidate,
    make_scenario_suite,
)


def test_llm_exploratory_candidate_cannot_supply_scored_assertion():
    with pytest.raises(ValidationError):
        make_scenario_candidate(assertions=(make_assertion(),))


def test_merged_origins_preserve_independent_assertions():
    candidate = make_scenario_candidate(
        origins=frozenset({"mechanical", "llm_exploratory"}),
        assertions=(
            make_assertion(
                origin="mechanical",
                source_invariant_id=None,
                mechanical_relation_id="relation-1",
            ),
        ),
    )
    assert len(candidate.assertions) == 1
    assert candidate.model_validate_json(candidate.model_dump_json()) == candidate


@pytest.mark.parametrize(
    "changes",
    [
        {"amount_minor": True},
        {"amount_minor": 0.5},
        {"amount_minor": 10_000_001},
        {"booking_days_before": 366},
        {"receipt_present": 1},
        {"approval_roles_present": frozenset({"executive"})},
        {"daily_category_total_minor": 5000},
    ],
)
def test_facts_reject_invalid_or_derived_stored_data(changes):
    with pytest.raises(ValidationError):
        make_facts(**changes)


def test_suite_rejects_sixteen_scenarios_and_duplicate_ids():
    with pytest.raises(ValidationError):
        make_scenario_suite(tuple(make_scenario(i) for i in range(16)))
    with pytest.raises(ValidationError):
        make_scenario_suite((make_scenario(), make_scenario()))


def test_suite_round_trip_preserves_frozen_collections():
    suite = make_scenario_suite(tuple(make_scenario(i) for i in range(15)))
    restored = ScenarioSuite.model_validate_json(suite.model_dump_json())
    assert restored == suite
    assert isinstance(restored.scenarios[0].facts.approval_roles_present, frozenset)
    with pytest.raises(AttributeError):
        restored.scenarios[0].origins.add("gold")


def test_set_inputs_are_frozen_without_retaining_mutable_aliases():
    origins = {"llm_exploratory"}
    candidate = make_scenario_candidate(origins=origins)
    origins.add("gold")
    assert candidate.origins == frozenset({"llm_exploratory"})
    with pytest.raises(ValidationError):
        make_scenario_candidate(origins=["llm_exploratory"])


def test_coverage_cannot_report_impossible_or_incomplete_success():
    from app.domain.models import (
        CoverageEvidence,
        CoverageSnapshot,
        GenerateTargetedScenariosRequest,
    )

    from .factories import make_policy, make_policy_contract

    with pytest.raises(ValidationError):
        CoverageSnapshot(total_rules=1, covered_rules=2)
    with pytest.raises(ValidationError):
        CoverageSnapshot(total_rules=1, covered_rules=0, status="satisfied")
    with pytest.raises(ValidationError):
        CoverageEvidence(
            target_kind="predicate_branch", target_id="rule-meal", scenario_ids=()
        )
    with pytest.raises(ValidationError):
        GenerateTargetedScenariosRequest(
            policy=make_policy(),
            contract=make_policy_contract(),
            seed=0,
            existing_candidates=(),
            coverage=CoverageSnapshot(),
            targeted_cycle=True,
        )
