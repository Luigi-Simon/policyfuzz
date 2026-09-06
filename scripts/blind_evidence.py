"""Bind a preserved attempt to its approved source, sealed labels and Git tag."""

from __future__ import annotations

import hashlib
import json
import re
import subprocess
from datetime import UTC, datetime
from pathlib import Path

from app.core.artifacts import complete_payload_projection
from app.core.hashing import canonical_sha256
from app.domain.models import RunRecord
from app.features.evaluation.gold_assessment import validate_revealed_benchmark

from scripts.record_blind_run import RUNTIME_FIELDS, _preflight


def _require(condition: bool) -> None:
    if not condition:
        raise ValueError("Blind evidence is not bound to the approved frozen attempt.")


def _time(value: str) -> datetime:
    result = datetime.fromisoformat(value.replace("Z", "+00:00"))
    _require(result.utcoffset() is not None)
    return result


def _path(root: Path, name: str) -> Path:
    _require(isinstance(name, str) and not Path(name).is_absolute())
    path = root / name
    _require(
        path.resolve().is_relative_to(root.resolve())
        and not any(part.is_symlink() for part in (path, *path.parents))
        and path.is_file()
    )
    return path


def bind_first_run(
    root: Path,
    active: dict,
    record: RunRecord,
    metadata: dict,
    *,
    now: datetime | None = None,
) -> tuple[str, ...]:
    """Validate source/custody identity; the caller separately verifies live mode and scores."""
    now = now or datetime.now(UTC)
    _require(
        metadata.get("schema_version") == "1.0" and metadata.get("error_code") is None
    )
    _require(
        metadata.get("result_sha256")
        == canonical_sha256(complete_payload_projection(record))
    )
    _require(
        metadata.get("stage") == record.stage
        and metadata.get("run_id") == record.run_id
    )
    started, completed = _time(metadata["started_at"]), _time(metadata["completed_at"])
    _require(started <= record.manifest.started_at <= completed <= now)
    runtime = metadata.get("runtime")
    values = record.manifest.model_dump(mode="json")
    _require(
        isinstance(runtime, dict)
        and runtime == {key: values[key] for key in RUNTIME_FIELDS}
    )
    inputs = metadata.get("input_bytes_sha256")
    _require(isinstance(inputs, dict) and len(inputs) == 6)
    policy_paths = [
        name
        for name, digest in inputs.items()
        if digest == active["source_policy_sha256"] and Path(name).suffix == ".txt"
    ]
    _require(len(policy_paths) == 1)
    policy = _path(root, policy_paths[0])
    source_seal = _path(root, active["source_seal"])
    schema_seal = _path(root, active["schema_seal"])
    text, binding, actual_inputs = _preflight(
        root,
        policy,
        source_seal,
        schema_seal,
        root / "submission/evidence/active-benchmark.json",
        started,
    )
    _require(binding == metadata.get("candidate") and actual_inputs == inputs)
    documents = [
        a.payload for a in record.artifacts if a.artifact_type == "policy_document"
    ]
    _require(len(documents) == 1)
    document = documents[0]
    offset = 0
    for page in document.pages:
        _require(page.start == offset and page.end == offset + len(page.text))
        offset = page.end
    _require("".join(page.text for page in document.pages) == text)
    _require(
        document.document_sha256
        == hashlib.sha256(text.encode()).hexdigest()
        == active["source_policy_sha256"]
    )
    baselines = [
        a.payload
        for a in record.artifacts
        if a.artifact_type == "policy_ir" and a.payload.kind == "compiled_baseline"
    ]
    _require(
        bool(baselines)
        and all(p.document_sha256 == document.document_sha256 for p in baselines)
    )
    schema = json.loads(schema_seal.read_bytes())
    validate_revealed_benchmark(root / "samples/benchmarks/blind", schema)
    for key in ("commit", "tag_object", "tree"):
        _require(
            isinstance(metadata.get(key), str)
            and re.fullmatch("[0-9a-f]{40}", metadata[key]) is not None
        )
    tag = metadata.get("tag")
    _require(
        isinstance(tag, str)
        and re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._/-]{0,199}", tag) is not None
        and ".." not in tag
    )

    def git(*args: str) -> bytes:
        try:
            return subprocess.check_output(
                ("git", *args), cwd=root, stderr=subprocess.DEVNULL
            )
        except subprocess.SubprocessError:
            raise ValueError(
                "Frozen blind Git provenance cannot be verified."
            ) from None

    reference = "refs/tags/" + tag
    _require(git("cat-file", "-t", reference).strip() == b"tag")
    _require(git("rev-parse", reference).decode().strip() == metadata["tag_object"])
    _require(
        git("rev-parse", reference + "^{commit}").decode().strip() == metadata["commit"]
    )
    _require(
        git("rev-parse", metadata["commit"] + "^{tree}").decode().strip()
        == metadata["tree"]
    )
    git("merge-base", "--is-ancestor", metadata["commit"], "HEAD")
    for name, digest in inputs.items():
        _path(root, name)
        _require(
            hashlib.sha256(git("show", metadata["commit"] + ":" + name)).hexdigest()
            == digest
        )
    return tuple(sorted(inputs)) + tuple(
        "samples/benchmarks/blind/" + name for name in sorted(schema["artifact_hashes"])
    )
