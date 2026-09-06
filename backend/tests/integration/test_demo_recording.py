import pytest

from app.domain.models import CreateRunRequest
from app.workflow.coordinator import RunCoordinator
from app.workflow.errors import InvalidRunCommandError
from app.workflow.store import RunStore
from tests.workflow.coordinator_fixtures import (
    Clock,
    compilation,
    document,
    manifest,
    request,
)


def _recorder(**kwargs):
    class Compiler:
        async def compile(self, value):
            return compilation(value)

    clock = Clock()
    return RunCoordinator(
        store=RunStore(clock),
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
        draft_severity="medium",
        mode="cached",
        recording_demo=True,
        **kwargs,
    )


@pytest.mark.asyncio
async def test_recording_executes_stages_with_cached_manifest_from_start():
    coordinator = _recorder()
    created = await coordinator.create_run(
        CreateRunRequest(
            source_type="bundled_sample",
            title="Synthetic",
            sample_id="development-policy",
        )
    )
    await coordinator.start(created.run_id)
    view = await coordinator.get_run(created.run_id)
    assert view.stage == "awaiting_contract"
    assert view.mode == "cached"
    assert (await coordinator.store.get(created.run_id)).manifest.mode == "cached"


@pytest.mark.asyncio
async def test_recording_rejects_pasted_input_before_storage():
    coordinator = _recorder()
    with pytest.raises(InvalidRunCommandError):
        await coordinator.create_run(request())


@pytest.mark.asyncio
async def test_real_stages_complete_scripted_development_flow():
    from scripts.demo_support import latest, run_demo

    record, outputs = await run_demo()
    comparison = latest(record, "comparison_bundle")
    assert record.stage == "complete"
    assert record.manifest.mode == "cached"
    assert comparison.acceptance.patch_accepted
    assert comparison.baseline_metrics.unique_finding_count == 3
    assert comparison.revised_metrics.unique_finding_count == 0
    assert len(latest(record, "scenario_suite").scenarios) <= 15
    assert outputs
