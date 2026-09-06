"""Frozen-contract ScenarioPlanner limits, adaptation and suite hashing."""

from datetime import UTC, datetime
from types import SimpleNamespace

import pytest

from app.core.fakes import ScriptedLLMClient
from app.domain.models import (
    AssembleSuiteRequest,
    CoverageSnapshot,
    GenerateInitialScenariosRequest,
    GenerateTargetedScenariosRequest,
    GenerationConfig,
    LLMResponse,
    Predicate,
    RunManifest,
)
from app.domain.protocols import ScenarioPlanner
from app.features.fuzzing.canonicalize import fact_sha256
from app.features.fuzzing.exploratory import exploratory_response_example
from app.features.fuzzing.planner import (
    CoverageLimitExceededError,
    DefaultScenarioPlanner,
)
from app.features.fuzzing.prompts import exploratory_prompt_commitment
from app.workflow.coordinator import RunCoordinator
from tests.domain.factories import (
    make_assertion,
    make_facts,
    make_policy,
    make_policy_contract,
    make_scenario_candidate,
)

HASH = "a" * 64


def manifest() -> RunManifest:
    return RunManifest(
        manifest_id="manifest-1",
        run_id="run-1",
        engine_version="1.0",
        engine_sha256="e" * 64,
        prompt_hashes=(exploratory_prompt_commitment(),),
        provider="scripted",
        model_identifier="scripted-model",
        generation_config=GenerationConfig(),
        random_seed=42,
        started_at=datetime(2026, 9, 6, tzinfo=UTC),
        mode="cached",
    )


def initial_request() -> GenerateInitialScenariosRequest:
    return GenerateInitialScenariosRequest(
        policy=make_policy(),
        contract=make_policy_contract(),
        seed=42,
        scenario_budget=15,
    )


def assemble_request(candidates) -> AssembleSuiteRequest:
    return AssembleSuiteRequest(
        suite_id="suite-1",
        document_sha256=HASH,
        policy_contract_sha256=HASH,
        rule_set_sha256=HASH,
        engine_version="1.0",
        seed=42,
        candidates=tuple(candidates),
    )


@pytest.mark.asyncio
async def test_initial_generation_reserves_targeted_capacity() -> None:
    planner = DefaultScenarioPlanner()
    batch = await planner.generate_initial(initial_request())

    assert isinstance(planner, ScenarioPlanner)
    assert 1 <= len(batch.candidates) <= 10


@pytest.mark.asyncio
async def test_every_matching_confirmed_invariant_assertion_is_frozen() -> None:
    policy = make_policy(
        rules=(
            make_policy()
            .rules[0]
            .model_copy(
                update={
                    "when": (
                        Predicate(field="amount_minor", operator="gte", value=5_000),
                    )
                }
            ),
        )
    )
    contract = make_policy_contract()
    batch = await DefaultScenarioPlanner().generate_initial(
        GenerateInitialScenariosRequest(
            policy=policy, contract=contract, seed=42, scenario_budget=10
        )
    )

    expected = {item.assertion.assertion_id for item in contract.invariants}
    assert len(batch.candidates) > 1
    assert all(
        {item.assertion_id for item in candidate.assertions} == expected
        and "session" in candidate.origins
        for candidate in batch.candidates
    )


@pytest.mark.asyncio
async def test_incompatible_assertion_rejection_is_not_counted_as_duplicate(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    facts = make_facts(amount_minor=7_000)
    candidates = tuple(
        make_scenario_candidate(
            candidate_id=f"conflict-{index}",
            origins=frozenset({"mechanical"}),
            facts=facts,
            assertions=(
                make_assertion(
                    assertion_id=f"mechanical-{index}",
                    expected_value=expected,
                    origin="mechanical",
                    source_invariant_id=None,
                    mechanical_relation_id=f"relation-{index}",
                ),
            ),
        )
        for index, expected in enumerate((6_000, 7_000))
    )
    monkeypatch.setattr(
        "app.features.fuzzing.planner.build_initial_mechanical_candidates",
        lambda *_args, **_kwargs: candidates,
    )
    planner = DefaultScenarioPlanner()
    request = initial_request()

    batch = await planner.generate_initial(request)
    coordinator = RunCoordinator.__new__(RunCoordinator)
    coordinator.scenario_planner = planner
    suite = coordinator._assemble(
        SimpleNamespace(run_id="run-1", manifest=manifest()),
        request.policy,
        request.contract,
        batch.candidates,
    )

    assert len(suite.scenarios) == 1
    assert suite.statistics.generated_count == 2
    assert suite.statistics.rejected_count == 1
    assert suite.statistics.duplicate_count == 0
    assert [item.reason_code for item in suite.statistics.rejections] == [
        "incompatible_assertions"
    ]


@pytest.mark.asyncio
async def test_targeted_generation_calls_model_once_and_excludes_used_facts() -> None:
    payload = exploratory_response_example(
        rule_id="rule-meal", invariant_id="invariant-0"
    )
    llm = ScriptedLLMClient([LLMResponse(output=payload)])
    planner = DefaultScenarioPlanner(llm, manifest=manifest())
    existing = make_scenario_candidate(
        candidate_id="existing", facts=make_facts(amount_minor=5_000)
    )
    request = GenerateTargetedScenariosRequest(
        policy=make_policy(),
        contract=make_policy_contract(),
        seed=42,
        scenario_budget=5,
        existing_candidates=(existing,),
        coverage=CoverageSnapshot(
            total_rules=1,
            total_invariants=3,
            missing_rule_ids=("rule-meal",),
            missing_invariant_ids=("invariant-0",),
        ),
        targeted_cycle=1,
    )
    targeted = await planner.generate_targeted(request)

    assert len(targeted.candidates) <= 5
    assert [item.operation for item in llm.requests] == ["targeted_scenario_generation"]
    assert all(
        fact_sha256(item.facts) != fact_sha256(existing.facts)
        for item in targeted.candidates
    )
    with pytest.raises(CoverageLimitExceededError, match="COVERAGE_LIMIT_EXCEEDED"):
        await planner.generate_targeted(request)


def test_suite_hash_and_scenario_order_are_stable_across_batch_order() -> None:
    candidates = (
        make_scenario_candidate(candidate_id="one", facts=make_facts(amount_minor=100)),
        make_scenario_candidate(candidate_id="two", facts=make_facts(amount_minor=200)),
    )
    forward = DefaultScenarioPlanner().assemble_suite(assemble_request(candidates))
    reverse = DefaultScenarioPlanner().assemble_suite(
        assemble_request(tuple(reversed(candidates)))
    )

    assert forward.content_sha256 == reverse.content_sha256
    assert [item.scenario_id for item in forward.scenarios] == sorted(
        item.scenario_id for item in forward.scenarios
    )


def test_assemble_caps_total_at_fifteen_and_keeps_rejection_visible() -> None:
    candidates = tuple(
        make_scenario_candidate(
            candidate_id=f"candidate-{index}",
            facts=make_facts(amount_minor=100 + index),
        )
        for index in range(16)
    )
    suite = DefaultScenarioPlanner().assemble_suite(assemble_request(candidates))

    assert len(suite.scenarios) == 15
    assert (
        sum(
            item.reason_code == "budget_exceeded"
            for item in suite.statistics.rejections
        )
        == 1
    )
    assert suite.statistics.generated_count == 16
