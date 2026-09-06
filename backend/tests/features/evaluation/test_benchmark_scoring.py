import hashlib
import json
from datetime import UTC, datetime

import pytest

from app.domain.models import (
    AnalyzeFindingsRequest,
    BenchmarkDefect,
    BenchmarkManifest,
    Finding,
    FindingReport,
    Predicate,
    ScoreBenchmarkRequest,
)
from app.features.evaluation.benchmark import score_benchmark
from app.features.evaluation.benchmark_cli import main
from app.features.evaluation.engine import DeterministicEvaluationEngine
from app.features.evaluation.findings import (
    DeterministicFindingAnalyzer,
    finding_fingerprint,
)


def _benchmark_case(request_factory, policy_factory, rule_factory):
    rule = rule_factory(
        when=(Predicate(field="amount_minor", operator="lt", value=1000),)
    )
    span = rule.provenance.span.model_copy(
        update={
            "quote_sha256": hashlib.sha256(
                rule.provenance.span.quote.encode("utf-8")
            ).hexdigest()
        }
    )
    rule = rule.model_copy(
        update={"provenance": rule.provenance.model_copy(update={"span": span})}
    )
    policy = policy_factory([rule])
    request = request_factory(policy)
    evaluation = DeterministicEvaluationEngine().evaluate(request)
    analyzed = DeterministicFindingAnalyzer().analyze(
        AnalyzeFindingsRequest(
            policy=policy,
            contract=request.contract,
            suite=request.suite,
            evaluation=evaluation,
        )
    )
    finding = next(
        item for item in analyzed.findings if item.finding_type == "structural_gap"
    )
    scenario = request.suite.scenarios[0].model_copy(
        update={"origins": frozenset({"gold"})}
    )
    defect = BenchmarkDefect(
        defect_id="defect-gap",
        finding_type=finding.finding_type,
        dimension=finding.dimension,
        target_ids=finding.rule_ids,
        severity="medium",
        semantic_signature_sha256="3" * 64,
        permitted_witness_ids=finding.scenario_ids,
        expected_finding_fingerprint_sha256=finding.fingerprint_sha256,
    )
    manifest = BenchmarkManifest(
        benchmark_id="synthetic-benchmark",
        document_sha256=policy.document_sha256,
        policy_contract_sha256=evaluation.inputs.contract_sha256,
        engine_version=evaluation.engine_version,
        sealed_at=datetime(2026, 9, 6, tzinfo=UTC),
        seal_sha256="4" * 64,
        defects=(defect,),
        gold_scenarios=(scenario,),
        required_dimensions=request.contract.required_dimensions,
    )
    return manifest, evaluation, finding


def test_score_benchmark_matches_once_and_counts_unmatched_scored_findings(
    request_factory, policy_factory, rule_factory
):
    manifest, evaluation, finding = _benchmark_case(
        request_factory, policy_factory, rule_factory
    )
    extra = Finding(
        finding_id="extra-finding",
        fingerprint_sha256=finding_fingerprint(
            "structural_gap", "eligibility", rule_ids=("other-rule",)
        ),
        finding_type="structural_gap",
        evidence_level="mechanically_reproduced",
        scenario_ids=finding.scenario_ids,
        rule_ids=("other-rule",),
        dimension="eligibility",
        traces=finding.traces,
    )
    findings = FindingReport(
        report_id="scored-findings",
        inputs=evaluation.inputs,
        findings=(finding, extra),
    )

    score = score_benchmark(
        ScoreBenchmarkRequest(
            manifest=manifest, findings=findings, evaluation=evaluation
        )
    )

    assert (score.true_positives, score.false_positives, score.false_negatives) == (
        1,
        1,
        0,
    )
    assert score.precision_percent == 50
    assert score.recall_percent == 100
    assert score.f1_percent == 67


def test_score_benchmark_uses_maximum_one_to_one_matching(
    request_factory, policy_factory, rule_factory
):
    manifest, evaluation, finding = _benchmark_case(
        request_factory, policy_factory, rule_factory
    )
    duplicate_root = manifest.defects[0].model_copy(update={"defect_id": "defect-2"})
    manifest = manifest.model_copy(
        update={"defects": (*manifest.defects, duplicate_root)}
    )
    findings = FindingReport(
        report_id="findings", inputs=evaluation.inputs, findings=(finding,)
    )

    score = score_benchmark(
        ScoreBenchmarkRequest(
            manifest=manifest, findings=findings, evaluation=evaluation
        )
    )

    assert (score.true_positives, score.false_positives, score.false_negatives) == (
        1,
        0,
        1,
    )


def test_score_benchmark_rejects_duplicate_witnesses(
    request_factory, policy_factory, rule_factory
):
    manifest, evaluation, finding = _benchmark_case(
        request_factory, policy_factory, rule_factory
    )
    duplicated = finding.model_copy(
        update={
            "scenario_ids": (*finding.scenario_ids, *finding.scenario_ids),
            "traces": (*finding.traces, *finding.traces),
        }
    )
    findings = FindingReport(
        report_id="findings", inputs=evaluation.inputs, findings=(duplicated,)
    )

    with pytest.raises(ValueError, match="duplicate witness"):
        score_benchmark(
            ScoreBenchmarkRequest(
                manifest=manifest, findings=findings, evaluation=evaluation
            )
        )


def test_score_benchmark_rejects_anchor_mismatch(
    request_factory, policy_factory, rule_factory
):
    manifest, evaluation, finding = _benchmark_case(
        request_factory, policy_factory, rule_factory
    )
    findings = FindingReport(
        report_id="findings",
        inputs=evaluation.inputs.model_copy(update={"engine_sha256": "f" * 64}),
        findings=(finding,),
    )

    with pytest.raises(ValueError, match="HASH_MISMATCH"):
        score_benchmark(
            ScoreBenchmarkRequest(
                manifest=manifest, findings=findings, evaluation=evaluation
            )
        )


def test_score_benchmark_rejects_semantic_only_manifest_as_ambiguous(
    request_factory, policy_factory, rule_factory
):
    manifest, evaluation, finding = _benchmark_case(
        request_factory, policy_factory, rule_factory
    )
    ambiguous = manifest.defects[0].model_copy(
        update={"expected_finding_fingerprint_sha256": None}
    )
    manifest = manifest.model_copy(update={"defects": (ambiguous,)})
    findings = FindingReport(
        report_id="findings", inputs=evaluation.inputs, findings=(finding,)
    )

    with pytest.raises(ValueError, match="explicit expected finding fingerprint"):
        score_benchmark(
            ScoreBenchmarkRequest(
                manifest=manifest, findings=findings, evaluation=evaluation
            )
        )


def test_benchmark_cli_writes_typed_score_once(
    tmp_path, request_factory, policy_factory, rule_factory
):
    manifest, evaluation, finding = _benchmark_case(
        request_factory, policy_factory, rule_factory
    )
    findings = FindingReport(
        report_id="findings", inputs=evaluation.inputs, findings=(finding,)
    )
    manifest_path = tmp_path / "manifest.json"
    result_path = tmp_path / "run-result.json"
    output_path = tmp_path / "score.json"
    manifest_path.write_text(manifest.model_dump_json(indent=2), encoding="utf-8")
    result_path.write_text(
        json.dumps(
            {
                "evaluation": evaluation.model_dump(mode="json"),
                "findings": findings.model_dump(mode="json"),
            }
        ),
        encoding="utf-8",
    )

    assert (
        main(
            [
                "score",
                "--manifest",
                str(manifest_path),
                "--run-result",
                str(result_path),
                "--output",
                str(output_path),
            ]
        )
        == 0
    )
    written = json.loads(output_path.read_text(encoding="utf-8"))
    assert written["benchmark_id"] == manifest.benchmark_id
    assert written["true_positives"] == 1

    original = output_path.read_bytes()
    assert (
        main(
            [
                "score",
                "--manifest",
                str(manifest_path),
                "--run-result",
                str(result_path),
                "--output",
                str(output_path),
            ]
        )
        == 1
    )
    assert output_path.read_bytes() == original


@pytest.fixture
async def concrete_record_and_manifest():
    from pathlib import Path

    from scripts.demo_support import run_demo

    record, _ = await run_demo()
    manifest = BenchmarkManifest.model_validate_json(
        (
            Path(__file__).resolve().parents[4]
            / "samples/benchmarks/development/defect-manifest.json"
        ).read_text()
    )
    return record, manifest


@pytest.mark.asyncio
async def test_record_cli_selects_confirmed_baseline_and_original_findings(
    concrete_record_and_manifest,
):
    from app.features.evaluation.benchmark_cli import _select_record_evidence

    record, manifest = concrete_record_and_manifest
    baselines = [
        a
        for a in record.artifacts
        if a.artifact_type == "policy_ir" and a.payload.kind == "compiled_baseline"
    ]
    assert {a.payload.review_status for a in baselines} == {
        "provisional",
        "session_confirmed",
    }
    confirmed = next(
        a for a in baselines if a.payload.review_status == "session_confirmed"
    )
    evaluation, selected = _select_record_evidence(
        record.model_dump(mode="json"), manifest
    )
    assert evaluation.inputs.policy_sha256 == confirmed.artifact_sha256
    reports = [
        a.payload
        for a in record.artifacts
        if a.artifact_type == "finding_report" and a.payload.inputs == evaluation.inputs
    ]
    assert len(reports) == 2
    assert selected == reports[0]
    assert all(f.review_status == "pending" for f in selected.findings)
    assert any(f.review_status == "accepted" for f in reports[1].findings)


@pytest.mark.asyncio
async def test_record_cli_rejects_conflicting_confirmed_baselines(
    concrete_record_and_manifest,
):
    from app.core.artifacts import make_artifact_envelope
    from app.features.evaluation.benchmark_cli import _select_record_evidence

    record, manifest = concrete_record_and_manifest
    baseline = next(
        a.payload
        for a in record.artifacts
        if a.artifact_type == "policy_ir"
        and a.payload.kind == "compiled_baseline"
        and a.payload.review_status == "session_confirmed"
    )
    conflicting = make_artifact_envelope(
        artifact_type="policy_ir",
        payload=baseline.model_copy(
            update={"policy_id": "conflicting-confirmed-baseline"}
        ),
        run_manifest_id=record.manifest.manifest_id,
    )
    record = record.model_copy(update={"artifacts": (*record.artifacts, conflicting)})
    with pytest.raises(ValueError, match="confirmed baseline"):
        _select_record_evidence(record.model_dump(mode="json"), manifest)
