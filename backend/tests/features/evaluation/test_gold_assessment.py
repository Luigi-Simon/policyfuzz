"""Public synthetic post-run assessment fixtures; never a private blind archive."""

import hashlib
import json
from datetime import UTC, datetime, timedelta

import pytest
from pydantic import ValidationError

from app.core.artifacts import make_artifact_envelope, semantic_payload_projection
from app.core.hashing import canonical_sha256
from app.domain.models import (
    AnalyzeFindingsRequest,
    Assertion,
    BenchmarkCorrectedSemantics,
    BenchmarkDefect,
    BenchmarkExpectedRule,
    BenchmarkManifest,
    BenchmarkScore,
    BenchmarkSourceLabel,
    BenchmarkSourceLabels,
    EvaluatePolicyRequest,
    GenerationConfig,
    InputHashes,
    PolicyDocument,
    PolicyPage,
    Predicate,
    RevisionRuleDraft,
    RunManifest,
    RunRecord,
    ScenarioSuite,
    SourceSpan,
)
from app.features.evaluation.benchmark_cli import main
from app.features.evaluation.engine import DeterministicEvaluationEngine, payload_hash
from app.features.evaluation.findings import DeterministicFindingAnalyzer
from app.features.evaluation.gold_assessment import current_engine_sha256


def _write(path, model):
    value = model.model_dump(mode="json") if hasattr(model, "model_dump") else model
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n")


def _bytes_hash(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


@pytest.fixture
def assessment_packet(
    tmp_path,
    request_factory,
    policy_factory,
    rule_factory,
    scenario_factory,
    contract,
    facts,
):
    source = "Synthetic meals eligible below SGD 50."
    sha = hashlib.sha256(source.encode()).hexdigest()
    span = SourceSpan(page=1, start=0, end=len(source), quote=source, quote_sha256=sha)
    document = PolicyDocument(
        document_id="source",
        title="Synthetic source",
        source_type="bundled_sample",
        pages=(PolicyPage(page=1, text=source, start=0, end=len(source)),),
        document_sha256=sha,
    )
    base = rule_factory(
        "r1", when=(Predicate(field="amount_minor", operator="lt", value=5000),)
    )
    base = base.model_copy(
        update={"provenance": base.provenance.model_copy(update={"span": span})}
    )
    gold_policy = policy_factory([base]).model_copy(update={"document_sha256": sha})
    captured = gold_policy.model_copy(
        update={
            "rules": (
                base.model_copy(
                    update={
                        "when": (
                            Predicate(field="amount_minor", operator="gte", value=5000),
                        )
                    }
                ),
            )
        }
    )
    gold_contract = contract.model_copy(
        update={"contract_id": "independent-gold-contract"}
    )
    gold_case = scenario_factory("sealed-gold-case")
    gold_case = gold_case.model_copy(
        update={
            "origins": frozenset({"gold"}),
            "assertions": (
                Assertion(
                    assertion_id="gold-eligibility",
                    target_kind="effect_value",
                    dimension="eligibility",
                    operator="eq",
                    expected_value="allow",
                    origin="gold",
                    gold_label_id="source-label",
                ),
            ),
        }
    )
    gold_suite = ScenarioSuite(
        suite_id="sealed-gold",
        content_sha256="0" * 64,
        seed=42,
        document_sha256=sha,
        policy_contract_sha256=payload_hash(gold_contract),
        rule_set_sha256=canonical_sha256(semantic_payload_projection(gold_policy)),
        engine_version="1.0.0",
        scenarios=(gold_case,),
    )
    gold_suite = gold_suite.model_copy(
        update={"content_sha256": payload_hash(gold_suite)}
    )
    gold_evaluation = DeterministicEvaluationEngine().evaluate(
        EvaluatePolicyRequest(
            policy=gold_policy,
            contract=gold_contract,
            suite=gold_suite,
            engine_version="1.0.0",
            inputs=InputHashes(
                policy_sha256=payload_hash(gold_policy),
                contract_sha256=payload_hash(gold_contract),
                suite_sha256=payload_hash(gold_suite),
                engine_sha256=current_engine_sha256(),
                run_manifest_sha256="d" * 64,
            ),
        )
    )
    defect = BenchmarkDefect(
        defect_id="authored-gap",
        finding_type="structural_gap",
        dimension="eligibility",
        target_ids=("r1",),
        severity="medium",
        source_spans=(span,),
        permitted_witness_ids=(gold_case.scenario_id,),
        expected_finding_fingerprint_sha256=canonical_sha256(
            {"type": "structural_gap", "dimension": "eligibility", "rule_ids": ("r1",)}
        ),
    )
    manifest = BenchmarkManifest(
        benchmark_id="synthetic-gold",
        document_sha256=sha,
        policy_contract_sha256=payload_hash(gold_contract),
        engine_version="1.0.0",
        sealed_at=datetime(2026, 9, 4, tzinfo=UTC),
        seal_sha256="e" * 64,
        defects=(defect,),
        gold_scenarios=(gold_case,),
        required_dimensions=gold_contract.required_dimensions,
    )
    source_labels = BenchmarkSourceLabels(
        document=document,
        labels=(
            BenchmarkSourceLabel(
                label_id="source-label", source_span=span, rule_ids=("r1",)
            ),
        ),
    )
    corrected = BenchmarkCorrectedSemantics(
        document_sha256=sha,
        baseline_policy_sha256=payload_hash(gold_policy),
        rules=(
            BenchmarkExpectedRule(
                rule_id="r1",
                revision=2,
                rule=RevisionRuleDraft(
                    description="Include boundary",
                    when=(Predicate(field="amount_minor", operator="lte", value=5000),),
                    effects=base.effects,
                ),
            ),
        ),
    )
    artifacts = {
        "source-labels.json": source_labels,
        "canonical-policy-ir.json": gold_policy,
        "confirmed-contract.json": gold_contract,
        "frozen-suite.json": gold_suite,
        "expected-effects.json": gold_evaluation,
        "defect-manifest.json": manifest,
        "corrected-semantics.json": corrected,
    }
    directory = tmp_path / "revealed"
    directory.mkdir()
    for name, value in artifacts.items():
        _write(directory / name, value)
    seal = {
        "schema_version": "1.0",
        "archive_sha256": "a" * 64,
        "source_policy_sha256": sha,
        "artifact_hashes": {
            name: payload_hash(value) for name, value in artifacts.items()
        },
        "defect_ids_sha256": canonical_sha256(["authored-gap"]),
        "rule_count": 1,
        "scenario_count": 1,
        "defect_count": 1,
        "created_at": "2026-09-04T00:00:00Z",
        "custodian_role": "Synthetic test custodian",
    }
    seal_path = tmp_path / "blind-schema-seal.json"
    _write(seal_path, seal)
    raw_path = tmp_path / "first-run.json"
    metadata_path = tmp_path / "first-run.json.metadata.json"

    def record_policy(policy=captured, confirmed=True):
        moment = datetime(2026, 9, 6, tzinfo=UTC)
        run_manifest = RunManifest(
            manifest_id="run-manifest",
            run_id="first-run",
            engine_version="1.0.0",
            engine_sha256=current_engine_sha256(),
            prompt_hashes=(),
            provider="synthetic",
            model_identifier="scripted",
            generation_config=GenerationConfig(),
            random_seed=42,
            started_at=moment,
            mode="live",
        )
        case = scenario_factory(
            "generated-first-case",
            facts=facts.model_copy(update={"amount_minor": 1000}),
            assertions=(contract.invariants[0].assertion,),
        )
        request = request_factory(policy, [case])
        request = request.model_copy(
            update={
                "inputs": request.inputs.model_copy(
                    update={
                        "engine_sha256": run_manifest.engine_sha256,
                        "run_manifest_sha256": payload_hash(run_manifest),
                    }
                )
            }
        )
        evaluation = DeterministicEvaluationEngine().evaluate(request)
        findings = DeterministicFindingAnalyzer().analyze(
            AnalyzeFindingsRequest(
                policy=policy,
                contract=contract,
                suite=request.suite,
                evaluation=evaluation,
            )
        )
        pieces = [
            ("policy_document", document),
            ("policy_ir", policy.model_copy(update={"review_status": "provisional"})),
        ]
        if confirmed:
            pieces.append(("policy_ir", policy))
        pieces += [
            ("policy_contract", contract),
            ("scenario_suite", request.suite),
            ("evaluation_report", evaluation),
            ("finding_report", findings),
        ]
        record = RunRecord(
            run_id="first-run",
            stage="complete",
            manifest=run_manifest,
            created_at=moment,
            expires_at=moment + timedelta(minutes=30),
            artifacts=tuple(
                make_artifact_envelope(
                    artifact_type=kind,
                    payload=value,
                    run_manifest_id=run_manifest.manifest_id,
                )
                for kind, value in pieces
            ),
        )
        _write(raw_path, record)
        metadata = {
            "schema_version": "1.0",
            "status": "recorded",
            "error_code": None,
            "run_id": record.run_id,
            "result_bytes_sha256": _bytes_hash(raw_path),
            "result_sha256": payload_hash(record),
            "candidate": {
                "source_policy_sha256": sha,
                "schema_archive_sha256": seal["archive_sha256"],
            },
            "input_bytes_sha256": {
                "submission/evidence/blind-schema-seal.json": _bytes_hash(seal_path)
            },
            "runtime": {
                "engine_version": "1.0.0",
                "engine_sha256": run_manifest.engine_sha256,
            },
            "commit": "1" * 40,
        }
        _write(metadata_path, metadata)
        return record

    record = record_policy()
    output = tmp_path / "postrun-gold"
    args = [
        "assess-gold",
        "--run-result",
        str(raw_path),
        "--run-metadata",
        str(metadata_path),
        "--benchmark-dir",
        str(directory),
        "--schema-seal",
        str(seal_path),
        "--output",
        str(output),
    ]
    return locals()


def test_assessment_keeps_raw_untouched_and_uses_captured_policy(assessment_packet):
    p = assessment_packet
    before = p["raw_path"].read_bytes()
    assert main(p["args"]) == 0
    assert p["raw_path"].read_bytes() == before
    score = json.loads((p["output"] / "score.json").read_text())
    proof = json.loads((p["output"] / "provenance.json").read_text())
    assert score["assessment_kind"] == "post_run_gold_assessment"
    assert score["headline_gate_eligible"] is False
    assert score["score"]["false_negatives"] == 1
    assert score["score"]["true_positives"] == 0
    assert proof["captured_policy_sha256"] == payload_hash(p["captured"])
    assert proof["captured_policy_sha256"] != proof["canonical_gold_policy_sha256"]
    assert proof["original_contract_sha256"] != proof["gold_contract_sha256"]
    assert proof["original_suite_sha256"] != proof["derived_suite_sha256"]
    assert proof["evaluation"]["inputs"]["policy_sha256"] == payload_hash(p["captured"])
    assert proof["derived_suite"]["scenarios"] == [
        p["gold_case"].model_dump(mode="json")
    ]
    with pytest.raises(ValidationError):
        BenchmarkScore.model_validate_json(json.dumps(score))


def test_assessment_keeps_unmatched_roots_as_false_counts(assessment_packet):
    p = assessment_packet
    captured = p["gold_policy"].model_copy(
        update={
            "rules": (p["base"].model_copy(update={"rule_id": "captured-other-id"}),)
        }
    )
    p["record_policy"](captured)
    assert main(p["args"]) == 0
    score = json.loads((p["output"] / "score.json").read_text())["score"]
    assert (
        score["true_positives"],
        score["false_positives"],
        score["false_negatives"],
    ) == (0, 1, 1)


@pytest.mark.parametrize("target", ["seal", "artifact", "raw", "engine"])
def test_assessment_rejects_tampered_bound_inputs(assessment_packet, target):
    p = assessment_packet
    if target == "seal":
        seal = json.loads(p["seal_path"].read_text())
        seal["archive_sha256"] = "f" * 64
        _write(p["seal_path"], seal)
    elif target == "artifact":
        model = p["gold_policy"].model_copy(update={"policy_id": "tampered"})
        _write(p["directory"] / "canonical-policy-ir.json", model)
    elif target == "raw":
        p["raw_path"].write_text(p["raw_path"].read_text() + "\n")
    else:
        metadata = json.loads(p["metadata_path"].read_text())
        metadata["runtime"]["engine_sha256"] = "f" * 64
        _write(p["metadata_path"], metadata)
    assert main(p["args"]) == 1
    assert not p["output"].exists()


def test_assessment_rejects_missing_confirmed_baseline(assessment_packet):
    p = assessment_packet
    p["record_policy"](confirmed=False)
    assert main(p["args"]) == 1
    assert not p["output"].exists()


def test_assessment_publication_is_exclusive(assessment_packet):
    p = assessment_packet
    assert main(p["args"]) == 0
    before = {f.name: f.read_bytes() for f in p["output"].iterdir()}
    assert main(p["args"]) == 1
    assert {f.name: f.read_bytes() for f in p["output"].iterdir()} == before


def test_assessment_failed_publication_has_no_partial_pair(
    assessment_packet, monkeypatch
):
    from app.features.evaluation import gold_assessment

    p = assessment_packet

    def fail(*args):
        raise OSError("synthetic publish failure")

    monkeypatch.setattr(gold_assessment, "_rename_no_replace", fail)
    assert main(p["args"]) == 1
    assert not p["output"].exists()
    assert not tuple(p["tmp_path"].glob(".postrun-gold.*"))
