"""Deterministic artifact construction and explicit version-1 hash projections."""

import json
from collections.abc import Iterable, Mapping

from pydantic import BaseModel

from app.core.hashing import canonical_sha256, normalize_for_hash
from app.domain.models import (
    ApplyRevisionRequest,
    ArtifactEnvelope,
    ArtifactPayload,
    ArtifactRef,
    ArtifactSummary,
    ArtifactType,
    BenchmarkManifest,
    CreateRunRequest,
    EvaluationTrace,
    FindingSummary,
    Invariant,
    InvariantDraft,
    InvariantSummary,
    PolicyDocument,
    RevisionConfirmation,
    RevisionProposal,
    RevisionRuleDraft,
    Rule,
    RuleDraft,
    RuleSummary,
    RunEvent,
    RunManifest,
    RunRecord,
    RunView,
    ScenarioSuite,
    SessionRevisionProvenance,
)

# Only actual self-digests are omitted. Document hashes, quote hashes, input
# hashes, ArtifactRef hashes and TraceRef hashes remain integrity anchors.
_COMPLETE_EXCLUSIONS = {
    ArtifactEnvelope: frozenset({"artifact_sha256", "semantic_sha256"}),
    ScenarioSuite: frozenset({"content_sha256"}),
    EvaluationTrace: frozenset({"trace_sha256"}),
}

# Exact classes are intentional: a future domain model with a field named
# "description" or "timestamp" does not silently inherit a hashing exclusion.
_SEMANTIC_EXCLUSIONS = {
    PolicyDocument: frozenset({"title"}),
    RuleDraft: frozenset({"description", "confidence_percent"}),
    Rule: frozenset({"description", "confidence_percent"}),
    RuleSummary: frozenset({"description", "confidence_percent"}),
    InvariantDraft: frozenset({"description"}),
    Invariant: frozenset({"description"}),
    InvariantSummary: frozenset({"description"}),
    RevisionRuleDraft: frozenset({"description"}),
    RevisionProposal: frozenset({"draft_policy_wording"}),
    RevisionConfirmation: frozenset({"draft_policy_wording"}),
    SessionRevisionProvenance: frozenset({"confirmed_at"}),
    RunManifest: frozenset({"started_at"}),
    BenchmarkManifest: frozenset({"sealed_at"}),
    ApplyRevisionRequest: frozenset({"confirmed_at"}),
    RunEvent: frozenset({"timestamp", "action_summary"}),
    RunView: frozenset({"events", "decision_at"}),
    RunRecord: frozenset({"events", "created_at", "expires_at", "decision_at"}),
    ArtifactSummary: frozenset({"title"}),
    FindingSummary: frozenset({"summary"}),
    CreateRunRequest: frozenset({"title"}),
}


def _payload_projection(payload: object, *, semantic: bool) -> object:
    active: set[int] = set()

    def project(value: object) -> object:
        if not isinstance(value, (BaseModel, Mapping, list, tuple, set, frozenset)):
            return normalize_for_hash(value)
        identity = id(value)
        if identity in active:
            raise ValueError("cyclic payload cannot be projected")
        active.add(identity)
        try:
            if isinstance(value, BaseModel):
                excluded = _COMPLETE_EXCLUSIONS.get(type(value), frozenset())
                if semantic:
                    excluded = excluded | _SEMANTIC_EXCLUSIONS.get(
                        type(value), frozenset()
                    )
                return normalize_for_hash(
                    {
                        key: project(child)
                        for key, child in dict(value).items()
                        if key not in excluded
                    }
                )
            if isinstance(value, Mapping):
                return normalize_for_hash(
                    {key: project(child) for key, child in value.items()}
                )
            values = [project(child) for child in value]
            if isinstance(value, (set, frozenset)):
                unique = {
                    json.dumps(
                        child, ensure_ascii=False, sort_keys=True, separators=(",", ":")
                    ): child
                    for child in values
                }
                return [unique[key] for key in sorted(unique)]
            return values
        finally:
            active.remove(identity)

    return project(payload)


def complete_payload_projection(payload: object) -> object:
    """Return canonical JSON values with only concrete self-digests excluded.

    This traverses models before normalizing so self-digests in nested suites and
    evaluation traces are excluded without dropping referenced integrity hashes.
    Plain mappings have no domain type and therefore receive no field exclusions.
    """
    return _payload_projection(payload, semantic=False)


def semantic_payload_projection(payload: object) -> object:
    """Project complete content without known display fields, timestamps/events.

    IDs, revisions, provenance references, source coordinates, quote hashes,
    inputs, predicates, effects, decisions and metrics remain significant. This
    is not the separate stretch prose-equivalence signature. Models must retain
    their concrete types; plain mapping keys never trigger domain exclusions.
    """
    return _payload_projection(payload, semantic=True)


def make_artifact_envelope(
    *,
    artifact_type: ArtifactType,
    payload: ArtifactPayload,
    parent_refs: Iterable[ArtifactRef] = (),
    run_manifest_id: str,
) -> ArtifactEnvelope:
    """Validate immutable domain content and attach its complete/semantic hashes.

    Parent references contribute sorted unique complete hashes to metadata, not
    payload digests. Their contents cannot be verified without parent objects.
    All models are revalidated by the public contracts, including constructed or
    copied instances that may have bypassed normal Pydantic validation.
    """
    parents = []
    for reference in parent_refs:
        if not isinstance(reference, ArtifactRef):
            raise TypeError("parent_refs must contain ArtifactRef values")
        parents.append(ArtifactRef.model_validate(reference).artifact_sha256)
    validated = ArtifactEnvelope(
        artifact_type=artifact_type,
        payload=payload,
        parent_hashes=tuple(sorted(set(parents))),
        run_manifest_id=run_manifest_id,
        artifact_sha256="0" * 64,
        semantic_sha256="0" * 64,
    )
    return ArtifactEnvelope.model_validate(
        validated.model_copy(
            update={
                "artifact_sha256": canonical_sha256(
                    complete_payload_projection(validated.payload)
                ),
                "semantic_sha256": canonical_sha256(
                    semantic_payload_projection(validated.payload)
                ),
            }
        )
    )


def validate_artifact_envelope(envelope: ArtifactEnvelope) -> ArtifactEnvelope:
    """Revalidate an envelope and recompute both payload digests; return its model.

    Reject malformed contracts, noncanonical parent ordering and digest mismatch.
    Metadata and parent contents are not authenticated by these payload hashes;
    validating the referenced parent objects is the caller's responsibility.
    """
    validated = ArtifactEnvelope.model_validate(envelope)
    if validated.parent_hashes != tuple(sorted(set(validated.parent_hashes))):
        raise ValueError("parent_hashes must be sorted and unique")
    if validated.artifact_sha256 != canonical_sha256(
        complete_payload_projection(validated.payload)
    ):
        raise ValueError("artifact_sha256 does not match complete payload")
    if validated.semantic_sha256 != canonical_sha256(
        semantic_payload_projection(validated.payload)
    ):
        raise ValueError("semantic_sha256 does not match semantic payload")
    return validated
