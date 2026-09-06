#!/usr/bin/env python3
"""Record one approved, revealed blind policy from a clean annotated Git tag.

No private archive or label input is accepted. An exclusive reservation in the
Git common directory survives failed/interrupted runs and alternate output paths.
The output is a strict RunRecord; its public audit is OUTPUT.metadata.json.
Historical provenance is immutable: approval is a separate hash-bound human
record referenced by active-benchmark.json's approval_evidence {path, sha256}.
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import os
import re
import subprocess
import sys
import tempfile
import unicodedata
from collections.abc import Awaitable, Callable, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT / "backend") not in sys.path:
    sys.path.insert(0, str(ROOT / "backend"))

from app.core.artifacts import complete_payload_projection, validate_artifact_envelope
from app.core.hashing import canonical_sha256
from app.domain.models import RunRecord, RunView

ARTIFACT_NAMES = frozenset(
    {
        "source-labels.json",
        "canonical-policy-ir.json",
        "confirmed-contract.json",
        "frozen-suite.json",
        "expected-effects.json",
        "defect-manifest.json",
        "corrected-semantics.json",
    }
)
RUNTIME_FIELDS = (
    "provider",
    "model_identifier",
    "generation_config",
    "engine_version",
    "engine_sha256",
    "prompt_hashes",
    "random_seed",
)
Confirmation = Callable[[str, RunView], Awaitable[str]]


class RecorderError(ValueError):
    """A fixed public error code, never provider output or policy content."""


@dataclass(frozen=True)
class GitSnapshot:
    commit: str
    tag_object: str
    tag_commit: str
    tree: str
    tag_type: str
    dirty: bool
    common_dir: Path
    tracked_inputs: tuple[tuple[str, str], ...] = ()


class ExecutionInterrupted(Exception):
    def __init__(self, record: RunRecord | None):
        self.record = record
        super().__init__("BLIND_EXECUTION_FAILED")


def require(condition: bool, code: str) -> None:
    if not condition:
        raise RecorderError(code)


def git_snapshot(root: Path, tag: str, input_paths: Sequence[str] = ()) -> GitSnapshot:
    require(
        bool(re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._/-]{0,199}", tag))
        and ".." not in tag,
        "BLIND_TAG_INVALID",
    )

    def git(*arguments: str) -> str:
        try:
            return subprocess.check_output(
                ("git", *arguments), cwd=root, text=True, stderr=subprocess.DEVNULL
            ).strip()
        except subprocess.SubprocessError:
            raise RecorderError("BLIND_TAG_INVALID") from None

    reference = "refs/tags/" + tag
    commit = git("rev-parse", "HEAD")
    try:
        tracked = tuple(
            sorted(
                (
                    name,
                    _sha(
                        subprocess.check_output(
                            ("git", "show", commit + ":" + name),
                            cwd=root,
                            stderr=subprocess.DEVNULL,
                        )
                    ),
                )
                for name in input_paths
            )
        )
    except subprocess.SubprocessError:
        raise RecorderError("BLIND_TAG_INPUT_MISMATCH") from None
    return GitSnapshot(
        commit=git("rev-parse", "HEAD"),
        tag_object=git("rev-parse", reference),
        tag_commit=git("rev-parse", reference + "^{commit}"),
        tree=git("rev-parse", "HEAD^{tree}"),
        tag_type=git("cat-file", "-t", reference),
        dirty=bool(git("status", "--porcelain", "--untracked-files=all")),
        common_dir=(root / git("rev-parse", "--git-common-dir")).resolve(),
        tracked_inputs=tracked,
    )


def _no_symlinks(path: Path) -> None:
    require(
        not any(item.is_symlink() for item in (path, *path.parents)),
        "BLIND_PATH_INVALID",
    )


def _read(path: Path, limit: int = 65_536) -> bytes:
    _no_symlinks(path)
    require(path.is_file() and path.stat().st_size <= limit, "BLIND_INPUT_INVALID")
    with path.open("rb") as stream:
        data = stream.read(limit + 1)
    require(len(data) <= limit, "BLIND_INPUT_INVALID")
    return data


def _json(path: Path) -> dict[str, Any]:
    def unique(pairs):
        result = {}
        for key, value in pairs:
            require(key not in result, "BLIND_METADATA_INVALID")
            result[key] = value
        return result

    def invalid(value):
        raise RecorderError("BLIND_METADATA_INVALID")

    try:
        value = json.loads(
            _read(path), object_pairs_hook=unique, parse_constant=invalid
        )
    except (UnicodeError, json.JSONDecodeError):
        raise RecorderError("BLIND_METADATA_INVALID") from None
    require(isinstance(value, dict), "BLIND_METADATA_INVALID")
    return value


def _public_path(root: Path, value: str) -> Path:
    require(isinstance(value, str), "BLIND_METADATA_INVALID")
    path = root / value
    _no_symlinks(path)
    require(path.resolve().is_relative_to(root.resolve()), "BLIND_PATH_INVALID")
    require(
        path.suffix == ".json" and path.name not in ARTIFACT_NAMES, "BLIND_PATH_INVALID"
    )
    return path


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _timestamp(value: datetime) -> str:
    require(
        isinstance(value, datetime) and value.utcoffset() is not None,
        "BLIND_CLOCK_INVALID",
    )
    return value.astimezone(UTC).isoformat()


def _hex(value: object) -> bool:
    return isinstance(value, str) and re.fullmatch("[0-9a-f]{64}", value) is not None


def _approval_time(value: object) -> datetime:
    try:
        require(isinstance(value, str), "BLIND_APPROVAL_INVALID")
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        require(parsed.utcoffset() is not None, "BLIND_APPROVAL_INVALID")
        return parsed.astimezone(UTC)
    except (TypeError, ValueError):
        raise RecorderError("BLIND_APPROVAL_INVALID") from None


def _preflight(
    root: Path,
    policy: Path,
    source_seal: Path,
    schema_seal: Path,
    active_path: Path,
    started_at: datetime,
):
    require(
        active_path.resolve().is_relative_to(root.resolve())
        and active_path.name not in ARTIFACT_NAMES,
        "BLIND_PATH_INVALID",
    )
    active = _json(active_path)
    # Do not read the revealed policy or construct a provider before approval.
    require(
        active.get("human_review") == "approved"
        and active.get("headline_gold_scoring_eligible") is True,
        "BLIND_APPROVAL_PENDING",
    )
    require(
        active.get("schema_version") == "1.0"
        and type(active.get("candidate_version")) is int
        and active["candidate_version"] > 0,
        "BLIND_METADATA_INVALID",
    )
    source_path = _public_path(root, active.get("source_seal"))
    schema_path = _public_path(root, active.get("schema_seal"))
    require(
        source_path.resolve() == source_seal.resolve()
        and schema_path.resolve() == schema_seal.resolve(),
        "BLIND_CHAIN_MISMATCH",
    )
    require(
        source_path.name == "blind-seal.json"
        and schema_path.name == "blind-schema-seal.json",
        "BLIND_CHAIN_MISMATCH",
    )
    provenance_path = _public_path(root, active.get("provenance"))
    source, schema, provenance = (
        _json(source_path),
        _json(schema_path),
        _json(provenance_path),
    )
    binding = {
        key: active.get(key)
        for key in (
            "candidate_version",
            "source_policy_sha256",
            "schema_archive_sha256",
        )
    }
    require(
        _hex(binding["source_policy_sha256"])
        and _hex(binding["schema_archive_sha256"]),
        "BLIND_METADATA_INVALID",
    )
    require(
        all(provenance.get(key) == value for key, value in binding.items()),
        "BLIND_CHAIN_MISMATCH",
    )
    require(
        source.get("policy_sha256")
        == schema.get("source_policy_sha256")
        == binding["source_policy_sha256"],
        "BLIND_CHAIN_MISMATCH",
    )
    require(
        schema.get("archive_sha256") == binding["schema_archive_sha256"],
        "BLIND_CHAIN_MISMATCH",
    )
    require(
        _hex(source.get("archive_sha256"))
        and source["archive_sha256"] == provenance.get("source_archive_sha256"),
        "BLIND_CHAIN_MISMATCH",
    )
    require(
        _hex(source.get("manifest_sha256")) and _hex(source.get("defect_ids_sha256")),
        "BLIND_METADATA_INVALID",
    )
    require(
        source["defect_ids_sha256"]
        == schema.get("defect_ids_sha256")
        == provenance.get("defect_ids_sha256")
        == active.get("defect_ids_sha256"),
        "BLIND_CHAIN_MISMATCH",
    )
    require(
        source.get("defect_count") == schema.get("defect_count") == 3
        and type(schema.get("rule_count")) is int
        and 8 <= schema["rule_count"] <= 10
        and schema.get("scenario_count") == 15
        and schema.get("schema_version") == "1.0",
        "BLIND_METADATA_INVALID",
    )
    hashes = schema.get("artifact_hashes")
    require(
        isinstance(hashes, dict)
        and hashes.keys() == ARTIFACT_NAMES
        and all(_hex(value) for value in hashes.values()),
        "BLIND_METADATA_INVALID",
    )
    evidence = active.get("approval_evidence")
    require(
        isinstance(evidence, dict) and _hex(evidence.get("sha256")),
        "BLIND_APPROVAL_PENDING",
    )
    approval_path = _public_path(root, evidence.get("path"))
    paths = (
        active_path,
        source_path,
        schema_path,
        provenance_path,
        approval_path,
        policy,
    )
    require(len({path.resolve() for path in paths}) == len(paths), "BLIND_PATH_INVALID")
    require(
        provenance.get("independent_human_review") == "pending"
        and provenance.get("headline_gold_scoring_eligible") is False,
        "BLIND_APPROVAL_INVALID",
    )
    require(_sha(_read(approval_path)) == evidence["sha256"], "BLIND_APPROVAL_INVALID")
    approval = _json(approval_path)
    require(
        approval.get("reviewer_type") == "human"
        and approval.get("decision") == "approve"
        and isinstance(approval.get("reviewer_id"), str)
        and bool(approval["reviewer_id"].strip())
        and all(approval.get(key) == value for key, value in binding.items()),
        "BLIND_APPROVAL_INVALID",
    )
    approval_time = _approval_time(approval.get("timestamp"))
    created = [
        _approval_time(item.get("created_at")) for item in (source, schema, provenance)
    ]
    require(max(created) <= approval_time <= started_at, "BLIND_APPROVAL_INVALID")
    require(policy.resolve().is_relative_to(root.resolve()), "BLIND_PATH_INVALID")
    raw = _read(policy, 200_000)
    require(_sha(raw) == binding["source_policy_sha256"], "BLIND_POLICY_MISMATCH")
    try:
        text = raw.decode("utf-8")
    except UnicodeError:
        raise RecorderError("BLIND_POLICY_INVALID") from None
    require(
        0 < len(text) <= 50_000
        and bool(text.strip())
        and unicodedata.normalize("NFC", text.replace("\r\n", "\n").replace("\r", "\n"))
        == text,
        "BLIND_POLICY_INVALID",
    )
    identities = {(path.stat().st_dev, path.stat().st_ino) for path in paths}
    require(len(identities) == len(paths), "BLIND_PATH_INVALID")
    inputs = {str(path.relative_to(root)): _sha(_read(path, 200_000)) for path in paths}
    return text, binding, inputs


def runtime_metadata() -> dict[str, Any]:
    """Read public configuration and source commitments without constructing an SDK."""
    from app.container import make_manifest_factory
    from app.core.config import Settings
    from app.workflow.types import SystemClock

    settings = Settings(app_mode="live")
    require(
        bool(settings.llm_model and settings.openai_api_key),
        "BLIND_PROVIDER_NOT_CONFIGURED",
    )
    manifest = make_manifest_factory(settings, SystemClock())(
        "blind-runtime-metadata", "live"
    )
    values = manifest.model_dump(mode="json")
    return {field: values[field] for field in RUNTIME_FIELDS}


def _bytes(value: object) -> bytes:
    return (
        json.dumps(value, sort_keys=True, ensure_ascii=False, indent=2, allow_nan=False)
        + "\n"
    ).encode("utf-8")


def _sync_directory(path: Path) -> None:
    descriptor = os.open(path, os.O_RDONLY)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def _durable_mkdir(path: Path) -> None:
    missing = []
    cursor = path
    while not cursor.exists():
        missing.append(cursor)
        cursor = cursor.parent
    for directory in reversed(missing):
        directory.mkdir(exist_ok=True)
        _sync_directory(directory.parent)


def _validate_envelopes(record: RunRecord) -> None:
    known = set()
    require(
        sum(item.artifact_type == "run_manifest" for item in record.artifacts) == 1,
        "BLIND_RESULT_INVALID",
    )
    try:
        for artifact in record.artifacts:
            validate_artifact_envelope(artifact)
            require(
                artifact.run_manifest_id == record.manifest.manifest_id
                and set(artifact.parent_hashes) <= known,
                "BLIND_RESULT_INVALID",
            )
            if artifact.artifact_type == "run_manifest":
                require(artifact.payload == record.manifest, "BLIND_RESULT_INVALID")
            known.add(artifact.artifact_sha256)
    except (TypeError, ValueError):
        raise RecorderError("BLIND_RESULT_INVALID") from None


def _atomic(path: Path, data: bytes, *, replace: bool = False) -> None:
    _no_symlinks(path)
    _durable_mkdir(path.parent)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(dir=path.parent, delete=False) as stream:
            temporary = Path(stream.name)
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        if replace:
            os.replace(temporary, path)
        else:
            try:
                os.link(temporary, path)
            except FileExistsError:
                raise RecorderError("BLIND_OUTPUT_EXISTS") from None
        _sync_directory(path.parent)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def _publish(source: Path, target: Path) -> None:
    """Exclusively expose an already durable file without replacing another file."""
    _no_symlinks(target)
    _durable_mkdir(target.parent)
    try:
        os.link(source, target)
    except FileExistsError:
        raise RecorderError("BLIND_OUTPUT_EXISTS") from None
    _sync_directory(target.parent)


def _remove_owned_link(source: Path, target: Path) -> None:
    """Rollback only a link to this attempt's inode, never an unrelated file."""
    try:
        original = source.stat(follow_symlinks=False)
        published = target.stat(follow_symlinks=False)
    except FileNotFoundError:
        return
    if (original.st_dev, original.st_ino) == (published.st_dev, published.st_ino):
        target.unlink()
        _sync_directory(target.parent)


def _reserve(path: Path, metadata: dict[str, Any]) -> None:
    _no_symlinks(path)
    _durable_mkdir(path.parent)
    try:
        descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    except FileExistsError:
        raise RecorderError("BLIND_ALREADY_ATTEMPTED") from None
    with os.fdopen(descriptor, "wb") as stream:
        stream.write(_bytes(metadata))
        stream.flush()
        os.fsync(stream.fileno())
    _sync_directory(path.parent)


async def interactive_confirmation(action: str, view: RunView) -> str:
    print(
        json.dumps(
            {"action": action, "review": view.model_dump(mode="json")},
            ensure_ascii=False,
        )
    )
    return await asyncio.to_thread(
        input, "Paste the complete reviewed command JSON (no automatic approval): "
    )


def _live_container(guard: Callable[[], None]):
    from app.container import build_container
    from app.core.config import Settings
    from app.core.llm_openai import OpenAILLMClient

    settings = Settings(app_mode="live")

    class GuardedClient:
        adapter = None

        async def complete_json(self, request):
            guard()
            if self.adapter is None:
                self.adapter = OpenAILLMClient.from_settings(settings)
            response = await self.adapter.complete_json(request)
            guard()
            return response

        async def aclose(self):
            if self.adapter is not None:
                await self.adapter.aclose()

    client = GuardedClient()
    container = build_container(settings, llm=client)
    container.close_provider = client.aclose
    return container


async def execute_live(
    policy_text: str,
    confirmation: Confirmation,
    guard: Callable[[], None],
    *,
    container_factory: Callable = _live_container,
) -> RunRecord:
    """Run real stages, pausing for explicit JSON commands at all review gates."""
    from app.domain.models import (
        ConfirmContractRequest,
        ConfirmRevisionRequest,
        CreateRunRequest,
        SelectFindingsRequest,
    )

    guard()
    container = None
    latest = None
    try:
        container = container_factory(guard)
        container.task_runner.start()
        coordinator = container.coordinator
        created = await coordinator.create_run(
            CreateRunRequest(
                source_type="pasted_text",
                title="SYNTHETIC BLIND POLICY — REVEALED SOURCE",
                text=policy_text,
                non_confidential_confirmed=True,
            )
        )

        async def capture():
            stored = await coordinator.store.get(created.run_id)
            return RunRecord.model_validate_json(
                stored.model_dump_json(
                    exclude={"version", "source_request", "pending_confirmation"}
                )
            )

        latest = await capture()
        await container.task_runner.run(
            created.run_id,
            lambda: container.execute(
                created.run_id, lambda: coordinator.start(created.run_id)
            ),
        )
        latest = await capture()
        gates = {
            "awaiting_contract": ("confirm_contract", ConfirmContractRequest),
            "awaiting_finding_review": ("select_findings", SelectFindingsRequest),
            "awaiting_revision_confirmation": (
                "confirm_revision",
                ConfirmRevisionRequest,
            ),
        }
        while True:
            view = await coordinator.get_run(created.run_id)
            if view.stage not in gates:
                return latest
            action, model = gates[view.stage]
            guard()
            raw = await confirmation(action, view)
            command = model.model_validate_json(raw)
            guard()
            method = getattr(coordinator, action)
            await container.task_runner.run(
                created.run_id,
                lambda method=method, command=command: container.execute(
                    created.run_id, lambda: method(created.run_id, command)
                ),
            )
            latest = await capture()
    except BaseException:  # noqa: BLE001 - preserve even interrupted first attempts
        raise ExecutionInterrupted(latest) from None
    finally:
        if container is not None:
            try:
                await container.aclose()
            except BaseException:  # noqa: BLE001 - cleanup must not discard captured evidence
                raise ExecutionInterrupted(latest) from None


async def record_blind_run(
    *,
    root: Path,
    tag: str,
    policy: Path,
    source_seal: Path,
    schema_seal: Path,
    output: Path,
    candidate_metadata: Path | None = None,
    executor: Callable[
        [str, Confirmation, Callable[[], None]], Awaitable[RunRecord]
    ] = execute_live,
    confirmation: Confirmation = interactive_confirmation,
    snapshot: Callable[[], GitSnapshot] | None = None,
    runtime_metadata: Callable[[], dict[str, Any]] = runtime_metadata,
    now: Callable[[], datetime] = lambda: datetime.now(UTC),
) -> dict[str, Any]:
    root = root.absolute()
    metadata_path = output.with_name(output.name + ".metadata.json")
    require(
        not os.path.lexists(output) and not os.path.lexists(metadata_path),
        "BLIND_OUTPUT_EXISTS",
    )
    _no_symlinks(output)
    active = (
        candidate_metadata
        if candidate_metadata is not None
        else root / "submission/evidence/active-benchmark.json"
    )
    started_at = now()
    started_at_text = _timestamp(started_at)
    policy_text, binding, inputs = _preflight(
        root, policy, source_seal, schema_seal, active, started_at
    )
    snapshot = snapshot or (lambda: git_snapshot(root, tag, tuple(inputs)))
    frozen = snapshot()
    require(
        not frozen.dirty
        and frozen.tag_type == "tag"
        and frozen.commit == frozen.tag_commit
        and all(
            re.fullmatch(r"(?:[0-9a-f]{40}|[0-9a-f]{64})", value)
            for value in (frozen.commit, frozen.tag_object, frozen.tree)
        ),
        "BLIND_CLEAN_ANNOTATED_TAG_REQUIRED",
    )
    require(
        frozen.tracked_inputs == tuple(sorted(inputs.items())),
        "BLIND_TAG_INPUT_MISMATCH",
    )
    runtime = json.loads(_bytes(runtime_metadata()))
    attempt_id = canonical_sha256(
        {key: binding[key] for key in ("source_policy_sha256", "schema_archive_sha256")}
    )
    reservation = (
        frozen.common_dir / "policyfuzz-blind-attempts" / (attempt_id + ".json")
    )
    metadata = {
        "schema_version": "1.0",
        "status": "reserved",
        "attempt_id": attempt_id,
        "tag": tag,
        "tag_object": frozen.tag_object,
        "commit": frozen.commit,
        "tree": frozen.tree,
        "candidate": binding,
        "input_bytes_sha256": inputs,
        "runtime": runtime,
        "started_at": started_at_text,
    }
    _reserve(reservation, metadata)

    def guard() -> None:
        require(
            snapshot() == frozen and runtime_metadata() == runtime,
            "BLIND_FROZEN_INPUT_CHANGED",
        )
        try:
            require(
                all(
                    _sha(_read(root / name, 200_000)) == digest
                    for name, digest in inputs.items()
                ),
                "BLIND_FROZEN_INPUT_CHANGED",
            )
        except (OSError, RecorderError):
            raise RecorderError("BLIND_FROZEN_INPUT_CHANGED") from None

    record = None
    error_code = None
    try:
        guard()
        produced = await executor(policy_text, confirmation, guard)
        record = RunRecord.model_validate_json(produced.model_dump_json())
        guard()
        _validate_envelopes(record)
        manifest = record.manifest.model_dump(mode="json")
        require(
            record.manifest.mode == "live"
            and {key: manifest[key] for key in RUNTIME_FIELDS} == runtime,
            "BLIND_RESULT_INVALID",
        )
        documents = [
            item.payload
            for item in record.artifacts
            if item.artifact_type == "policy_document"
        ]
        require(
            len(documents) == 1
            and documents[0].document_sha256 == binding["source_policy_sha256"]
            and len(documents[0].pages) == 1
            and documents[0].pages[0].text == policy_text,
            "BLIND_RESULT_INVALID",
        )
        require(
            record.stage
            in {"complete", "completed_no_findings", "completed_no_revision"},
            "BLIND_RUN_INCOMPLETE",
        )
    except ExecutionInterrupted as exc:
        error_code = "BLIND_EXECUTION_FAILED"
        if exc.record is not None:
            try:
                record = RunRecord.model_validate_json(exc.record.model_dump_json())
            except (TypeError, ValueError, AttributeError):
                record = None
    except RecorderError as exc:
        error_code = (
            str(exc)
            if str(exc)
            in {
                "BLIND_FROZEN_INPUT_CHANGED",
                "BLIND_RESULT_INVALID",
                "BLIND_RUN_INCOMPLETE",
            }
            else "BLIND_EXECUTION_FAILED"
        )
    except BaseException:  # noqa: BLE001 - preserve even interrupted first attempts
        error_code = "BLIND_EXECUTION_FAILED"
    metadata.update(
        status="recorded"
        if error_code is None
        else "invalidated"
        if error_code == "BLIND_FROZEN_INPUT_CHANGED"
        else "failed",
        completed_at=_timestamp(now()),
        error_code=error_code,
    )
    custody = reservation.with_suffix("")
    custody_raw = custody / "first-run.json"
    custody_audit = custody / "metadata.json"
    publications = []
    try:
        if record is not None:
            data = _bytes(record.model_dump(mode="json"))
            metadata.update(
                run_id=record.run_id,
                stage=record.stage,
                result_bytes_sha256=_sha(data),
                result_sha256=canonical_sha256(complete_payload_projection(record)),
            )
            _atomic(custody_raw, data)
            publications.append((custody_raw, output))
        # Both first-attempt files are durable before exposing either canonical name.
        _atomic(custody_audit, _bytes(metadata))
        publications.append((custody_audit, metadata_path))
        _atomic(reservation, _bytes(metadata | {"status": "publishing"}), replace=True)
        for source, target in publications:
            _publish(source, target)
        _atomic(reservation, _bytes(metadata), replace=True)
    except BaseException:  # noqa: BLE001 - preserve interrupted publication without raw errors
        # Include a link created just before a sync failure; inspect inode ownership
        # even if _publish raised before returning. Never unlink another writer's file.
        for source, target in publications:
            try:
                _remove_owned_link(source, target)
            except OSError:
                pass
        metadata.update(
            status="publication_failed", error_code="BLIND_PUBLICATION_FAILED"
        )
        for audit_path in (custody_audit, reservation):
            try:
                _atomic(audit_path, _bytes(metadata), replace=True)
            except (OSError, RecorderError):
                # The exclusive reservation remains consumed even during storage
                # failure. Any already durable raw result remains in custody.
                pass
        raise RecorderError("BLIND_PUBLICATION_FAILED") from None
    if error_code is not None:
        raise RecorderError(error_code) from None
    return metadata


class _SafeParser(argparse.ArgumentParser):
    def error(self, message: str) -> None:
        self.exit(2, "BLIND_CLI_ARGUMENTS\n")


def main(argv: Sequence[str] | None = None) -> int:
    parser = _SafeParser(description=__doc__)
    for flag in ("tag", "policy", "source-seal", "schema-seal", "output"):
        parser.add_argument(
            "--" + flag, required=True, type=str if flag == "tag" else Path
        )
    parser.add_argument(
        "--candidate-metadata",
        type=Path,
        default=ROOT / "submission/evidence/active-benchmark.json",
    )
    args = parser.parse_args(argv)
    try:
        metadata = asyncio.run(
            record_blind_run(
                root=ROOT,
                tag=args.tag,
                policy=args.policy.absolute(),
                source_seal=args.source_seal.absolute(),
                schema_seal=args.schema_seal.absolute(),
                output=args.output.absolute(),
                candidate_metadata=args.candidate_metadata.absolute(),
            )
        )
    except (RecorderError, OSError, ValueError, subprocess.SubprocessError):
        print(
            "Blind run refused or preserved as failed. Check approval, seals, frozen tag, and attempt metadata; no retry is permitted after reservation.",
            file=sys.stderr,
        )
        return 1
    print(
        json.dumps(
            {
                "status": metadata["status"],
                "run_id": metadata["run_id"],
                "result_sha256": metadata["result_sha256"],
            }
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
