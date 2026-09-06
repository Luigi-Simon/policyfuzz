"""Fresh replay sessions with an explicitly rebased, validated evidence graph."""

from pydantic import BaseModel

from app.core.artifacts import complete_payload_projection, make_artifact_envelope
from app.core.hashing import canonical_sha256
from app.domain.models import ArtifactRef, InputHashes, RunRecord
from app.workflow.validation import validate_cached_record


def _digest(value):
    return canonical_sha256(complete_payload_projection(value))


def _manifest_inputs(value, manifest_sha256):
    """Rewrite only typed manifest anchors, including nested comparison metrics."""
    if isinstance(value, InputHashes):
        return value.model_copy(update={"run_manifest_sha256": manifest_sha256})
    if isinstance(value, BaseModel):
        changes = {}
        for name in type(value).model_fields:
            current = getattr(value, name)
            updated = _manifest_inputs(current, manifest_sha256)
            if updated is not current:
                changes[name] = updated
        return (
            type(value).model_validate(value.model_copy(update=changes))
            if changes
            else value
        )
    if isinstance(value, tuple):
        updated = tuple(_manifest_inputs(item, manifest_sha256) for item in value)
        return (
            value
            if all(
                before is after for before, after in zip(value, updated, strict=True)
            )
            else updated
        )
    return value


def _reference(envelope):
    return ArtifactRef(
        artifact_type=envelope.artifact_type,
        artifact_sha256=envelope.artifact_sha256,
        semantic_sha256=envelope.semantic_sha256,
    )


def rebase_cached_record(source: RunRecord, run_id: str) -> RunRecord:
    """Preserve recorded semantics/provenance while minting a new session graph.

    The manifest identity carries the complete canonical source-record digest.
    Its recorded time, model/configuration, engine and prompt commitments stay
    intact. Policy, contract, suite, proposal and scenario identities never move.
    All report InputHashes, envelope parents and event references are rebuilt,
    then the complete graph is checked again before storage.
    """
    source = validate_cached_record(source)
    manifest = source.manifest.model_copy(
        update={
            "run_id": run_id,
            "manifest_id": f"replay-{_digest(source)}-{canonical_sha256(run_id)[:32]}",
        }
    )
    manifest_sha256 = _digest(manifest)
    mapping = {}
    artifacts = []
    for original in source.artifacts:
        payload = (
            manifest
            if original.artifact_type == "run_manifest"
            else _manifest_inputs(original.payload, manifest_sha256)
        )
        replay = make_artifact_envelope(
            artifact_type=original.artifact_type,
            payload=payload,
            parent_refs=tuple(
                _reference(mapping[digest]) for digest in original.parent_hashes
            ),
            run_manifest_id=manifest.manifest_id,
        )
        artifacts.append(replay)
        mapping[original.artifact_sha256] = replay
    events = tuple(
        event
        if event.artifact is None
        else event.model_copy(
            update={"artifact": _reference(mapping[event.artifact.artifact_sha256])}
        )
        for event in source.events
    )
    record = RunRecord.model_validate(
        source.model_copy(
            update={
                "run_id": run_id,
                "manifest": manifest,
                "artifacts": tuple(artifacts),
                "events": events,
            }
        )
    )
    return validate_cached_record(record)
