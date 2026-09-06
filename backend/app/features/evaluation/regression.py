"""Exhaustive frozen-pair comparison and seven independent acceptance gates."""

from dataclasses import dataclass

from app.core.hashing import canonical_sha256
from app.domain.models import (
    AnalyzeFindingsRequest,
    AssertionResult,
    AssertionTransition,
    AssertionTransitionCounts,
    CompareRevisionRequest,
    ComparisonBundle,
    EffectDimension,
    EffectStateCounts,
    EvaluatePolicyRequest,
    Finding,
    MetricsRequest,
    OverrideRef,
    PatchAcceptanceCounts,
    PatchAcceptanceReport,
    PolicyContract,
    RegressionReport,
    Scenario,
    ScenarioEvaluation,
)
from app.features.evaluation.engine import (
    DeterministicEvaluationEngine,
    payload_hash,
    scenario_assertions,
)
from app.features.evaluation.findings import DeterministicFindingAnalyzer
from app.features.evaluation.signatures import semantic_rule_signature

_BAD = {"GAP", "CONFLICT", "INCONCLUSIVE", "ERROR"}


def compare_assertion_outcomes(
    before: AssertionResult,
    after: AssertionResult,
    *,
    scenario_id="scenario",
    protected=False,
    targeted=False,
) -> AssertionTransition:
    if before.assertion_id != after.assertion_id:
        raise ValueError("assertion identity mismatch")
    return AssertionTransition(
        scenario_id=scenario_id,
        assertion_id=before.assertion_id,
        before=before.status,
        after=after.status,
        protected=protected,
        targeted=targeted,
    )


def effect_counts(report):
    return EffectStateCounts(
        **{
            status: sum(
                d.status == status
                for r in report.results
                for d in r.trace.resolved_effects
            )
            for status in (
                "VALUE",
                "GAP",
                "CONFLICT",
                "NOT_APPLICABLE",
                "INCONCLUSIVE",
                "ERROR",
            )
        }
    )


def validate_report(policy, contract, suite, report):
    expected = DeterministicEvaluationEngine().evaluate(
        EvaluatePolicyRequest(
            policy=policy,
            contract=contract,
            suite=suite,
            inputs=report.inputs,
            engine_version=report.engine_version,
        )
    )
    if expected != report:
        raise ValueError("comparison requires complete authentic deterministic reports")


def target_witnesses_fixed(
    finding: Finding,
    before: dict[str, ScenarioEvaluation],
    after: dict[str, ScenarioEvaluation],
    scenarios: dict[str, Scenario],
    contract: PolicyContract,
) -> bool:
    """Require actual repair of every original witness and its independent assertions."""
    if finding.evidence_level == "candidate":
        return False
    for scenario_id in finding.scenario_ids:
        old, new = before[scenario_id], after[scenario_id]
        old_dimension = next(
            d for d in old.trace.resolved_effects if d.dimension == finding.dimension
        )
        new_dimension = next(
            d for d in new.trace.resolved_effects if d.dimension == finding.dimension
        )
        if new_dimension.status != "VALUE":
            return False
        assertions = tuple(
            a
            for a in scenario_assertions(contract, scenarios[scenario_id])
            if a.dimension == finding.dimension
        )
        old_results = {a.assertion_id: a.status for a in old.assertion_results}
        new_results = {a.assertion_id: a.status for a in new.assertion_results}
        if any(new_results.get(a.assertion_id) != "PASS" for a in assertions):
            return False
        if finding.invariant_id is not None:
            relevant = tuple(
                a for a in assertions if a.source_invariant_id == finding.invariant_id
            )
            if not relevant or not all(
                old_results.get(a.assertion_id) != "PASS" for a in relevant
            ):
                return False
        elif finding.assertion_id is not None:
            if (
                old_results.get(finding.assertion_id) == "PASS"
                or new_results.get(finding.assertion_id) != "PASS"
            ):
                return False
        elif old_dimension.status not in {"GAP", "CONFLICT"}:
            return False
    return True


@dataclass(frozen=True)
class DeterministicRegressionAnalyzer:
    def compare(self, request: CompareRevisionRequest) -> ComparisonBundle:
        from app.features.evaluation.metrics import compute_metrics

        before, after = request.baseline_evaluation, request.revised_evaluation
        for key in (
            "suite_sha256",
            "contract_sha256",
            "engine_sha256",
            "run_manifest_sha256",
        ):
            if getattr(before.inputs, key) != getattr(after.inputs, key):
                raise ValueError("HASH_MISMATCH: frozen comparison anchors")
        validate_report(
            request.baseline_policy, request.contract, request.suite, before
        )
        validate_report(request.revised_policy, request.contract, request.suite, after)
        if (
            request.baseline_findings.inputs != before.inputs
            or request.revised_findings.inputs != after.inputs
        ):
            raise ValueError("HASH_MISMATCH: comparison finding anchors")
        if not (
            request.proposal.document_sha256 == request.baseline_policy.document_sha256
            and request.proposal.suite_sha256 == payload_hash(request.suite)
            and request.proposal.policy_contract_sha256
            == payload_hash(request.contract)
            and request.proposal.rule_set_sha256 == request.suite.rule_set_sha256
        ):
            raise ValueError("HASH_MISMATCH: proposal anchors")
        for policy, evaluation, supplied in (
            (request.baseline_policy, before, request.baseline_findings),
            (request.revised_policy, after, request.revised_findings),
        ):
            expected_findings = DeterministicFindingAnalyzer().analyze(
                AnalyzeFindingsRequest(
                    policy=policy,
                    contract=request.contract,
                    suite=request.suite,
                    evaluation=evaluation,
                )
            )

            def evidence(finding):
                updates = {"review_status": "pending"}
                if finding.severity_origin == "session_reviewer":
                    updates.update(severity=None, severity_origin=None)
                return finding.model_copy(update=updates)

            if (
                tuple(evidence(f) for f in supplied.findings)
                != expected_findings.findings
            ):
                raise ValueError("comparison finding evidence is not authentic")
        targets = {
            f.finding_id: f
            for f in request.baseline_findings.findings
            if f.finding_id in request.proposal.accepted_finding_ids
        }
        if set(targets) != set(request.proposal.accepted_finding_ids):
            raise ValueError("unknown targeted finding")
        remaining_fingerprints = {
            f.fingerprint_sha256 for f in request.revised_findings.findings
        }
        scenarios = {s.scenario_id: s for s in request.suite.scenarios}
        before_by_id = {r.scenario_id: r for r in before.results}
        after_by_id = {r.scenario_id: r for r in after.results}
        fixed = sum(
            f.fingerprint_sha256 not in remaining_fingerprints
            and target_witnesses_fixed(
                f, before_by_id, after_by_id, scenarios, request.contract
            )
            for f in targets.values()
        )
        target_pairs = {
            (sid, f.dimension) for f in targets.values() for sid in f.scenario_ids
        }
        target_assertions = {
            (sid, i.assertion.assertion_id)
            for f in targets.values()
            for sid in f.scenario_ids
            for i in request.contract.invariants
            if i.invariant_id == f.invariant_id
        }
        transitions, new_bad, outside, protected, holdout = (
            [],
            set(),
            set(),
            set(),
            set(),
        )
        after_by_id = {r.scenario_id: r for r in after.results}
        for old in before.results:
            new = after_by_id[old.scenario_id]
            scenario = scenarios[old.scenario_id]
            old_dimensions = {d.dimension: d for d in old.trace.resolved_effects}
            new_dimensions = {d.dimension: d for d in new.trace.resolved_effects}
            if set(old_dimensions) != {d.value for d in EffectDimension} or set(
                new_dimensions
            ) != set(old_dimensions):
                raise ValueError("missing or additional scenario-dimension pair")
            for dimension, result in new_dimensions.items():
                prior = old_dimensions[dimension]
                pair = (old.scenario_id, dimension)
                deterioration = result.status in _BAD and (
                    result.status != prior.status or result != prior
                )
                if deterioration:
                    new_bad.add(pair)
                    if pair not in target_pairs:
                        outside.add(pair)
                    if scenario.protected:
                        protected.add(pair)
                    if scenario.partition == "holdout":
                        holdout.add(pair)
            old_assertions = {a.assertion_id: a for a in old.assertion_results}
            new_assertions = {a.assertion_id: a for a in new.assertion_results}
            if set(old_assertions) != set(new_assertions):
                raise ValueError("missing or additional assertion instance")
            for aid in sorted(old_assertions):
                prior, result = old_assertions[aid], new_assertions[aid]
                pair = (old.scenario_id, aid)
                transitions.append(
                    compare_assertion_outcomes(
                        prior,
                        result,
                        scenario_id=old.scenario_id,
                        protected=scenario.protected,
                        targeted=pair in target_assertions,
                    )
                )
                deterioration = (
                    prior.status == "PASS" and result.status != "PASS"
                ) or (
                    prior.status in ("FAIL", "INCONCLUSIVE")
                    and result.status == "ERROR"
                )
                if deterioration:
                    if pair not in target_assertions:
                        outside.add(pair)
                    if scenario.protected:
                        protected.add(pair)
                    if scenario.partition == "holdout":
                        holdout.add(pair)
            old_compliance = {
                c.dimension: c.status for c in old.trace.compliance_values
            }
            for c in new.trace.compliance_values:
                if (
                    old_compliance.get(c.dimension) == "COMPLIANT"
                    and c.status != "COMPLIANT"
                ):
                    pair = (old.scenario_id, c.dimension)
                    if pair not in target_pairs:
                        outside.add(pair)
                    if scenario.protected:
                        protected.add(pair)
                    if scenario.partition == "holdout":
                        holdout.add(pair)
        baseline_rules = {r.rule_id: r for r in request.baseline_policy.rules}
        revised_rules = {r.rule_id: r for r in request.revised_policy.rules}
        allowed = {op.rule_id for op in request.proposal.operations}
        unrelated = 0
        for rid in set(baseline_rules) | set(revised_rules):
            if rid not in allowed and (
                rid not in baseline_rules
                or rid not in revised_rules
                or semantic_rule_signature(baseline_rules[rid], baseline_rules)
                != semantic_rule_signature(revised_rules[rid], revised_rules)
            ):
                unrelated += 1
        # Never allow removed rules or added rules without a corresponding add operation.
        unrelated += len(set(baseline_rules) - set(revised_rules))
        unrelated += len(
            (set(revised_rules) - set(baseline_rules))
            - {
                op.rule_id
                for op in request.proposal.operations
                if op.kind == "add_rule"
            }
        )
        for operation in request.proposal.operations:
            actual = revised_rules.get(operation.rule_id)
            old = baseline_rules.get(operation.rule_id)
            if actual is None:
                unrelated += 1
                continue
            if operation.kind == "add_override":
                if old is None:
                    unrelated += 1
                    continue
                expected_fields = (
                    old.when,
                    old.effects,
                    old.overrides
                    + (
                        OverrideRef(
                            dimension=operation.dimension,
                            target_rule_id=operation.target_rule_id,
                        ),
                    ),
                )
            else:
                expected_fields = (
                    operation.rule.when,
                    operation.rule.effects,
                    operation.rule.overrides,
                )
            if (actual.when, actual.effects, actual.overrides) != expected_fields:
                unrelated += 1
            if actual.revision != (old.revision + 1 if old else 1):
                unrelated += 1
            if (
                actual.provenance.kind != "session_revision"
                or actual.provenance.proposal_id != request.proposal.proposal_id
            ):
                unrelated += 1
        if (
            request.baseline_policy.unsupported_clauses
            != request.revised_policy.unsupported_clauses
        ):
            unrelated += 1
        counts = {
            "pass_to_pass": 0,
            "fail_to_pass": 0,
            "pass_to_fail": 0,
            "fail_to_fail": 0,
            "inconclusive_or_error": 0,
        }
        for t in transitions:
            key = f"{t.before.lower()}_to_{t.after.lower()}"
            counts[key if key in counts else "inconclusive_or_error"] += 1
        baseline_states, revised_states = effect_counts(before), effect_counts(after)
        regression = RegressionReport(
            report_id=f"regression-{canonical_sha256((before, after))}",
            baseline_inputs=before.inputs,
            revised_inputs=after.inputs,
            baseline_effect_states=baseline_states,
            revised_effect_states=revised_states,
            assertion_transition_counts=AssertionTransitionCounts(**counts),
            assertion_transitions=tuple(transitions),
        )
        checks = {
            "suite_hash_matches": before.inputs.suite_sha256
            == after.inputs.suite_sha256,
            "all_target_findings_fixed": fixed == len(targets),
            "zero_new_failures_outside_targets": not outside,
            "zero_protected_regressions": not protected,
            "no_increase_in_gap_conflict_inconclusive_or_error": not new_bad,
            "unrelated_rules_unchanged": not unrelated,
            "holdout_not_worse": not holdout,
        }
        acceptance = PatchAcceptanceReport(
            baseline_inputs=before.inputs,
            revised_inputs=after.inputs,
            **checks,
            patch_accepted=all(checks.values()),
            counts=PatchAcceptanceCounts(
                target_findings=len(targets),
                fixed_target_findings=fixed,
                new_failures_outside_targets=len(outside),
                protected_regressions=len(protected),
                baseline_gap_conflict_inconclusive_or_error=sum(
                    getattr(baseline_states, s) for s in _BAD
                ),
                revised_gap_conflict_inconclusive_or_error=sum(
                    getattr(revised_states, s) for s in _BAD
                ),
                unrelated_rule_changes=unrelated,
                holdout_regressions=len(holdout),
            ),
        )
        return ComparisonBundle(
            baseline_inputs=before.inputs,
            revised_inputs=after.inputs,
            regression=regression,
            acceptance=acceptance,
            baseline_metrics=compute_metrics(
                MetricsRequest(evaluation=before, findings=request.baseline_findings)
            ),
            revised_metrics=compute_metrics(
                MetricsRequest(evaluation=after, findings=request.revised_findings)
            ),
        )
