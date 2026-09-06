import pytest

from tests.workflow.coordinator_fixtures import baseline, evaluate, harness


@pytest.mark.asyncio
async def test_baseline_freezes_and_authoritatively_reexecutes_exact_suite():
    coordinator, fakes = harness()
    view = await baseline(coordinator)
    assert view.stage == "completed_no_findings"
    requests = fakes.evaluation_engine.requests
    assert len(requests) == 2
    assert requests[0].suite == requests[1].suite
    assert fakes.scenario_planner.initial_requests[0].scenario_budget == 10
    assert fakes.scenario_planner.targeted_calls == 0
    record = await fakes.store.get(view.run_id)
    assert (
        len([a for a in record.artifacts if a.artifact_type == "scenario_suite"]) == 1
    )
    contract = next(
        a.payload for a in record.artifacts if a.artifact_type == "policy_contract"
    )
    assert {i.severity for i in contract.invariants} == {"high"}


@pytest.mark.asyncio
async def test_missing_coverage_targets_only_once_then_refuses_authority():
    from app.workflow.fake_stages import FakeEvaluationEngine

    coordinator, fakes = harness(
        evaluation_engine=FakeEvaluationEngine(
            [lambda r: evaluate(r, missing=True), lambda r: evaluate(r, missing=True)]
        )
    )
    view = await baseline(coordinator)
    assert view.stage == "coverage_limit_exceeded"
    assert fakes.scenario_planner.targeted_calls == 1
    assert fakes.scenario_planner.targeted_requests[0].scenario_budget == 5
    record = await fakes.store.get(view.run_id)
    assert not any(
        a.artifact_type in {"scenario_suite", "evaluation_report", "revision_proposal"}
        for a in record.artifacts
    )


@pytest.mark.asyncio
async def test_targeted_success_still_reruns_frozen_suite_authoritatively():
    from app.workflow.fake_stages import FakeEvaluationEngine

    coordinator, fakes = harness(
        evaluation_engine=FakeEvaluationEngine(
            [lambda r: evaluate(r, missing=True), evaluate, evaluate]
        )
    )
    view = await baseline(coordinator)
    assert view.stage == "completed_no_findings"
    assert fakes.scenario_planner.targeted_calls == 1
    assert view.coverage.covered_invariants == 3
    assert len(fakes.evaluation_engine.requests) == 3
    assert (
        fakes.evaluation_engine.requests[1].suite
        == fakes.evaluation_engine.requests[2].suite
    )


@pytest.mark.asyncio
async def test_initial_batch_over_budget_is_not_assembled():
    from app.workflow.fake_stages import FakeScenarioPlanner
    from tests.workflow.coordinator_fixtures import batch

    def oversized(value):
        first = batch(value).candidates[0]
        return batch(value).model_copy(
            update={
                "candidates": tuple(
                    first.model_copy(update={"candidate_id": f"extra-{i}"})
                    for i in range(11)
                )
            }
        )

    planner = FakeScenarioPlanner(initial=[oversized])
    coordinator, _fakes = harness(scenario_planner=planner)
    view = await baseline(coordinator)
    assert view.stage == "failed"
    assert planner.assembly_calls == 0
