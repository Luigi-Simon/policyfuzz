"""Group reproducible witnesses by deterministic root cause."""

from dataclasses import dataclass

from app.core.hashing import canonical_sha256
from app.domain.models import AnalyzeFindingsRequest, Finding, FindingReport, TraceRef
from app.features.evaluation.engine import payload_hash, scenario_assertions


def finding_fingerprint(
    finding_type,
    dimension,
    *,
    rule_ids=(),
    invariant_id=None,
    assertion_id=None,
    source_span_sha256=None,
    scenario_fact_sha256s=(),
):
    payload = {"type": finding_type, "dimension": dimension}
    if finding_type in ("structural_gap", "conflict"):
        payload["rule_ids"] = tuple(sorted(set(rule_ids)))
    elif finding_type == "intent_breach":
        payload["invariant_id"] = invariant_id
    elif finding_type == "unsupported_clause":
        payload["source_span_sha256"] = source_span_sha256
    elif finding_type == "regression":
        payload["assertion_id"] = assertion_id
    else:
        payload.update(
            rule_ids=tuple(sorted(set(rule_ids))),
            invariant_id=invariant_id,
            scenario_fact_sha256s=tuple(sorted(set(scenario_fact_sha256s))),
        )
    return canonical_sha256(payload)


@dataclass(frozen=True)
class DeterministicFindingAnalyzer:
    def analyze(self, request: AnalyzeFindingsRequest) -> FindingReport:
        if (
            request.evaluation.inputs.policy_sha256 != payload_hash(request.policy)
            or request.evaluation.inputs.contract_sha256
            != payload_hash(request.contract)
            or request.evaluation.inputs.suite_sha256 != payload_hash(request.suite)
        ):
            raise ValueError("HASH_MISMATCH: finding input anchors")
        scenarios = {s.scenario_id: s for s in request.suite.scenarios}
        if set(scenarios) != {r.scenario_id for r in request.evaluation.results}:
            raise ValueError("finding evaluation scenario set mismatch")
        rules = {r.rule_id: r for r in request.policy.rules}
        invariants = {i.invariant_id: i for i in request.contract.invariants}
        groups = {}

        def add(
            result,
            kind,
            dimension,
            rule_ids=(),
            invariant_id=None,
            assertion_id=None,
            clause=None,
        ):
            fingerprint = finding_fingerprint(
                kind,
                dimension,
                rule_ids=rule_ids,
                invariant_id=invariant_id,
                assertion_id=assertion_id,
                source_span_sha256=canonical_sha256(clause.span) if clause else None,
            )
            if fingerprint not in groups:
                groups[fingerprint] = {
                    "finding_id": f"finding-{fingerprint}",
                    "fingerprint_sha256": fingerprint,
                    "finding_type": kind,
                    "dimension": dimension,
                    "rule_ids": tuple(sorted(set(rule_ids))),
                    "invariant_id": invariant_id,
                    "assertion_id": assertion_id,
                    "evidence_level": "session_confirmed"
                    if invariant_id
                    else "candidate"
                    if clause
                    else "mechanically_reproduced",
                    "severity": invariants[invariant_id].severity
                    if invariant_id
                    else None,
                    "severity_origin": "session_invariant" if invariant_id else None,
                    "witnesses": {},
                    "citations": {},
                }
            group = groups[fingerprint]
            group["witnesses"][result.scenario_id] = TraceRef(
                scenario_id=result.scenario_id, trace_sha256=result.trace.trace_sha256
            )
            spans = (
                [clause.span]
                if clause
                else [
                    rules[r].provenance.span
                    for r in rule_ids
                    if r in rules and rules[r].provenance.kind == "text_citation"
                ]
            )
            for span in spans:
                group["citations"][canonical_sha256(span)] = span

        for result in sorted(request.evaluation.results, key=lambda r: r.scenario_id):
            scenario = scenarios[result.scenario_id]
            if result.verdict == "ERROR":
                continue
            assertions = {
                a.assertion_id: a
                for a in scenario_assertions(request.contract, scenario)
            }
            invariant_gap_dimensions = set()
            for outcome in result.assertion_results:
                assertion = assertions.get(outcome.assertion_id)
                if assertion is None:
                    raise ValueError("unknown assertion result")
                dimension = next(
                    d
                    for d in result.trace.resolved_effects
                    if d.dimension == assertion.dimension
                )
                if assertion.source_invariant_id and (
                    outcome.status == "FAIL"
                    or (
                        dimension.status == "GAP"
                        and not any(
                            e.dimension == assertion.dimension
                            for r in request.policy.rules
                            for e in r.effects
                        )
                    )
                ):
                    # A confirmed requirement with no executable effect is a witnessed intent omission.
                    add(
                        result,
                        "intent_breach",
                        assertion.dimension,
                        tuple(
                            r.rule_id
                            for r in request.policy.rules
                            if any(
                                e.dimension == assertion.dimension for e in r.effects
                            )
                        ),
                        invariant_id=assertion.source_invariant_id,
                    )
                    if assertion.dimension not in request.contract.required_dimensions:
                        invariant_gap_dimensions.add(assertion.dimension)
            for dimension in result.trace.resolved_effects:
                if (
                    dimension.status == "GAP"
                    and dimension.dimension not in invariant_gap_dimensions
                ):
                    target_ids = tuple(
                        r.rule_id
                        for r in request.policy.rules
                        if any(e.dimension == dimension.dimension for e in r.effects)
                    )
                    add(result, "structural_gap", dimension.dimension, target_ids)
                elif dimension.status == "CONFLICT":
                    survivors = tuple(
                        r
                        for r in dimension.applicable_rule_ids
                        if r not in dimension.overridden_rule_ids
                    )
                    add(result, "conflict", dimension.dimension, survivors)
                for clause_id in dimension.unsupported_clause_ids:
                    clause = next(
                        c
                        for c in request.policy.unsupported_clauses
                        if c.clause_id == clause_id
                    )
                    add(
                        result, "unsupported_clause", dimension.dimension, clause=clause
                    )
        findings = []
        for fingerprint, group in sorted(groups.items()):
            witnesses, citations = group.pop("witnesses"), group.pop("citations")
            findings.append(
                Finding(
                    **group,
                    scenario_ids=tuple(sorted(witnesses)),
                    traces=tuple(witnesses[key] for key in sorted(witnesses)),
                    citations=tuple(citations[key] for key in sorted(citations)),
                )
            )
        digest = canonical_sha256(tuple(findings))
        return FindingReport(
            report_id=f"findings-{digest}",
            inputs=request.evaluation.inputs,
            findings=tuple(findings),
        )
