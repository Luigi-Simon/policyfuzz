"""Exact, one-to-one scoring of deterministic findings against a benchmark."""

import hashlib

from app.domain.models import BenchmarkScore, Finding, ScoreBenchmarkRequest
from app.features.evaluation.engine import payload_hash


def _percent(numerator: int, denominator: int) -> int | None:
    if denominator == 0:
        return None
    return (numerator * 100 + denominator // 2) // denominator


def _finding_targets(finding: Finding) -> tuple[str, ...]:
    if finding.finding_type == "intent_breach":
        return (finding.invariant_id,) if finding.invariant_id is not None else ()
    if finding.finding_type == "regression":
        return (finding.assertion_id,) if finding.assertion_id is not None else ()
    return tuple(sorted(finding.rule_ids))


def _is_scored(finding: Finding) -> bool:
    return (
        finding.evidence_level != "candidate"
        and finding.finding_type != "potential_loophole"
    )


def _validate_evidence(request: ScoreBenchmarkRequest) -> None:
    manifest, findings, evaluation = (
        request.manifest,
        request.findings,
        request.evaluation,
    )
    if (
        findings.inputs != evaluation.inputs
        or manifest.policy_contract_sha256 != evaluation.inputs.contract_sha256
        or manifest.engine_version != evaluation.engine_version
    ):
        raise ValueError("HASH_MISMATCH: benchmark inputs")

    gold_ids = tuple(scenario.scenario_id for scenario in manifest.gold_scenarios)
    result_ids = tuple(result.scenario_id for result in evaluation.results)
    if len(gold_ids) != len(set(gold_ids)):
        raise ValueError("benchmark contains duplicate gold scenario IDs")
    if set(gold_ids) != set(result_ids):
        raise ValueError("HASH_MISMATCH: benchmark evaluation scenario set")
    results = {result.scenario_id: result for result in evaluation.results}
    for result in evaluation.results:
        if payload_hash(result.trace) != result.trace.trace_sha256:
            raise ValueError("HASH_MISMATCH: fabricated evaluation trace")

    defect_ids = [defect.defect_id for defect in manifest.defects]
    if len(defect_ids) != len(set(defect_ids)):
        raise ValueError("benchmark contains duplicate defect IDs")
    for defect in manifest.defects:
        if len(defect.target_ids) != len(set(defect.target_ids)):
            raise ValueError("benchmark defect contains duplicate target IDs")
        if len(defect.permitted_witness_ids) != len(set(defect.permitted_witness_ids)):
            raise ValueError("benchmark defect contains duplicate permitted witnesses")
        if not set(defect.permitted_witness_ids) <= set(gold_ids):
            raise ValueError("benchmark defect witness is outside the gold suite")
        if defect.expected_finding_fingerprint_sha256 is None:
            raise ValueError(
                "benchmark scoring requires an explicit expected finding fingerprint"
            )
        for span in defect.source_spans:
            if (
                hashlib.sha256(span.quote.encode("utf-8")).hexdigest()
                != span.quote_sha256
            ):
                raise ValueError("HASH_MISMATCH: benchmark source citation")

    finding_ids = [finding.finding_id for finding in findings.findings]
    fingerprints = [finding.fingerprint_sha256 for finding in findings.findings]
    if len(finding_ids) != len(set(finding_ids)):
        raise ValueError("finding report contains duplicate finding IDs")
    if len(fingerprints) != len(set(fingerprints)):
        raise ValueError("finding report contains duplicate root-cause fingerprints")
    for finding in findings.findings:
        if len(finding.scenario_ids) != len(set(finding.scenario_ids)) or len(
            finding.traces
        ) != len({trace.scenario_id for trace in finding.traces}):
            raise ValueError("finding contains duplicate witness")
        if set(finding.scenario_ids) != {trace.scenario_id for trace in finding.traces}:
            raise ValueError("finding witness and trace identities differ")
        for trace in finding.traces:
            result = results.get(trace.scenario_id)
            if result is None or result.trace.trace_sha256 != trace.trace_sha256:
                raise ValueError("HASH_MISMATCH: finding witness trace")
        for span in finding.citations:
            if (
                hashlib.sha256(span.quote.encode("utf-8")).hexdigest()
                != span.quote_sha256
            ):
                raise ValueError("HASH_MISMATCH: finding citation")


def _matches(defect, finding: Finding) -> bool:
    return (
        defect.finding_type == finding.finding_type
        and defect.dimension == finding.dimension
        and tuple(sorted(defect.target_ids)) == _finding_targets(finding)
        and defect.expected_finding_fingerprint_sha256 == finding.fingerprint_sha256
        and bool(set(defect.permitted_witness_ids) & set(finding.scenario_ids))
    )


def _maximum_matching(defects, findings: tuple[Finding, ...]) -> int:
    """Return maximum cardinality for the exact defect/finding bipartite graph."""
    matched_findings: dict[int, int] = {}

    def assign(defect_index: int, visited: set[int]) -> bool:
        for finding_index, finding in enumerate(findings):
            if finding_index in visited or not _matches(defects[defect_index], finding):
                continue
            visited.add(finding_index)
            prior = matched_findings.get(finding_index)
            if prior is None or assign(prior, visited):
                matched_findings[finding_index] = defect_index
                return True
        return False

    return sum(assign(index, set()) for index in range(len(defects)))


def score_benchmark(request: ScoreBenchmarkRequest) -> BenchmarkScore:
    """Score explicit root-cause fingerprints without text or model heuristics."""
    _validate_evidence(request)
    scored_findings = tuple(
        sorted(
            (finding for finding in request.findings.findings if _is_scored(finding)),
            key=lambda finding: (finding.fingerprint_sha256, finding.finding_id),
        )
    )
    defects = tuple(sorted(request.manifest.defects, key=lambda item: item.defect_id))
    true_positives = _maximum_matching(defects, scored_findings)
    false_positives = len(scored_findings) - true_positives
    false_negatives = len(defects) - true_positives
    precision_denominator = true_positives + false_positives
    recall_denominator = true_positives + false_negatives
    f1_denominator = 2 * true_positives + false_positives + false_negatives
    return BenchmarkScore(
        benchmark_id=request.manifest.benchmark_id,
        inputs=request.evaluation.inputs,
        true_positives=true_positives,
        false_positives=false_positives,
        false_negatives=false_negatives,
        precision_percent=_percent(true_positives, precision_denominator),
        recall_percent=_percent(true_positives, recall_denominator),
        f1_percent=_percent(2 * true_positives, f1_denominator),
    )
