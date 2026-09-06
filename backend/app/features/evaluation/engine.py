"""Authoritative pure Python execution over frozen, hash-bound scenarios."""

from dataclasses import dataclass

from app.core.artifacts import complete_payload_projection, semantic_payload_projection
from app.core.hashing import canonical_sha256
from app.domain.models import (
    ComplianceResult,
    CoverageEvidence,
    CoverageSnapshot,
    DimensionResult,
    EffectDimension,
    EvaluatePolicyRequest,
    EvaluationReport,
    EvaluationTrace,
    PolicyContract,
    PolicyIR,
    PredicateResult,
    PublicError,
    Scenario,
    ScenarioEvaluation,
)
from app.features.evaluation.assertions import evaluate_assertion
from app.features.evaluation.compliance import derive_compliance
from app.features.evaluation.predicates import evaluate_conditions, rule_matches
from app.features.evaluation.resolution import (
    resolve_dimension,
    scenario_required_dimensions,
)
from app.features.evaluation.rule_validation import validate_rule_set

ENGINE_VERSION = "1.0.0"


def payload_hash(value):
    return canonical_sha256(complete_payload_projection(value))


def matched_invariants(contract, facts):
    return tuple(
        i
        for i in contract.invariants
        if all(p.matched for p in evaluate_conditions(i.when, facts))
    )


def scenario_assertions(contract, scenario):
    assertions = {a.assertion_id: a for a in scenario.assertions}
    for invariant in matched_invariants(contract, scenario.facts):
        assertion = invariant.assertion
        if (
            assertion.assertion_id in assertions
            and assertions[assertion.assertion_id] != assertion
        ):
            raise ValueError("conflicting frozen/invariant assertion identity")
        assertions[assertion.assertion_id] = assertion
    return tuple(assertions[key] for key in sorted(assertions))


def _trace(scenario_id, **kwargs):
    trace = EvaluationTrace(scenario_id=scenario_id, trace_sha256="0" * 64, **kwargs)
    return trace.model_copy(update={"trace_sha256": payload_hash(trace)})


def evaluate_scenario(
    policy: PolicyIR, contract: PolicyContract, scenario: Scenario
) -> ScenarioEvaluation:
    try:
        scenario = Scenario.model_validate(scenario)
        invariants = matched_invariants(contract, scenario.facts)
        assertions = scenario_assertions(contract, scenario)
        traces = tuple(
            rule_matches(r, scenario.facts)
            for r in sorted(policy.rules, key=lambda r: r.rule_id)
        )
        required = scenario_required_dimensions(
            scenario, contract, frozenset(i.invariant_id for i in invariants)
        )
        dimensions = tuple(
            resolve_dimension(policy, scenario, d.value, required, traces)
            for d in EffectDimension
        )
        compliance = tuple(
            derive_compliance(d.dimension, d.value, scenario.facts)
            if d.status == "VALUE"
            else ComplianceResult(
                dimension=d.dimension,
                status=d.status
                if d.status in ("ERROR", "NOT_APPLICABLE")
                else "INCONCLUSIVE",
            )
            for d in dimensions
            if d.dimension != "eligibility"
        )
        fired = tuple(t.rule_id for t in traces if t.matched)
        citations = {
            canonical_sha256(r.provenance): r.provenance
            for r in policy.rules
            if r.rule_id in fired
        }
        trace = _trace(
            scenario.scenario_id,
            fired_rule_ids=fired,
            predicate_results=tuple(
                PredicateResult(
                    rule_id=t.rule_id, predicate_index=index, matched=p.matched
                )
                for t in traces
                for index, p in enumerate(t.predicates)
            ),
            resolved_effects=dimensions,
            compliance_values=compliance,
            source_citations=tuple(citations[key] for key in sorted(citations)),
        )
        results = tuple(
            evaluate_assertion(a, dimensions, compliance) for a in assertions
        )
        states = {r.status for r in results}
        verdict = next(
            (s for s in ("ERROR", "FAIL", "INCONCLUSIVE") if s in states),
            "PASS" if results else "UNSCORED",
        )
        return ScenarioEvaluation(
            scenario_id=scenario.scenario_id,
            trace=trace,
            assertion_results=results,
            verdict=verdict,
        )
    except (ValueError, TypeError, AttributeError):
        trace = _trace(
            scenario.scenario_id,
            fired_rule_ids=(),
            predicate_results=(),
            resolved_effects=tuple(
                DimensionResult(dimension=d.value, status="ERROR")
                for d in EffectDimension
            ),
            compliance_values=tuple(
                ComplianceResult(dimension=d.value, status="ERROR")
                for d in EffectDimension
                if d.value != "eligibility"
            ),
            source_citations=(),
        )
        return ScenarioEvaluation(
            scenario_id=scenario.scenario_id,
            trace=trace,
            verdict="ERROR",
            error=PublicError(
                code="INVALID_INPUT",
                message="Scenario facts or assertions are invalid.",
            ),
        )


def validate_evaluation_anchors(request: EvaluatePolicyRequest):
    checks = (
        request.inputs.policy_sha256 == payload_hash(request.policy),
        request.inputs.contract_sha256 == payload_hash(request.contract),
        request.inputs.suite_sha256
        == payload_hash(request.suite)
        == request.suite.content_sha256,
        request.suite.document_sha256 == request.policy.document_sha256,
        request.suite.policy_contract_sha256 == payload_hash(request.contract),
        request.engine_version == request.suite.engine_version == ENGINE_VERSION,
    )
    if request.policy.kind == "compiled_baseline":
        checks += (
            request.suite.rule_set_sha256
            == canonical_sha256(semantic_payload_projection(request.policy)),
        )
    if not all(checks):
        raise ValueError("HASH_MISMATCH: evaluation anchors or engine version")


@dataclass(frozen=True)
class DeterministicEvaluationEngine:
    def evaluate(self, request: EvaluatePolicyRequest) -> EvaluationReport:
        validate_rule_set(request.policy)
        PolicyContract.model_validate(request.contract)
        validate_evaluation_anchors(request)
        results = tuple(
            evaluate_scenario(request.policy, request.contract, s)
            for s in sorted(request.suite.scenarios, key=lambda s: s.scenario_id)
        )
        evidence = {}
        for result in results:
            for rid in result.trace.fired_rule_ids:
                evidence.setdefault(("rule", rid, None, None), []).append(
                    result.scenario_id
                )
            for p in result.trace.predicate_results:
                evidence.setdefault(
                    ("predicate_branch", p.rule_id, p.predicate_index, p.matched), []
                ).append(result.scenario_id)
            if result.verdict != "ERROR":
                scenario = next(
                    s
                    for s in request.suite.scenarios
                    if s.scenario_id == result.scenario_id
                )
                for i in matched_invariants(request.contract, scenario.facts):
                    evidence.setdefault(
                        ("invariant", i.invariant_id, None, None), []
                    ).append(result.scenario_id)
        covered_rules = {key[1] for key in evidence if key[0] == "rule"}
        covered_invariants = {key[1] for key in evidence if key[0] == "invariant"}
        missing_rules = tuple(
            sorted(
                r.rule_id
                for r in request.policy.rules
                if r.rule_id not in covered_rules
            )
        )
        missing_invariants = tuple(
            sorted(
                i.invariant_id
                for i in request.contract.invariants
                if i.invariant_id not in covered_invariants
            )
        )
        coverage = CoverageSnapshot(
            total_rules=len(request.policy.rules),
            covered_rules=len(covered_rules),
            total_invariants=len(request.contract.invariants),
            covered_invariants=len(covered_invariants),
            total_predicate_branches=2 * sum(len(r.when) for r in request.policy.rules),
            covered_predicate_branches=sum(
                key[0] == "predicate_branch" for key in evidence
            ),
            evidence=tuple(
                CoverageEvidence(
                    target_kind=k[0],
                    target_id=k[1],
                    predicate_index=k[2],
                    predicate_outcome=k[3],
                    scenario_ids=tuple(sorted(ids)),
                )
                for k, ids in sorted(evidence.items())
            ),
            missing_rule_ids=missing_rules,
            missing_invariant_ids=missing_invariants,
            status="satisfied"
            if not missing_rules and not missing_invariants
            else "pending",
        )
        digest = canonical_sha256(
            {
                "inputs": request.inputs,
                "results": results,
                "coverage": coverage,
                "engine_version": ENGINE_VERSION,
            }
        )
        return EvaluationReport(
            report_id=f"evaluation-{digest}",
            inputs=request.inputs,
            engine_version=ENGINE_VERSION,
            results=results,
            coverage=coverage,
        )
