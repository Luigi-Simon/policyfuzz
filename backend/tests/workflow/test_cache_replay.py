from pathlib import Path

import pytest
from pydantic import BaseModel

from app.core.artifacts import complete_payload_projection
from app.core.hashing import canonical_sha256
from app.domain.models import CreateRunRequest, InputHashes, RunRecord
from app.workflow.errors import InvalidRunCommandError
from app.workflow.validation import validate_cached_record
from tests.workflow.coordinator_fixtures import cached_record, harness


def digest(value):
    return canonical_sha256(complete_payload_projection(value))


def inputs(value):
    if isinstance(value, InputHashes):
        yield value
    elif isinstance(value, BaseModel):
        for name in type(value).model_fields:
            yield from inputs(getattr(value, name))
    elif isinstance(value, (tuple, list)):
        for item in value:
            yield from inputs(item)


def test_complete_cached_graph_rebases_only_session_manifest_references():
    from app.workflow.cache_replay import rebase_cached_record

    path = Path(__file__).resolve().parents[3] / "samples/cached-demo/run-record.json"
    original_bytes = path.read_bytes()
    source = RunRecord.model_validate_json(original_bytes)
    assert source.stage == "complete"
    replay = rebase_cached_record(source, "new-session")
    assert validate_cached_record(replay) == replay
    assert replay.run_id == replay.manifest.run_id == "new-session"
    assert digest(source) in replay.manifest.manifest_id
    assert replay.manifest.started_at == source.manifest.started_at
    assert replay.manifest.prompt_hashes == source.manifest.prompt_hashes
    assert replay.manifest.engine_sha256 == source.manifest.engine_sha256
    assert replay.manifest.mode == "cached"
    unchanged = {
        "policy_document",
        "policy_ir",
        "policy_contract",
        "scenario_suite",
        "revision_proposal",
    }
    for old, new in zip(source.artifacts, replay.artifacts, strict=True):
        assert old.artifact_type == new.artifact_type
        assert new.run_manifest_id == replay.manifest.manifest_id
        if old.artifact_type in unchanged:
            assert old.payload == new.payload
            assert old.artifact_sha256 == new.artifact_sha256
        for before, after in zip(inputs(old.payload), inputs(new.payload), strict=True):
            assert after.run_manifest_sha256 == digest(replay.manifest)
            assert before.model_dump(
                exclude={"run_manifest_sha256"}
            ) == after.model_dump(exclude={"run_manifest_sha256"})
    changed = {a.artifact_sha256 for a in replay.artifacts}
    assert all(
        event.artifact is None or event.artifact.artifact_sha256 in changed
        for event in replay.events
    )
    assert path.read_bytes() == original_bytes
    assert source == RunRecord.model_validate_json(original_bytes)


async def test_deleted_cached_ids_remain_tombstoned_if_factory_repeats():
    source = cached_record()
    coordinator, _ = harness(
        mode="cached", cached_loader=lambda _: source, run_id_factory=lambda: "same-id"
    )
    command = CreateRunRequest(
        source_type="bundled_sample", sample_id="development-policy", title="Synthetic"
    )
    created = await coordinator.create_run(command)
    assert created.run_id == "same-id"
    await coordinator.delete_run(created.run_id)
    with pytest.raises(InvalidRunCommandError):
        await coordinator.create_run(command)
