"""End-to-end command and integrity boundaries for the bounded coordinator."""

import asyncio

import pytest

from app.domain.models import ConfirmContractRequest
from tests.workflow.coordinator_fixtures import (
    Clock,
    compilation,
    document,
    manifest,
    request,
)


@pytest.mark.asyncio
async def test_start_pauses_with_unconfirmed_severity_and_rejection_is_terminal():
    from app.workflow.coordinator import RunCoordinator
    from app.workflow.store import RunStore

    class Compiler:
        async def compile(self, value):
            return compilation(value)

    clock = Clock()
    store = RunStore(clock)
    coordinator = RunCoordinator(
        store=store,
        clock=clock,
        policy_compiler=Compiler(),
        scenario_planner=None,
        evaluation_engine=None,
        finding_analyzer=None,
        revision_planner=None,
        revision_applier=None,
        regression_analyzer=None,
        ingest=document,
        metrics=None,
        manifest_factory=manifest,
        draft_severity="low",
        run_id_factory=lambda: "run",
    )
    created = await coordinator.create_run(request())
    await coordinator.start(created.run_id)
    view = await coordinator.get_run(created.run_id)
    assert view.stage == "awaiting_contract"
    assert {item.severity for item in view.pending_confirmation.invariants} == {"low"}
    record = await store.get(created.run_id)
    assert record.source_request is None
    assert not any(a.artifact_type == "policy_contract" for a in record.artifacts)
    rejected = await coordinator.confirm_contract(
        created.run_id, ConfirmContractRequest(decision="reject")
    )
    assert rejected.stage == "contract_rejected"
    assert rejected.pending_confirmation is None


@pytest.mark.asyncio
async def test_stale_contract_anchor_does_not_change_review_state():
    from app.workflow.errors import StaleArtifactError
    from tests.workflow.coordinator_fixtures import confirm, harness

    coordinator, fakes = harness()
    created = await coordinator.create_run(request())
    await coordinator.start(created.run_id)
    before = await fakes.store.get(created.run_id)
    command = confirm(await coordinator.get_run(created.run_id)).model_copy(
        update={"baseline_policy_sha256": "0" * 64}
    )
    with pytest.raises(StaleArtifactError):
        await coordinator.confirm_contract(created.run_id, command)
    assert await fakes.store.get(created.run_id) == before


@pytest.mark.asyncio
async def test_competing_contract_commands_claim_only_one_generation():
    from app.workflow.errors import WorkflowError
    from app.workflow.fake_stages import FakeScenarioPlanner
    from tests.workflow.coordinator_fixtures import assemble, batch, confirm, harness

    entered, release = asyncio.Event(), asyncio.Event()

    async def paused(value):
        entered.set()
        await release.wait()
        return batch(value)

    planner = FakeScenarioPlanner(initial=[paused], suites=[assemble])
    coordinator, _fakes = harness(scenario_planner=planner)
    created = await coordinator.create_run(request())
    await coordinator.start(created.run_id)
    command = confirm(await coordinator.get_run(created.run_id))
    task = asyncio.create_task(coordinator.confirm_contract(created.run_id, command))
    await asyncio.wait_for(entered.wait(), 1)
    with pytest.raises(WorkflowError):
        await coordinator.confirm_contract(created.run_id, command)
    release.set()
    await task
    assert planner.initial_calls == 1


@pytest.mark.asyncio
@pytest.mark.parametrize("kind", ["potential_loophole", "private"])
async def test_nonreviewable_findings_end_without_drafting(kind):
    from app.workflow.fake_stages import FakeFindingAnalyzer, FakeScenarioPlanner
    from tests.workflow.coordinator_fixtures import (
        assemble,
        baseline,
        batch,
        harness,
        one_finding,
    )

    def candidates(value):
        result = batch(value)
        if kind == "private":
            return result.model_copy(
                update={
                    "candidates": tuple(
                        c.model_copy(update={"partition": "holdout"})
                        for c in result.candidates
                    )
                }
            )
        return result

    coordinator, fakes = harness(
        finding_analyzer=FakeFindingAnalyzer(
            [
                lambda r: one_finding(
                    r,
                    "potential_loophole"
                    if kind == "potential_loophole"
                    else "structural_gap",
                )
            ]
        ),
        scenario_planner=FakeScenarioPlanner(initial=[candidates], suites=[assemble]),
    )
    view = await baseline(coordinator)
    assert view.stage == "completed_no_findings"
    assert fakes.revision_planner.calls == 0


@pytest.mark.asyncio
async def test_invariant_severity_is_inherited_and_conflicting_override_rejected():
    from app.workflow.errors import InvalidRunCommandError
    from app.workflow.fake_stages import FakeFindingAnalyzer
    from tests.workflow.coordinator_fixtures import (
        baseline,
        one_finding,
        revision_harness,
        selection,
    )

    coordinator, fakes = revision_harness(
        finding_analyzer=FakeFindingAnalyzer(
            [lambda r: one_finding(r, "intent_breach")]
        )
    )
    view = await baseline(coordinator)
    with pytest.raises(InvalidRunCommandError):
        await coordinator.select_findings(view.run_id, selection("critical"))
    await coordinator.select_findings(view.run_id, selection(None))
    finding = fakes.revision_planner.requests[0].findings.findings[0]
    assert finding.severity == "high" and finding.severity_origin == "session_invariant"


@pytest.mark.asyncio
async def test_rejected_finding_cannot_carry_severity():
    from app.workflow.errors import InvalidRunCommandError
    from tests.workflow.coordinator_fixtures import (
        baseline,
        revision_harness,
        selection,
    )

    coordinator, _fakes = revision_harness()
    view = await baseline(coordinator)
    with pytest.raises(InvalidRunCommandError):
        await coordinator.select_findings(view.run_id, selection("high", "reject"))
    assert (await coordinator.get_run(view.run_id)).stage == "awaiting_finding_review"
