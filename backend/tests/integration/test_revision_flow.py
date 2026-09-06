import pytest

from app.domain.models import ConfirmRevisionRequest
from app.workflow.errors import InvalidRunCommandError
from tests.workflow.coordinator_fixtures import baseline, revision_harness, selection


@pytest.mark.asyncio
async def test_revision_confirms_once_and_retests_identical_frozen_suite():
    coordinator, fakes = revision_harness()
    view = await baseline(coordinator)
    assert view.stage == "awaiting_finding_review"
    view = await coordinator.select_findings(view.run_id, selection())
    assert view.stage == "awaiting_revision_confirmation"
    assert view.pending_confirmation.operations[0].before.rule_id == "rule"
    view = await coordinator.confirm_revision(
        view.run_id, ConfirmRevisionRequest(proposal_id="proposal", decision="confirm")
    )
    assert view.stage == "complete"
    requests = fakes.evaluation_engine.requests
    assert requests[1].suite == requests[2].suite
    assert requests[1].contract == requests[2].contract
    assert requests[1].inputs.policy_sha256 != requests[2].inputs.policy_sha256
    assert view.comparison_metrics.patch_accepted
    assert fakes.revision_planner.calls == fakes.revision_applier.calls == 1


@pytest.mark.asyncio
async def test_structural_severity_is_required_and_rejection_has_no_downstream_calls():
    coordinator, fakes = revision_harness()
    view = await baseline(coordinator)
    with pytest.raises(InvalidRunCommandError):
        await coordinator.select_findings(view.run_id, selection(None))
    assert (await coordinator.get_run(view.run_id)).stage == "awaiting_finding_review"
    view = await coordinator.select_findings(view.run_id, selection(None, "reject"))
    assert view.stage == "completed_no_revision"
    assert fakes.revision_planner.calls == 0


@pytest.mark.asyncio
async def test_revision_rejection_is_terminal_without_application():
    coordinator, fakes = revision_harness()
    view = await baseline(coordinator)
    await coordinator.select_findings(view.run_id, selection())
    view = await coordinator.confirm_revision(
        view.run_id, ConfirmRevisionRequest(proposal_id="proposal", decision="reject")
    )
    assert view.stage == "revision_rejected"
    assert fakes.revision_applier.calls == 0


@pytest.mark.asyncio
async def test_equal_count_bad_state_relocation_preserves_false_acceptance_gate():
    from app.domain.models import DimensionResult, EffectStateCounts
    from app.workflow.fake_stages import FakeEvaluationEngine, FakeRegressionAnalyzer
    from tests.workflow.coordinator_fixtures import compare, digest, evaluate, metrics

    def relocation(value):
        result = evaluate(value)
        index = 1 if value.policy.kind == "structured_revision" else 0
        rows = list(result.results)
        trace = rows[index].trace.model_copy(
            update={
                "resolved_effects": (
                    DimensionResult(dimension="eligibility", status="GAP"),
                )
            }
        )
        trace = trace.model_copy(update={"trace_sha256": digest(trace)})
        rows[index] = rows[index].model_copy(update={"trace": trace})
        return result.model_copy(update={"results": tuple(rows)})

    def measured_metrics(value):
        return metrics(value).model_copy(
            update={"effect_states": EffectStateCounts(VALUE=2, GAP=1)}
        )

    def conservative(value):
        result = compare(value)
        before = result.baseline_metrics.model_copy(
            update={"effect_states": EffectStateCounts(VALUE=2, GAP=1)}
        )
        after = result.revised_metrics.model_copy(
            update={"effect_states": EffectStateCounts(VALUE=2, GAP=1)}
        )
        regression = result.regression.model_copy(
            update={
                "baseline_effect_states": before.effect_states,
                "revised_effect_states": after.effect_states,
            }
        )
        counts = result.acceptance.counts.model_copy(
            update={
                "baseline_gap_conflict_inconclusive_or_error": 1,
                "revised_gap_conflict_inconclusive_or_error": 1,
            }
        )
        acceptance = result.acceptance.model_copy(
            update={
                "no_increase_in_gap_conflict_inconclusive_or_error": False,
                "patch_accepted": False,
                "counts": counts,
            }
        )
        return result.model_copy(
            update={
                "baseline_metrics": before,
                "revised_metrics": after,
                "regression": regression,
                "acceptance": acceptance,
            }
        )

    coordinator, _fakes = revision_harness(
        evaluation_engine=FakeEvaluationEngine([relocation, relocation, relocation]),
        regression_analyzer=FakeRegressionAnalyzer([conservative]),
        metrics=measured_metrics,
    )
    view = await baseline(coordinator)
    await coordinator.select_findings(view.run_id, selection())
    view = await coordinator.confirm_revision(
        view.run_id, ConfirmRevisionRequest(proposal_id="proposal", decision="confirm")
    )
    assert view.stage == "complete"
    assert not view.comparison_metrics.patch_accepted
    assert not view.comparison_metrics.acceptance.no_increase_in_gap_conflict_inconclusive_or_error


@pytest.mark.asyncio
async def test_competing_revision_confirmations_apply_only_once():
    import asyncio

    from app.workflow.errors import WorkflowError

    coordinator, fakes = revision_harness()
    view = await baseline(coordinator)
    await coordinator.select_findings(view.run_id, selection())
    command = ConfirmRevisionRequest(proposal_id="proposal", decision="confirm")
    results = await asyncio.gather(
        coordinator.confirm_revision(view.run_id, command),
        coordinator.confirm_revision(view.run_id, command),
        return_exceptions=True,
    )
    assert sum(isinstance(result, WorkflowError) for result in results) == 1
    assert fakes.revision_applier.calls == 1
    assert (await coordinator.get_run(view.run_id)).stage == "complete"
