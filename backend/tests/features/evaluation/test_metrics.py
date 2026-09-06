import pytest

from app.domain.models import Finding, FindingReport, MetricsRequest, TraceRef
from app.features.evaluation.engine import DeterministicEvaluationEngine
from app.features.evaluation.metrics import compute_metrics


def _finding(
    report, *, finding_id, fingerprint, evidence_level="mechanically_reproduced"
):
    result = report.results[0]
    finding_type = (
        "potential_loophole" if evidence_level == "candidate" else "structural_gap"
    )
    return Finding(
        finding_id=finding_id,
        fingerprint_sha256=fingerprint,
        finding_type=finding_type,
        evidence_level=evidence_level,
        scenario_ids=(result.scenario_id,),
        rule_ids=("r1",),
        dimension="eligibility",
        traces=(
            TraceRef(
                scenario_id=result.scenario_id,
                trace_sha256=result.trace.trace_sha256,
            ),
        ),
    )


def test_compute_metrics_counts_authoritative_results_and_unique_scored_causes(
    request_factory,
):
    evaluation = DeterministicEvaluationEngine().evaluate(request_factory())
    findings = FindingReport(
        report_id="findings",
        inputs=evaluation.inputs,
        findings=(
            _finding(evaluation, finding_id="f1", fingerprint="1" * 64),
            _finding(evaluation, finding_id="f2", fingerprint="1" * 64),
            _finding(
                evaluation,
                finding_id="candidate",
                fingerprint="2" * 64,
                evidence_level="candidate",
            ),
        ),
    )

    metrics = compute_metrics(MetricsRequest(evaluation=evaluation, findings=findings))

    assert metrics.inputs == evaluation.inputs
    assert metrics.scenario_count == 1
    assert metrics.effect_states.VALUE == 1
    assert metrics.effect_states.NOT_APPLICABLE == 4
    assert metrics.assertions.passed == 1
    assert metrics.assertion_pass_percent == 100
    assert metrics.unique_finding_count == 1
    assert metrics.coverage == evaluation.coverage


def test_compute_metrics_uses_none_for_zero_assertion_denominator(
    request_factory, scenario_factory, facts
):
    unasserted = scenario_factory(
        facts=facts.model_copy(update={"expense_category": "airfare"})
    )
    evaluation = DeterministicEvaluationEngine().evaluate(
        request_factory(scenarios=[unasserted])
    )
    findings = FindingReport(
        report_id="findings", inputs=evaluation.inputs, findings=()
    )

    metrics = compute_metrics(MetricsRequest(evaluation=evaluation, findings=findings))

    assert metrics.assertions.passed == 0
    assert metrics.assertion_pass_percent is None


def test_compute_metrics_rejects_findings_from_different_inputs(request_factory):
    evaluation = DeterministicEvaluationEngine().evaluate(request_factory())
    findings = FindingReport(
        report_id="findings",
        inputs=evaluation.inputs.model_copy(update={"engine_sha256": "f" * 64}),
        findings=(),
    )

    with pytest.raises(ValueError, match="HASH_MISMATCH"):
        compute_metrics(MetricsRequest(evaluation=evaluation, findings=findings))
