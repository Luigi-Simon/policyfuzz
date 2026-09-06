"""Deterministic aggregate metrics over authoritative evaluation evidence."""

from collections import Counter

from app.domain.models import (
    AssertionCounts,
    EffectStateCounts,
    MetricsReport,
    MetricsRequest,
)


def _percent(numerator: int, denominator: int) -> int | None:
    if denominator == 0:
        return None
    return (numerator * 100 + denominator // 2) // denominator


def compute_metrics(request: MetricsRequest) -> MetricsReport:
    """Count only hash-aligned deterministic results and non-candidate causes."""
    evaluation, findings = request.evaluation, request.findings
    if findings.inputs != evaluation.inputs:
        raise ValueError("HASH_MISMATCH: metric finding anchors")

    effect_counts = Counter(
        effect.status
        for result in evaluation.results
        for effect in result.trace.resolved_effects
    )
    assertion_counts = Counter(
        assertion.status
        for result in evaluation.results
        for assertion in result.assertion_results
    )
    assertion_total = sum(assertion_counts.values())
    scored_fingerprints = {
        finding.fingerprint_sha256
        for finding in findings.findings
        if finding.evidence_level != "candidate"
        and finding.finding_type != "potential_loophole"
    }

    return MetricsReport(
        inputs=evaluation.inputs,
        scenario_count=len(evaluation.results),
        effect_states=EffectStateCounts(
            VALUE=effect_counts["VALUE"],
            GAP=effect_counts["GAP"],
            NOT_APPLICABLE=effect_counts["NOT_APPLICABLE"],
            CONFLICT=effect_counts["CONFLICT"],
            INCONCLUSIVE=effect_counts["INCONCLUSIVE"],
            ERROR=effect_counts["ERROR"],
        ),
        assertions=AssertionCounts(
            passed=assertion_counts["PASS"],
            failed=assertion_counts["FAIL"],
            inconclusive=assertion_counts["INCONCLUSIVE"],
            error=assertion_counts["ERROR"],
        ),
        unique_finding_count=len(scored_fingerprints),
        coverage=evaluation.coverage,
        assertion_pass_percent=_percent(assertion_counts["PASS"], assertion_total),
    )
