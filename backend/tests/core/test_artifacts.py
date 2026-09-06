"""Artifact integrity and explicit complete/semantic projection behavior."""

from datetime import UTC, datetime, timedelta

import pytest
from backend.tests.domain.factories import (
    HASH,
    make_inputs,
    make_policy,
    make_policy_contract,
    make_rule,
    make_scenario_suite,
    make_span,
    make_trace,
)
from pydantic import BaseModel, ValidationError

from app.core.artifacts import (
    complete_payload_projection,
    make_artifact_envelope,
    semantic_payload_projection,
    validate_artifact_envelope,
)
from app.core.hashing import canonical_sha256
from app.domain.models import (
    AddOverrideOperation,
    ArtifactEnvelope,
    ArtifactRef,
    CoverageSnapshot,
    Effect,
    EvaluationReport,
    GenerationConfig,
    PolicyDocument,
    PolicyIR,
    PolicyPage,
    RevisionProposal,
    RunEvent,
    RunManifest,
    RunView,
    ScenarioEvaluation,
    SessionRevisionProvenance,
    TextRuleProvenance,
    TraceRef,
)

OTHER_HASH = "b" * 64
NOW = datetime(2026, 9, 4, tzinfo=UTC)


def envelope(payload=None, artifact_type="policy_ir", **changes):
    return make_artifact_envelope(
        artifact_type=artifact_type,
        payload=make_policy() if payload is None else payload,
        **({"run_manifest_id": "manifest-1"} | changes),
    )


def report(**changes):
    values = {
        "report_id": "report-1",
        "inputs": make_inputs(),
        "engine_version": "1.0",
        "results": (
            ScenarioEvaluation(
                scenario_id="scenario-0", trace=make_trace(), verdict="UNSCORED"
            ),
        ),
        "coverage": CoverageSnapshot(),
    }
    return EvaluationReport(**(values | changes))


def manifest(**changes):
    values = {
        "manifest_id": "manifest-1",
        "run_id": "run-1",
        "engine_version": "1.0",
        "engine_sha256": HASH,
        "prompt_hashes": (),
        "provider": "fake",
        "model_identifier": "fake",
        "generation_config": GenerationConfig(),
        "random_seed": 42,
        "started_at": NOW,
        "mode": "cached",
    }
    return RunManifest(**(values | changes))


def test_builder_hashes_payload_and_sorts_unique_parent_references():
    parents = tuple(
        ArtifactRef(
            artifact_type="policy_document", artifact_sha256=h, semantic_sha256=HASH
        )
        for h in (OTHER_HASH, HASH, OTHER_HASH)
    )
    result = envelope(parent_refs=parents)
    assert result.parent_hashes == (HASH, OTHER_HASH)
    assert result.artifact_sha256 == canonical_sha256(make_policy())
    assert result.artifact_sha256 != result.semantic_sha256
    changed_metadata = envelope(run_manifest_id="different", parent_refs=())
    assert changed_metadata.artifact_sha256 == result.artifact_sha256
    assert changed_metadata.semantic_sha256 == result.semantic_sha256
    with pytest.raises(ValidationError):
        result.payload.rules[0].description = "mutated"


@pytest.mark.parametrize(
    "field,value", [("description", "New display wording"), ("confidence_percent", 10)]
)
def test_policy_presentation_changes_only_complete_hash(field, value):
    baseline = envelope()
    changed = envelope(make_policy(rules=(make_rule(**{field: value}),)))
    assert baseline.artifact_sha256 != changed.artifact_sha256
    assert baseline.semantic_sha256 == changed.semantic_sha256


@pytest.mark.parametrize(
    "changes",
    [
        {"effects": (Effect(dimension="claim_cap_minor", value=4999),)},
        {"revision": 1},
        {"rule_id": "new-id"},
        {
            "provenance": TextRuleProvenance(
                citation_id="other-citation", span=make_span()
            )
        },
        {
            "provenance": TextRuleProvenance(
                citation_id="citation-meal",
                span=make_span().model_copy(update={"quote_sha256": OTHER_HASH}),
            )
        },
    ],
)
def test_policy_decisions_revisions_ids_and_provenance_change_semantic_hash(changes):
    assert (
        envelope().semantic_sha256
        != envelope(make_policy(rules=(make_rule(**changes),))).semantic_sha256
    )


def test_session_timestamp_is_display_only_but_provenance_anchor_is_not():
    provenance = SessionRevisionProvenance(
        proposal_id="proposal-1",
        operation_index=0,
        confirmed_at=NOW,
        baseline_citation_ids=("citation-meal",),
    )
    baseline = make_policy(
        kind="structured_revision", rules=(make_rule(provenance=provenance),)
    )
    later = make_policy(
        kind="structured_revision",
        rules=(
            make_rule(
                provenance=provenance.model_copy(
                    update={"confirmed_at": NOW + timedelta(hours=1)}
                )
            ),
        ),
    )
    other = make_policy(
        kind="structured_revision",
        rules=(
            make_rule(
                provenance=provenance.model_copy(update={"proposal_id": "proposal-2"})
            ),
        ),
    )
    assert envelope(baseline).artifact_sha256 != envelope(later).artifact_sha256
    assert envelope(baseline).semantic_sha256 == envelope(later).semantic_sha256
    assert envelope(baseline).semantic_sha256 != envelope(other).semantic_sha256


def test_manifest_time_is_excluded_but_generation_config_is_semantic():
    baseline = envelope(manifest(), "run_manifest")
    later = envelope(manifest(started_at=NOW + timedelta(seconds=1)), "run_manifest")
    changed = envelope(manifest(random_seed=43), "run_manifest")
    assert baseline.artifact_sha256 != later.artifact_sha256
    assert baseline.semantic_sha256 == later.semantic_sha256
    assert baseline.semantic_sha256 != changed.semantic_sha256


def test_document_title_is_display_only_and_raw_source_hash_remains_an_anchor():
    document = PolicyDocument(
        document_id="document-1",
        title="Synthetic",
        source_type="bundled_sample",
        pages=(PolicyPage(page=1, text="Meals capped", start=0, end=12),),
        document_sha256=HASH,
    )
    baseline = envelope(document, "policy_document")
    title = envelope(
        document.model_copy(update={"title": "Display"}), "policy_document"
    )
    source = envelope(
        document.model_copy(update={"document_sha256": OTHER_HASH}), "policy_document"
    )
    assert baseline.artifact_sha256 != title.artifact_sha256
    assert baseline.semantic_sha256 == title.semantic_sha256
    assert baseline.semantic_sha256 != source.semantic_sha256


def test_actual_suite_and_nested_trace_self_digests_are_excluded():
    baseline = envelope(make_scenario_suite(), "scenario_suite")
    changed = envelope(make_scenario_suite(content_sha256=OTHER_HASH), "scenario_suite")
    assert (baseline.artifact_sha256, baseline.semantic_sha256) == (
        changed.artifact_sha256,
        changed.semantic_sha256,
    )
    first_report = report()
    changed_result = first_report.results[0].model_copy(
        update={"trace": make_trace(trace_sha256=OTHER_HASH)}
    )
    second_report = report(results=(changed_result,))
    assert (
        envelope(first_report, "evaluation_report").artifact_sha256
        == envelope(second_report, "evaluation_report").artifact_sha256
    )
    assert (
        "trace_sha256"
        not in complete_payload_projection(first_report)["results"][0]["trace"]
    )


@pytest.mark.parametrize(
    "projection", [complete_payload_projection, semantic_payload_projection]
)
def test_reference_and_input_hashes_are_preserved(projection):
    ref = ArtifactRef(
        artifact_type="policy_ir", artifact_sha256=HASH, semantic_sha256=OTHER_HASH
    )
    assert projection(ref)["artifact_sha256"] == HASH
    assert projection(ref)["semantic_sha256"] == OTHER_HASH
    assert (
        projection(TraceRef(scenario_id="s1", trace_sha256=HASH))["trace_sha256"]
        == HASH
    )
    assert projection(make_span())["quote_sha256"] == HASH
    for field in (
        "policy_sha256",
        "contract_sha256",
        "suite_sha256",
        "engine_sha256",
        "run_manifest_sha256",
    ):
        assert canonical_sha256(projection(report())) != canonical_sha256(
            projection(report(inputs=make_inputs(**{field: OTHER_HASH})))
        )


def test_projection_exclusions_are_type_scoped_and_do_not_delete_similarly_named_data():
    data = {
        "title": "important",
        "description": "domain",
        "confidence_percent": 42,
        "events": [1],
        "timestamp": "anchor",
        "trace_sha256": HASH,
        "content_sha256": HASH,
        "artifact_sha256": HASH,
        "semantic_sha256": HASH,
    }

    class FutureDomain(BaseModel):
        description: str

    assert complete_payload_projection(data) == data
    assert semantic_payload_projection(data) == data
    assert semantic_payload_projection(FutureDomain(description="meaningful")) == {
        "description": "meaningful"
    }


def test_run_events_and_decision_timestamps_are_excluded_only_semantically():
    baseline = RunView(run_id="run-1", stage="queued", mode="cached")
    changed = baseline.model_copy(
        update={
            "events": (
                RunEvent(timestamp=NOW, stage="queued", action_summary="Queued"),
            ),
            "decision_at": NOW,
        }
    )
    assert canonical_sha256(complete_payload_projection(baseline)) != canonical_sha256(
        complete_payload_projection(changed)
    )
    assert semantic_payload_projection(baseline) == semantic_payload_projection(changed)


def test_draft_revision_wording_is_excluded_but_operation_target_remains():
    operation = AddOverrideOperation(
        rule_id="rule-meal",
        dimension="claim_cap_minor",
        target_rule_id="rule-general",
        finding_ids=("finding-gap",),
    )
    proposal = RevisionProposal(
        proposal_id="proposal-1",
        document_sha256=HASH,
        rule_set_sha256=HASH,
        policy_contract_sha256=HASH,
        suite_sha256=HASH,
        accepted_finding_ids=("finding-gap",),
        operations=(operation,),
        draft_policy_wording="Draft",
    )
    display = proposal.model_copy(update={"draft_policy_wording": "Other draft"})
    semantic = proposal.model_copy(
        update={
            "operations": (
                operation.model_copy(update={"target_rule_id": "rule-other"}),
            )
        }
    )
    assert (
        envelope(proposal, "revision_proposal").semantic_sha256
        == envelope(display, "revision_proposal").semantic_sha256
    )
    assert (
        envelope(proposal, "revision_proposal").artifact_sha256
        != envelope(display, "revision_proposal").artifact_sha256
    )
    assert (
        envelope(proposal, "revision_proposal").semantic_sha256
        != envelope(semantic, "revision_proposal").semantic_sha256
    )


@pytest.mark.parametrize(
    "kind,payload",
    [
        ("policy_ir", make_policy()),
        ("policy_contract", make_policy_contract()),
        ("scenario_suite", make_scenario_suite()),
        ("run_manifest", manifest()),
    ],
)
def test_model_json_roundtrip_validates_same_payload_digests(kind, payload):
    original = envelope(payload, kind)
    loaded = ArtifactEnvelope.model_validate_json(original.model_dump_json())
    assert validate_artifact_envelope(loaded) == original


@pytest.mark.parametrize("field", ["artifact_sha256", "semantic_sha256"])
def test_validation_rejects_forged_digest(field):
    forged = envelope().model_copy(update={field: HASH})
    with pytest.raises(ValueError, match=field):
        validate_artifact_envelope(forged)


def test_validation_rejects_changed_payload_and_mismatched_type():
    baseline = envelope()
    with pytest.raises(ValueError, match="artifact_sha256"):
        validate_artifact_envelope(
            baseline.model_copy(update={"payload": make_policy(policy_id="tampered")})
        )
    with pytest.raises(ValidationError):
        validate_artifact_envelope(
            baseline.model_copy(update={"artifact_type": "policy_document"})
        )


@pytest.mark.parametrize(
    "changes",
    [
        {"artifact_type": "unknown"},
        {"run_manifest_id": ""},
        {"payload": {"arbitrary": "data"}},
        {"artifact_type": "policy_document"},
    ],
)
def test_builder_rejects_malformed_contract_inputs(changes):
    with pytest.raises(ValidationError):
        make_artifact_envelope(
            **(
                {
                    "artifact_type": "policy_ir",
                    "payload": make_policy(),
                    "run_manifest_id": "manifest-1",
                }
                | changes
            )
        )


def test_builder_revalidates_forged_nested_models_and_parent_references():
    forged_rule = make_rule().model_copy(update={"confidence_percent": 1.5})
    forged_policy = PolicyIR.model_construct(
        **(make_policy().model_dump() | {"rules": (forged_rule,)})
    )
    with pytest.raises((ValidationError, TypeError)):
        envelope(forged_policy)
    forged_ref = ArtifactRef.model_construct(
        artifact_type="policy_ir", artifact_sha256="bad", semantic_sha256=HASH
    )
    with pytest.raises(ValidationError):
        envelope(parent_refs=(forged_ref,))
    with pytest.raises(TypeError):
        envelope(parent_refs=(HASH,))


def test_validation_rejects_noncanonical_parent_hash_order_or_duplicates():
    for hashes in ((OTHER_HASH, HASH), (HASH, HASH)):
        with pytest.raises(ValueError, match="parent_hashes"):
            validate_artifact_envelope(
                envelope().model_copy(update={"parent_hashes": hashes})
            )
