"""Offline one-shot recorder checks using only authored synthetic public metadata."""

import hashlib
import json
from datetime import UTC, datetime

import pytest

from app.domain.models import RunRecord
from tests.workflow.coordinator_fixtures import baseline, harness


def write(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, sort_keys=True) + "\n")
    return hashlib.sha256(path.read_bytes()).hexdigest()


@pytest.fixture
async def packet(tmp_path):
    from scripts.record_blind_run import GitSnapshot

    coordinator, parts = harness()
    await baseline(coordinator)
    stored = await parts.store.get("run")
    record = RunRecord.model_validate_json(
        stored.model_dump_json(
            exclude={"version", "source_request", "pending_confirmation"}
        )
    )
    policy = tmp_path / "samples/policies/blind-policy.txt"
    policy.parent.mkdir(parents=True)
    policy.write_text("Meals allowed.")
    policy_hash = hashlib.sha256(policy.read_bytes()).hexdigest()
    source = tmp_path / "submission/evidence/benchmark-v2/blind-seal.json"
    schema = source.with_name("blind-schema-seal.json")
    provenance = source.with_name("provenance.json")
    active = tmp_path / "submission/evidence/active-benchmark.json"
    approval = tmp_path / "submission/evidence/human-approval.json"
    write(
        source,
        {
            "policy_sha256": policy_hash,
            "archive_sha256": "1" * 64,
            "manifest_sha256": "2" * 64,
            "defect_ids_sha256": "3" * 64,
            "defect_count": 3,
            "created_at": "2026-09-06T00:00:00Z",
        },
    )
    write(
        schema,
        {
            "schema_version": "1.0",
            "source_policy_sha256": policy_hash,
            "archive_sha256": "4" * 64,
            "defect_ids_sha256": "3" * 64,
            "defect_count": 3,
            "rule_count": 9,
            "scenario_count": 15,
            "artifact_hashes": {
                name: "5" * 64
                for name in (
                    "source-labels.json",
                    "canonical-policy-ir.json",
                    "confirmed-contract.json",
                    "frozen-suite.json",
                    "expected-effects.json",
                    "defect-manifest.json",
                    "corrected-semantics.json",
                )
            },
            "created_at": "2026-09-06T00:00:01Z",
        },
    )
    write(
        provenance,
        {
            "candidate_version": 2,
            "source_policy_sha256": policy_hash,
            "source_archive_sha256": "1" * 64,
            "schema_archive_sha256": "4" * 64,
            "defect_ids_sha256": "3" * 64,
            "created_at": "2026-09-06T00:00:01Z",
            "independent_human_review": "pending",
            "headline_gold_scoring_eligible": False,
        },
    )
    approval_hash = write(
        approval,
        {
            "reviewer_type": "human",
            "decision": "approve",
            "reviewer_id": "synthetic-reviewer",
            "timestamp": "2026-09-06T00:00:02Z",
            "candidate_version": 2,
            "source_policy_sha256": policy_hash,
            "schema_archive_sha256": "4" * 64,
        },
    )
    write(
        active,
        {
            "schema_version": "1.0",
            "candidate_version": 2,
            "human_review": "approved",
            "headline_gold_scoring_eligible": True,
            "source_policy_sha256": policy_hash,
            "schema_archive_sha256": "4" * 64,
            "defect_ids_sha256": "3" * 64,
            "source_seal": str(source.relative_to(tmp_path)),
            "schema_seal": str(schema.relative_to(tmp_path)),
            "provenance": str(provenance.relative_to(tmp_path)),
            "approval_evidence": {
                "path": str(approval.relative_to(tmp_path)),
                "sha256": approval_hash,
            },
        },
    )
    tracked = tuple(
        sorted(
            (
                str(path.relative_to(tmp_path)),
                hashlib.sha256(path.read_bytes()).hexdigest(),
            )
            for path in (active, source, schema, provenance, approval, policy)
        )
    )
    snapshot = GitSnapshot(
        tracked_inputs=tracked,
        commit="a" * 40,
        tag_object="b" * 40,
        tag_commit="a" * 40,
        tree="c" * 40,
        tag_type="tag",
        dirty=False,
        common_dir=tmp_path / ".git",
    )
    runtime = {
        key: record.manifest.model_dump(mode="json")[key]
        for key in (
            "provider",
            "model_identifier",
            "generation_config",
            "engine_version",
            "engine_sha256",
            "prompt_hashes",
            "random_seed",
        )
    }
    return {
        "root": tmp_path,
        "tag": "blind-candidate-v1",
        "policy": policy,
        "source_seal": source,
        "schema_seal": schema,
        "candidate_metadata": active,
        "output": tmp_path / "evidence/blind-first-run.json",
        "snapshot": lambda: snapshot,
        "runtime_metadata": lambda: runtime,
        "now": lambda: datetime(2026, 9, 6, 0, 0, 3, tzinfo=UTC),
    }, record


async def test_records_first_public_run_and_bound_metadata(packet):
    from scripts.record_blind_run import record_blind_run

    options, record = packet
    calls = []

    async def execute(policy_text, confirmation, guard):
        guard()
        reservations = list(
            (options["root"] / ".git/policyfuzz-blind-attempts").glob("*.json")
        )
        assert len(reservations) == 1
        assert json.loads(reservations[0].read_text())["status"] == "reserved"
        calls.append(policy_text)
        return record

    metadata = await record_blind_run(**options, executor=execute)
    assert calls == ["Meals allowed."]
    assert RunRecord.model_validate_json(options["output"].read_bytes()) == record
    assert metadata["status"] == "recorded"
    assert metadata["commit"] == "a" * 40
    assert (
        metadata["result_bytes_sha256"]
        == hashlib.sha256(options["output"].read_bytes()).hexdigest()
    )
    assert metadata["runtime"] == options["runtime_metadata"]()
    assert "source_request" not in options["output"].read_text()


async def test_failed_attempt_is_durable_and_blocks_another_output(packet):
    from scripts.record_blind_run import RecorderError, record_blind_run

    options, _ = packet
    calls = []

    async def execute(*args):
        calls.append(1)
        raise RuntimeError("SECRET-provider-response")

    with pytest.raises(RecorderError, match="BLIND_EXECUTION_FAILED"):
        await record_blind_run(**options, executor=execute)
    metadata = options["output"].with_name(options["output"].name + ".metadata.json")
    assert "SECRET" not in metadata.read_text()
    assert json.loads(metadata.read_text())["status"] == "failed"
    options["output"] = options["output"].with_name("another-output.json")
    with pytest.raises(RecorderError, match="BLIND_ALREADY_ATTEMPTED"):
        await record_blind_run(**options, executor=execute)
    assert calls == [1]


@pytest.mark.parametrize(
    "issue",
    [
        "pending",
        "wrong_policy",
        "wrong_schema",
        "bad_approval",
        "dirty",
        "lightweight",
        "wrong_commit",
    ],
)
async def test_preflight_failure_never_calls_executor_or_reserves(packet, issue):
    from dataclasses import replace

    from scripts.record_blind_run import RecorderError, record_blind_run

    options, _ = packet
    if issue in {"pending", "wrong_schema", "bad_approval"}:
        active = json.loads(options["candidate_metadata"].read_text())
        if issue == "pending":
            active["human_review"] = "pending"
            active["headline_gold_scoring_eligible"] = False
        elif issue == "wrong_schema":
            active["schema_archive_sha256"] = "9" * 64
        else:
            active["approval_evidence"]["sha256"] = "9" * 64
        write(options["candidate_metadata"], active)
    elif issue == "wrong_policy":
        options["policy"].write_text("Changed synthetic policy")
    else:
        values = {
            "dirty": {"dirty": True},
            "lightweight": {"tag_type": "commit"},
            "wrong_commit": {"tag_commit": "d" * 40},
        }[issue]
        current = replace(options["snapshot"](), **values)
        options["snapshot"] = lambda: current

    async def forbidden(*args):
        pytest.fail("preflight called executor")

    with pytest.raises(RecorderError):
        await record_blind_run(**options, executor=forbidden)
    assert not (options["root"] / ".git/policyfuzz-blind-attempts").exists()


@pytest.mark.parametrize("drift", ["source", "commit", "runtime"])
async def test_execution_drift_preserves_first_record_but_invalidates_claim(
    packet, drift
):
    from dataclasses import replace

    from scripts.record_blind_run import RecorderError, record_blind_run

    options, record = packet
    original = options["snapshot"]()
    snapshots = [original]
    options["snapshot"] = lambda: snapshots[0]

    async def execute(*args):
        if drift == "source":
            options["policy"].write_text("Changed synthetic policy")
        elif drift == "commit":
            snapshots[0] = replace(original, commit="d" * 40)
        else:
            options["runtime_metadata"]()["model_identifier"] = "changed-model"
        return record

    with pytest.raises(RecorderError, match="BLIND_FROZEN_INPUT_CHANGED"):
        await record_blind_run(**options, executor=execute)
    assert RunRecord.model_validate_json(options["output"].read_bytes()) == record
    assert (
        json.loads(
            options["output"]
            .with_name(options["output"].name + ".metadata.json")
            .read_text()
        )["status"]
        == "invalidated"
    )


async def test_existing_output_is_never_overwritten(packet):
    from scripts.record_blind_run import RecorderError, record_blind_run

    options, _ = packet
    options["output"].parent.mkdir(parents=True)
    options["output"].write_text("existing evidence")
    with pytest.raises(RecorderError, match="BLIND_OUTPUT_EXISTS"):
        await record_blind_run(**options)
    assert options["output"].read_text() == "existing evidence"


def test_current_public_candidate_is_refused_without_opening_policy(tmp_path):
    import asyncio

    from scripts.record_blind_run import ROOT, RecorderError, record_blind_run

    active = json.loads(
        (ROOT / "submission/evidence/active-benchmark.json").read_text()
    )
    if (
        active.get("human_review") == "approved"
        and active.get("headline_gold_scoring_eligible") is True
    ):
        pytest.skip(
            "Independent approval has now been recorded; synthetic pending cases remain covered."
        )
    with pytest.raises(RecorderError, match="BLIND_APPROVAL_PENDING"):
        asyncio.run(
            record_blind_run(
                root=ROOT,
                tag="not-a-real-tag",
                policy=tmp_path / "never-revealed.txt",
                source_seal=ROOT / "submission/evidence/benchmark-v2/blind-seal.json",
                schema_seal=ROOT
                / "submission/evidence/benchmark-v2/blind-schema-seal.json",
                output=tmp_path / "no-result.json",
            )
        )


async def test_unvalidated_private_stored_run_is_not_published(packet):
    from scripts.record_blind_run import RecorderError, record_blind_run

    options, _ = packet
    coordinator, parts = harness()
    await baseline(coordinator)
    stored = await parts.store.get("run")

    async def execute(*args):
        return stored

    with pytest.raises(RecorderError):
        await record_blind_run(**options, executor=execute)
    assert not options["output"].exists()


async def test_policy_bytes_must_be_bound_to_tagged_tree(packet):
    from dataclasses import replace

    from scripts.record_blind_run import RecorderError, record_blind_run

    options, _ = packet
    snapshot = replace(options["snapshot"](), tracked_inputs=())
    options["snapshot"] = lambda: snapshot
    with pytest.raises(RecorderError, match="BLIND_TAG_INPUT_MISMATCH"):
        await record_blind_run(**options)


async def test_live_executor_requires_explicit_json_at_all_three_pauses():
    from scripts.record_blind_run import execute_live

    from app.container import AppContainer
    from app.core.config import Settings
    from app.domain.models import ConfirmRevisionRequest
    from app.workflow.task_runner import AsyncTaskRunner
    from tests.workflow.coordinator_fixtures import confirm, revision_harness, selection

    coordinator, parts = revision_harness()
    container = AppContainer(
        coordinator=coordinator,
        task_runner=AsyncTaskRunner(parts.store, parts.clock),
        settings=Settings(app_mode="live"),
        engine_version="1.0",
    )
    actions = []

    async def human(action, view):
        actions.append(action)
        commands = {
            "confirm_contract": lambda: confirm(view),
            "select_findings": selection,
            "confirm_revision": lambda: ConfirmRevisionRequest(
                proposal_id=view.pending_confirmation.proposal_id, decision="confirm"
            ),
        }
        return commands[action]().model_dump_json()

    record = await execute_live(
        "Meals allowed.", human, lambda: None, container_factory=lambda guard: container
    )
    assert actions == ["confirm_contract", "select_findings", "confirm_revision"]
    assert record.stage == "complete"
    assert record.manifest.mode == "live"


async def test_bad_human_command_preserves_partial_record_without_autoapproval():
    from scripts.record_blind_run import ExecutionInterrupted, execute_live

    from app.container import AppContainer
    from app.core.config import Settings
    from app.workflow.task_runner import AsyncTaskRunner

    coordinator, parts = harness()
    container = AppContainer(
        coordinator=coordinator,
        task_runner=AsyncTaskRunner(parts.store, parts.clock),
        settings=Settings(app_mode="live"),
        engine_version="1.0",
    )

    async def human(action, view):
        return '{"SECRET":"invalid command"}'

    with pytest.raises(ExecutionInterrupted) as caught:
        await execute_live(
            "Meals allowed.",
            human,
            lambda: None,
            container_factory=lambda guard: container,
        )
    assert caught.value.record.stage == "awaiting_contract"
    assert parts.scenario_planner.initial_calls == 0
    assert "SECRET" not in str(caught.value)


async def test_invalid_envelope_cannot_be_claimed_as_success(packet):
    from scripts.record_blind_run import RecorderError, record_blind_run

    options, record = packet
    bad = record.model_copy(
        update={
            "artifacts": (
                record.artifacts[0].model_copy(update={"artifact_sha256": "0" * 64}),
                *record.artifacts[1:],
            )
        }
    )

    async def execute(*args):
        return bad

    with pytest.raises(RecorderError, match="BLIND_RESULT_INVALID"):
        await record_blind_run(**options, executor=execute)
    audit = json.loads(
        options["output"]
        .with_name(options["output"].name + ".metadata.json")
        .read_text()
    )
    assert audit["status"] == "failed"


async def test_foreign_error_text_is_not_saved_as_a_code(packet):
    from scripts.record_blind_run import RecorderError, record_blind_run

    options, _ = packet

    async def execute(*args):
        raise RecorderError("SECRET-model-output")

    with pytest.raises(RecorderError, match="BLIND_EXECUTION_FAILED"):
        await record_blind_run(**options, executor=execute)
    assert (
        "SECRET"
        not in options["output"]
        .with_name(options["output"].name + ".metadata.json")
        .read_text()
    )


async def test_publication_failure_keeps_attempt_consumed(packet, monkeypatch):
    from scripts import record_blind_run as module

    options, record = packet
    original = module._publish

    def fail_output(source, target):
        if target == options["output"]:
            raise OSError("SECRET-local-failure")
        return original(source, target)

    monkeypatch.setattr(module, "_publish", fail_output)

    async def execute(*args):
        return record

    with pytest.raises(module.RecorderError, match="BLIND_PUBLICATION_FAILED"):
        await module.record_blind_run(**options, executor=execute)
    reservation = next(
        (options["root"] / ".git/policyfuzz-blind-attempts").glob("*.json")
    )
    audit = json.loads(reservation.read_text())
    assert audit["status"] == "publication_failed"
    assert "SECRET" not in reservation.read_text()
    options["output"] = options["output"].with_name("retry.json")
    with pytest.raises(module.RecorderError, match="BLIND_ALREADY_ATTEMPTED"):
        await module.record_blind_run(**options, executor=execute)


@pytest.mark.parametrize(
    "issue",
    [
        "reused_approval",
        "history",
        "early",
        "future",
        "naive_source",
        "missing_schema_time",
        "naive_provenance",
    ],
)
async def test_approval_separation_and_chronology_refuse_before_reservation(
    packet, issue
):
    from dataclasses import replace

    from scripts import record_blind_run as module

    options, _ = packet
    active_path = options["candidate_metadata"]
    active = json.loads(active_path.read_text())
    provenance_path = options["root"] / active["provenance"]
    approval_path = options["root"] / active["approval_evidence"]["path"]
    provenance = json.loads(provenance_path.read_text())
    approval = json.loads(approval_path.read_text())
    if issue == "reused_approval":
        approval_path = provenance_path
        approval = provenance | approval
        active["approval_evidence"]["path"] = active["provenance"]
    elif issue == "history":
        provenance.update(
            independent_human_review="complete", headline_gold_scoring_eligible=True
        )
        write(provenance_path, provenance)
    elif issue in {"early", "future"}:
        approval["timestamp"] = (
            "2000-01-01T00:00:00Z" if issue == "early" else "2099-01-01T00:00:00Z"
        )
    else:
        path = (
            options["source_seal"]
            if issue == "naive_source"
            else options["schema_seal"]
            if issue == "missing_schema_time"
            else provenance_path
        )
        value = json.loads(path.read_text())
        value["created_at"] = "2026-09-06T00:00:00"
        if issue == "missing_schema_time":
            value.pop("created_at")
        write(path, value)
    active["approval_evidence"]["sha256"] = write(approval_path, approval)
    write(active_path, active)
    old = options["snapshot"]()
    tracked = tuple(
        sorted(
            (name, hashlib.sha256((options["root"] / name).read_bytes()).hexdigest())
            for name, _ in old.tracked_inputs
            if issue != "reused_approval"
            or name != "submission/evidence/human-approval.json"
        )
    )
    frozen = replace(old, tracked_inputs=tracked)
    options["snapshot"] = lambda: frozen

    async def forbidden(*args):
        pytest.fail("Invalid approval reached execution")

    with pytest.raises(module.RecorderError, match="BLIND_(APPROVAL|PATH)_INVALID"):
        await module.record_blind_run(**options, executor=forbidden)
    assert not (options["root"] / ".git/policyfuzz-blind-attempts").exists()


@pytest.mark.parametrize("complete", [True, False])
async def test_cleanup_failure_preserves_latest_completed_or_partial_record(
    packet, complete
):
    from scripts.record_blind_run import ExecutionInterrupted, execute_live

    from app.container import AppContainer
    from app.core.config import Settings
    from app.domain.models import ConfirmRevisionRequest
    from app.workflow.task_runner import AsyncTaskRunner
    from tests.workflow.coordinator_fixtures import confirm, revision_harness, selection

    coordinator, parts = revision_harness()

    async def close():
        raise RuntimeError("SECRET-close-error")

    container = AppContainer(
        coordinator=coordinator,
        task_runner=AsyncTaskRunner(parts.store, parts.clock),
        settings=Settings(app_mode="live"),
        engine_version="1.0",
        close_provider=close,
    )

    async def human(action, view):
        if not complete:
            raise RuntimeError("SECRET-primary-error")
        commands = {
            "confirm_contract": lambda: confirm(view),
            "select_findings": selection,
            "confirm_revision": lambda: ConfirmRevisionRequest(
                proposal_id=view.pending_confirmation.proposal_id, decision="confirm"
            ),
        }
        return commands[action]().model_dump_json()

    from scripts.record_blind_run import RecorderError, record_blind_run

    options, _ = packet
    captured = []

    async def execute(policy, confirmation, guard):
        try:
            return await execute_live(
                policy, human, guard, container_factory=lambda guard: container
            )
        except ExecutionInterrupted as exc:
            captured.append(exc.record)
            raise

    with pytest.raises(RecorderError, match="BLIND_EXECUTION_FAILED"):
        await record_blind_run(**options, executor=execute)
    saved = RunRecord.model_validate_json(options["output"].read_bytes())
    assert saved == captured[0]
    assert saved.stage == ("complete" if complete else "awaiting_contract")
    sidecar = options["output"].with_name(options["output"].name + ".metadata.json")
    assert json.loads(sidecar.read_text())["status"] == "failed"
    assert "SECRET" not in sidecar.read_text()


@pytest.mark.parametrize("failure", ["sidecar", "final_reservation"])
async def test_publication_half_pair_is_removed_and_first_record_quarantined(
    packet, monkeypatch, failure
):
    from scripts import record_blind_run as module

    options, record = packet
    metadata_path = options["output"].with_name(
        options["output"].name + ".metadata.json"
    )
    atomic = module._atomic
    publish = module._publish

    def fail_publish(source, target):
        if failure == "sidecar" and target == metadata_path:
            raise OSError("SECRET-sidecar")
        return publish(source, target)

    monkeypatch.setattr(module, "_publish", fail_publish)

    def fail(path, data, **kwargs):
        if (
            failure == "final_reservation"
            and path.parent.name == "policyfuzz-blind-attempts"
            and json.loads(data)["status"] == "recorded"
        ):
            raise OSError("SECRET-final-update")
        return atomic(path, data, **kwargs)

    monkeypatch.setattr(module, "_atomic", fail)

    async def execute(*args):
        return record

    with pytest.raises(module.RecorderError, match="BLIND_PUBLICATION_FAILED"):
        await module.record_blind_run(**options, executor=execute)
    assert not options["output"].exists()
    assert not metadata_path.exists()
    reservation = next(
        (options["root"] / ".git/policyfuzz-blind-attempts").glob("*.json")
    )
    audit = json.loads(reservation.read_text())
    custody = reservation.with_suffix("")
    raw = (custody / "first-run.json").read_bytes()
    assert RunRecord.model_validate_json(raw) == record
    saved_audit = json.loads((custody / "metadata.json").read_text())
    assert saved_audit["result_bytes_sha256"] == hashlib.sha256(raw).hexdigest()
    assert saved_audit["status"] == audit["status"] == "publication_failed"
    options["output"] = options["output"].with_name("retry.json")
    with pytest.raises(module.RecorderError, match="BLIND_ALREADY_ATTEMPTED"):
        await module.record_blind_run(**options, executor=execute)


@pytest.mark.parametrize("failure", ["after_sidecar_link", "foreign_sidecar"])
async def test_publication_rollback_removes_only_owned_links(
    packet, monkeypatch, failure
):
    from scripts import record_blind_run as module

    options, record = packet
    output = options["output"]
    sidecar = output.with_name(output.name + ".metadata.json")
    publish = module._publish

    def injected(source, target):
        # Both custody files must already exist before the first canonical write.
        custody = source.parent
        raw = (custody / "first-run.json").read_bytes()
        audit = json.loads((custody / "metadata.json").read_text())
        assert audit["result_bytes_sha256"] == hashlib.sha256(raw).hexdigest()
        if target == sidecar and failure == "foreign_sidecar":
            target.write_text("unrelated evidence")
        publish(source, target)
        if target == sidecar and failure == "after_sidecar_link":
            raise OSError("SECRET-sync-failure")

    monkeypatch.setattr(module, "_publish", injected)

    async def execute(*args):
        return record

    with pytest.raises(module.RecorderError, match="BLIND_PUBLICATION_FAILED"):
        await module.record_blind_run(**options, executor=execute)
    assert not output.exists()
    if failure == "foreign_sidecar":
        assert sidecar.read_text() == "unrelated evidence"
    else:
        assert not sidecar.exists()
    reservation = next(
        (options["root"] / ".git/policyfuzz-blind-attempts").glob("*.json")
    )
    custody = reservation.with_suffix("")
    assert (
        RunRecord.model_validate_json((custody / "first-run.json").read_bytes())
        == record
    )
    assert (
        json.loads((custody / "metadata.json").read_text())["status"]
        == "publication_failed"
    )
