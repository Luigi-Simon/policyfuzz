import pytest

from app.domain.models import CreateRunRequest
from app.workflow.errors import WorkflowError
from tests.workflow.coordinator_fixtures import cached_record, harness


@pytest.mark.asyncio
async def test_cached_replay_creates_fresh_session_and_never_calls_stages():
    record = cached_record()
    coordinator, fakes = harness(mode="cached", cached_loader=lambda _: record)
    created = await coordinator.create_run(
        CreateRunRequest(
            source_type="bundled_sample", title="Synthetic", sample_id="synthetic"
        )
    )
    assert created.run_id == "run"
    assert created.run_id != record.run_id
    view = await coordinator.get_run(created.run_id)
    assert view.stage == "completed_no_findings" and view.mode == "cached"
    assert fakes.policy_compiler.calls == fakes.evaluation_engine.calls == 0
    with pytest.raises(WorkflowError):
        await coordinator.start(created.run_id)
    await coordinator.delete_run(created.run_id)


@pytest.mark.asyncio
@pytest.mark.parametrize("tamper", ["digest", "parent", "manifest", "inputs"])
async def test_cached_graph_tampering_is_rejected_before_storage(tamper):
    record = cached_record()
    envelopes = list(record.artifacts)
    if tamper == "digest":
        envelopes[0] = envelopes[0].model_copy(update={"semantic_sha256": "0" * 64})
    if tamper == "parent":
        envelopes[-1] = envelopes[-1].model_copy(update={"parent_hashes": ("0" * 64,)})
    if tamper == "manifest":
        envelopes[-1] = envelopes[-1].model_copy(update={"run_manifest_id": "other"})
    if tamper == "inputs":
        from app.core.artifacts import make_artifact_envelope

        old = envelopes[5]
        payload = old.payload.model_copy(
            update={
                "inputs": old.payload.inputs.model_copy(
                    update={"policy_sha256": "0" * 64}
                )
            }
        )
        envelopes[5] = make_artifact_envelope(
            artifact_type="evaluation_report",
            payload=payload,
            run_manifest_id=record.manifest.manifest_id,
        )
    record = record.model_copy(update={"artifacts": tuple(envelopes)})
    coordinator, fakes = harness(mode="cached", cached_loader=lambda _: record)
    with pytest.raises(WorkflowError):
        await coordinator.create_run(
            CreateRunRequest(
                source_type="bundled_sample", title="Synthetic", sample_id="synthetic"
            )
        )
    with pytest.raises(WorkflowError):
        await fakes.store.get("recorded")


@pytest.mark.asyncio
async def test_cached_suite_must_link_its_actual_parent_artifacts():
    record = cached_record()
    envelopes = list(record.artifacts)
    envelopes[4] = envelopes[4].model_copy(update={"parent_hashes": ()})
    record = record.model_copy(update={"artifacts": tuple(envelopes)})
    coordinator, _fakes = harness(mode="cached", cached_loader=lambda _: record)
    with pytest.raises(WorkflowError):
        await coordinator.create_run(
            CreateRunRequest(
                source_type="bundled_sample", title="Synthetic", sample_id="synthetic"
            )
        )


@pytest.mark.asyncio
async def test_appended_cached_suite_cannot_repartition_prior_holdout_evidence():
    from app.workflow.validation import validate_cached_record
    from app.workflow.views import to_run_view
    from tests.workflow.coordinator_fixtures import cached_holdout_record

    original = cached_holdout_record()
    assert validate_cached_record(original) == original
    assert to_run_view(original).traces == ()
    tampered = cached_holdout_record(append_visible_suite=True)
    coordinator, fakes = harness(mode="cached", cached_loader=lambda _: tampered)
    with pytest.raises(WorkflowError):
        await coordinator.create_run(
            CreateRunRequest(
                source_type="bundled_sample", title="Synthetic", sample_id="synthetic"
            )
        )
    with pytest.raises(WorkflowError):
        await fakes.store.get(original.run_id)
