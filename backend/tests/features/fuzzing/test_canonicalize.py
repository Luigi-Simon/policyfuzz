"""Deterministic validation, deduplication, selection and stable IDs."""

from app.domain.models import Predicate, ScenarioCandidate
from app.features.fuzzing.canonicalize import (
    canonicalize_with_rejections,
    fact_sha256,
    materialize_scenario,
)
from tests.domain.factories import (
    make_facts,
    make_invariant,
    make_policy,
    make_policy_contract,
    make_scenario_candidate,
)


def canonicalize(candidates, *, capacity=15, used=frozenset(), contract=None):
    return canonicalize_with_rejections(
        kind="initial",
        candidates=tuple(candidates),
        prior_rejections=(),
        policy=make_policy(),
        contract=contract or make_policy_contract(),
        capacity=capacity,
        requested_rule_ids=frozenset({"rule-meal"}),
        requested_invariant_ids=frozenset(
            {"invariant-0", "invariant-1", "invariant-2"}
        ),
        used_fact_sha256s=used,
    )


def test_identical_facts_merge_origins_and_keep_boundary_priority() -> None:
    mechanical = make_scenario_candidate(
        candidate_id="mechanical",
        category="normal",
        origins=frozenset({"mechanical"}),
        target_rule_ids=("rule-meal",),
    )
    llm = make_scenario_candidate(
        candidate_id="llm",
        category="boundary",
        origins=frozenset({"llm_exploratory"}),
        target_invariant_ids=("invariant-0",),
    )
    result = canonicalize((mechanical, llm))

    assert len(result.batch.candidates) == 1
    assert result.batch.candidates[0].origins == frozenset(
        {"mechanical", "llm_exploratory"}
    )
    assert result.batch.candidates[0].category == "boundary"
    assert result.batch.candidates[0].target_rule_ids == ("rule-meal",)
    assert result.batch.candidates[0].target_invariant_ids == ("invariant-0",)
    assert sum(item.reason_code == "duplicate" for item in result.rejections) == 1


def test_capacity_keeps_rejected_candidate_visible() -> None:
    candidates = tuple(
        make_scenario_candidate(
            candidate_id=f"candidate-{index}",
            facts=make_facts(amount_minor=100 + index),
        )
        for index in range(16)
    )
    result = canonicalize(candidates, capacity=15)

    assert len(result.batch.candidates) == 15
    assert sum(item.reason_code == "budget_exceeded" for item in result.rejections) == 1


def test_unknown_targets_and_already_used_facts_remain_visible() -> None:
    unknown = make_scenario_candidate(
        candidate_id="unknown", target_rule_ids=("missing-rule",)
    )
    used_candidate = make_scenario_candidate(
        candidate_id="used", facts=make_facts(amount_minor=999)
    )
    result = canonicalize(
        (unknown, used_candidate), used=frozenset({fact_sha256(used_candidate.facts)})
    )

    assert result.batch.candidates == ()
    assert [item.candidate_id for item in result.rejections] == ["unknown", "used"]
    assert [item.reason_code for item in result.rejections] == [
        "invalid_facts",
        "duplicate",
    ]


def test_assertion_claiming_session_origin_must_equal_confirmed_contract() -> None:
    assertion = (
        make_policy_contract()
        .invariants[0]
        .assertion.model_copy(update={"expected_value": 4_000})
    )
    candidate = make_scenario_candidate(
        candidate_id="llm-oracle",
        origins=frozenset({"llm_exploratory", "session"}),
        assertions=(assertion,),
        target_invariant_ids=("invariant-0",),
        protected=True,
    )
    result = canonicalize((candidate,))

    assert result.batch.candidates == ()
    assert result.rejections[0].reason_code == "invalid_assertion"


def test_confirmed_assertion_requires_invariant_to_apply_to_candidate_facts() -> None:
    invariant = make_invariant(
        when=(Predicate(field="amount_minor", operator="eq", value=5_000),)
    )
    contract = make_policy_contract(
        invariants=(invariant, make_invariant(1), make_invariant(2))
    )
    candidate = make_scenario_candidate(
        candidate_id="inapplicable-assertion",
        origins=frozenset({"mechanical", "session"}),
        facts=make_facts(amount_minor=4_999),
        assertions=(invariant.assertion,),
        target_invariant_ids=(invariant.invariant_id,),
        protected=True,
    )

    result = canonicalize((candidate,), contract=contract)

    assert result.batch.candidates == ()
    assert result.rejections[0].reason_code == "invalid_assertion"


def test_confirmed_assertion_requires_source_invariant_as_a_target() -> None:
    invariant = make_invariant()
    contract = make_policy_contract(
        invariants=(invariant, make_invariant(1), make_invariant(2))
    )
    candidate = make_scenario_candidate(
        candidate_id="untargeted-assertion",
        origins=frozenset({"mechanical", "session"}),
        assertions=(invariant.assertion,),
        protected=True,
    )

    result = canonicalize((candidate,), contract=contract)

    assert result.batch.candidates == ()
    assert result.rejections[0].reason_code == "invalid_assertion"


def test_scenario_id_ignores_origin_category_candidate_id_and_input_order() -> None:
    first = make_scenario_candidate(
        candidate_id="first",
        origins=frozenset({"mechanical"}),
        category="normal",
        target_rule_ids=("rule-meal",),
    )
    second = ScenarioCandidate(
        **first.model_dump(exclude={"candidate_id", "origins", "category"}),
        candidate_id="second",
        origins=frozenset({"llm_exploratory"}),
        category="boundary",
    )
    merged_a = canonicalize((first, second)).batch.candidates[0]
    merged_b = canonicalize((second, first)).batch.candidates[0]

    assert (
        materialize_scenario(merged_a).scenario_id
        == materialize_scenario(merged_b).scenario_id
    )


def test_selection_prefers_protected_then_adds_category_diversity() -> None:
    protected = make_scenario_candidate(
        candidate_id="protected",
        origins=frozenset({"session"}),
        category="normal",
        facts=make_facts(amount_minor=1),
        assertions=(make_policy_contract().invariants[0].assertion,),
        target_invariant_ids=("invariant-0",),
        protected=True,
    )
    boundary = make_scenario_candidate(
        candidate_id="boundary",
        category="boundary",
        facts=make_facts(amount_minor=2),
    )
    other_normal = make_scenario_candidate(
        candidate_id="normal", category="normal", facts=make_facts(amount_minor=3)
    )
    result = canonicalize((other_normal, boundary, protected), capacity=2)

    assert {item.candidate_id for item in result.batch.candidates} == {
        "candidate-"
        + materialize_scenario(protected).scenario_id.removeprefix("scenario-"),
        "candidate-"
        + materialize_scenario(boundary).scenario_id.removeprefix("scenario-"),
    }
