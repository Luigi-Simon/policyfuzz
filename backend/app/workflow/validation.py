"""Workflow graph validation, independent of deterministic specialist semantics."""

from collections import Counter

from app.core.artifacts import (
    complete_payload_projection,
    semantic_payload_projection,
    validate_artifact_envelope,
)
from app.core.hashing import canonical_sha256
from app.domain.models import (
    ComparisonBundle,
    EvaluationReport,
    FindingReport,
    InputHashes,
    MetricsReport,
    RevisionProposal,
    RunRecord,
    ScenarioBatch,
    ScenarioSuite,
)


def digest(value):
    return canonical_sha256(complete_payload_projection(value))


def semantic(value):
    return canonical_sha256(semantic_payload_projection(value))


def require(condition):
    if not condition:
        raise ValueError("workflow evidence is inconsistent")


def input_hashes(policy, contract, suite, manifest):
    return InputHashes(
        policy_sha256=digest(policy),
        contract_sha256=digest(contract),
        suite_sha256=digest(suite),
        engine_sha256=manifest.engine_sha256,
        run_manifest_sha256=digest(manifest),
    )


def validate_batch(value, budget, policy, contract):
    batch = ScenarioBatch.model_validate(value)
    require(len(batch.candidates) <= budget)
    require(len({c.candidate_id for c in batch.candidates}) == len(batch.candidates))
    rules = {r.rule_id for r in policy.rules}
    invariants = {i.invariant_id: i for i in contract.invariants}
    for case in batch.candidates:
        require(set(case.target_rule_ids) <= rules)
        require(set(case.target_invariant_ids) <= invariants.keys())
        for assertion in case.assertions:
            if assertion.origin == "session_confirmed":
                invariant = invariants.get(assertion.source_invariant_id)
                require(invariant is not None and invariant.assertion == assertion)
    return batch


def validate_suite(
    value, policy, contract, manifest, *, suite_id=None, candidate_count=None
):
    suite = ScenarioSuite.model_validate(value)
    require(suite.content_sha256 == digest(suite))
    require(suite.document_sha256 == policy.document_sha256)
    require(suite.policy_contract_sha256 == digest(contract))
    require(suite.rule_set_sha256 == semantic(policy))
    require(
        suite.engine_version == manifest.engine_version
        and suite.seed == manifest.random_seed
    )
    if suite_id is not None:
        require(suite.suite_id == suite_id)
    if candidate_count is not None:
        require(len(suite.scenarios) <= candidate_count)
    return suite


def validate_evaluation(value, request):
    report = EvaluationReport.model_validate(value)
    require(
        report.inputs == request.inputs
        and report.engine_version == request.engine_version
    )
    scenarios = {s.scenario_id: s for s in request.suite.scenarios}
    require({r.scenario_id for r in report.results} == scenarios.keys())
    rules = {r.rule_id: r for r in request.policy.rules}
    invariants = {i.invariant_id: i for i in request.contract.invariants}
    results = {r.scenario_id: r for r in report.results}
    permitted_provenances = tuple(rule.provenance for rule in request.policy.rules)
    for row in report.results:
        require(
            all(
                provenance in permitted_provenances
                for provenance in row.trace.source_citations
            )
        )
        require(row.trace.trace_sha256 == digest(row.trace))
        require(set(row.trace.fired_rule_ids) <= rules.keys())
        assertions = {a.assertion_id: a for a in scenarios[row.scenario_id].assertions}
        result_ids = [a.assertion_id for a in row.assertion_results]
        require(
            len(set(result_ids)) == len(result_ids)
            and set(result_ids) == assertions.keys()
        )
        for predicate in row.trace.predicate_results:
            require(
                predicate.rule_id in rules
                and predicate.predicate_index < len(rules[predicate.rule_id].when)
            )
        for effect in row.trace.resolved_effects:
            require(
                set(effect.applicable_rule_ids + effect.overridden_rule_ids)
                <= rules.keys()
            )
    coverage = report.coverage
    require(
        coverage.total_rules == len(rules)
        and coverage.total_invariants == len(invariants)
    )
    require(
        coverage.total_predicate_branches
        == 2 * sum(len(r.when) for r in rules.values())
    )
    covered_rules, covered_invariants, branches = set(), set(), set()
    evidence_keys = set()
    for evidence in coverage.evidence:
        key = (
            evidence.target_kind,
            evidence.target_id,
            evidence.predicate_index,
            evidence.predicate_outcome,
        )
        require(key not in evidence_keys)
        evidence_keys.add(key)
        require(
            bool(evidence.scenario_ids)
            and len(set(evidence.scenario_ids)) == len(evidence.scenario_ids)
        )
        require(set(evidence.scenario_ids) <= scenarios.keys())
        if evidence.target_kind == "rule":
            require(evidence.target_id in rules)
            for sid in evidence.scenario_ids:
                require(evidence.target_id in results[sid].trace.fired_rule_ids)
            covered_rules.add(evidence.target_id)
        elif evidence.target_kind == "invariant":
            require(evidence.target_id in invariants)
            invariant = invariants[evidence.target_id]
            for sid in evidence.scenario_ids:
                require(invariant.assertion in scenarios[sid].assertions)
                require(
                    any(
                        a.assertion_id == invariant.assertion.assertion_id
                        for a in results[sid].assertion_results
                    )
                )
            covered_invariants.add(evidence.target_id)
        else:
            require(
                evidence.target_id in rules
                and evidence.predicate_index < len(rules[evidence.target_id].when)
            )
            for sid in evidence.scenario_ids:
                require(
                    any(
                        p.rule_id == evidence.target_id
                        and p.predicate_index == evidence.predicate_index
                        and p.matched == evidence.predicate_outcome
                        for p in results[sid].trace.predicate_results
                    )
                )
            branches.add(key)
    require(
        coverage.covered_rules == len(covered_rules)
        and coverage.covered_invariants == len(covered_invariants)
        and coverage.covered_predicate_branches == len(branches)
    )
    require(set(coverage.missing_rule_ids) == rules.keys() - covered_rules)
    require(
        set(coverage.missing_invariant_ids) == invariants.keys() - covered_invariants
    )
    require(len(set(coverage.missing_rule_ids)) == len(coverage.missing_rule_ids))
    require(
        len(set(coverage.missing_invariant_ids)) == len(coverage.missing_invariant_ids)
    )
    return report


def minimum_coverage(report):
    coverage = report.coverage
    return not coverage.missing_rule_ids and not coverage.missing_invariant_ids


def validate_findings(value, evaluation, policy, contract, *, reviewed=False):
    report = FindingReport.model_validate(value)
    require(report.inputs == evaluation.inputs)
    require(len({f.finding_id for f in report.findings}) == len(report.findings))
    rows = {r.scenario_id: r for r in evaluation.results}
    rules = {r.rule_id for r in policy.rules}
    invariants = {i.invariant_id: i for i in contract.invariants}
    for finding in report.findings:
        require(reviewed or finding.review_status == "pending")
        require(set(finding.scenario_ids) <= rows.keys())
        require(set(finding.rule_ids) <= rules)
        for trace in finding.traces:
            require(trace.trace_sha256 == rows[trace.scenario_id].trace.trace_sha256)
        if finding.invariant_id is not None:
            require(finding.invariant_id in invariants)
            invariant = invariants[finding.invariant_id]
            require(finding.assertion_id in (None, invariant.assertion.assertion_id))
            if finding.severity is not None:
                require(
                    finding.severity == invariant.severity
                    and finding.severity_origin == "session_invariant"
                )
        elif finding.severity is not None:
            # Stage-supplied reviewer authority is not accepted before a decision.
            require(
                reviewed
                and finding.review_status == "accepted"
                and finding.severity_origin == "session_reviewer"
            )
    return report


def reviewable(report, suite):
    visible = {s.scenario_id for s in suite.scenarios if s.partition == "visible"}
    return tuple(
        f
        for f in report.findings
        if f.evidence_level != "candidate"
        and f.finding_type != "potential_loophole"
        and set(f.scenario_ids) <= visible
    )


def validate_metrics(value, evaluation, findings):
    report = MetricsReport.model_validate(value)
    require(
        report.inputs == evaluation.inputs and report.coverage == evaluation.coverage
    )
    require(report.scenario_count == len(evaluation.results))
    require(
        report.unique_finding_count
        == len(
            {
                f.fingerprint_sha256
                for f in findings.findings
                if f.evidence_level != "candidate"
                and f.finding_type != "potential_loophole"
            }
        )
    )
    effects = Counter(
        e.status for r in evaluation.results for e in r.trace.resolved_effects
    )
    for field in (
        "VALUE",
        "GAP",
        "NOT_APPLICABLE",
        "CONFLICT",
        "INCONCLUSIVE",
        "ERROR",
    ):
        require(getattr(report.effect_states, field) == effects[field])
    counts = Counter(a.status for r in evaluation.results for a in r.assertion_results)
    for field, status in (
        ("passed", "PASS"),
        ("failed", "FAIL"),
        ("inconclusive", "INCONCLUSIVE"),
        ("error", "ERROR"),
    ):
        require(getattr(report.assertions, field) == counts[status])
    return report


def validate_proposal(value, request):
    proposal = RevisionProposal.model_validate(value)
    for field in (
        "document_sha256",
        "rule_set_sha256",
        "policy_contract_sha256",
        "suite_sha256",
    ):
        require(getattr(proposal, field) == getattr(request, field))
    accepted = {d.finding_id for d in request.decisions if d.decision == "accept"}
    require(set(proposal.accepted_finding_ids) == accepted)
    require({f for op in proposal.operations for f in op.finding_ids} == accepted)
    rules = {r.rule_id: r for r in request.policy.rules}
    for operation in proposal.operations:
        if operation.kind == "add_rule":
            require(operation.rule_id not in rules)
        else:
            require(operation.rule_id in rules)
            if operation.kind == "replace_rule":
                require(
                    operation.expected_revision == rules[operation.rule_id].revision
                )
            else:
                require(operation.target_rule_id in rules)
    return proposal


def validate_comparison(value, request):
    bundle = ComparisonBundle.model_validate(value)
    before, after = request.baseline_evaluation, request.revised_evaluation
    for evidence in (bundle, bundle.regression, bundle.acceptance):
        require(
            evidence.baseline_inputs == before.inputs
            and evidence.revised_inputs == after.inputs
        )
    validate_metrics(bundle.baseline_metrics, before, request.baseline_findings)
    validate_metrics(bundle.revised_metrics, after, request.revised_findings)
    require(
        bundle.regression.baseline_effect_states
        == bundle.baseline_metrics.effect_states
    )
    require(
        bundle.regression.revised_effect_states == bundle.revised_metrics.effect_states
    )
    cases = {s.scenario_id: s for s in request.suite.scenarios}
    old = {
        (r.scenario_id, a.assertion_id): a.status
        for r in before.results
        for a in r.assertion_results
    }
    new = {
        (r.scenario_id, a.assertion_id): a.status
        for r in after.results
        for a in r.assertion_results
    }
    transitions = bundle.regression.assertion_transitions
    require(
        {(t.scenario_id, t.assertion_id) for t in transitions}
        == old.keys()
        == new.keys()
    )
    transition_counts = Counter()
    for transition in transitions:
        key = (transition.scenario_id, transition.assertion_id)
        require(transition.before == old[key] and transition.after == new[key])
        require(transition.protected == cases[transition.scenario_id].protected)
        name = (
            f"{transition.before.lower()}_to_{transition.after.lower()}"
            if transition.before in {"PASS", "FAIL"}
            and transition.after in {"PASS", "FAIL"}
            else "inconclusive_or_error"
        )
        transition_counts[name] += 1
    for field in (
        "pass_to_pass",
        "fail_to_pass",
        "pass_to_fail",
        "fail_to_fail",
        "inconclusive_or_error",
    ):
        require(
            getattr(bundle.regression.assertion_transition_counts, field)
            == transition_counts[field]
        )
    acceptance = bundle.acceptance
    counts = acceptance.counts
    require(counts.target_findings == len(request.proposal.accepted_finding_ids))
    require(counts.fixed_target_findings <= counts.target_findings)
    require(
        counts.protected_regressions
        == sum(
            t.protected and t.before == "PASS" and t.after != "PASS"
            for t in transitions
        )
    )
    require(
        counts.holdout_regressions
        <= sum(cases[t.scenario_id].partition == "holdout" for t in transitions)
    )
    bad_states = {"GAP", "CONFLICT", "INCONCLUSIVE", "ERROR"}
    require(
        counts.baseline_gap_conflict_inconclusive_or_error
        == sum(
            e.status in bad_states
            for r in before.results
            for e in r.trace.resolved_effects
        )
    )
    require(
        counts.revised_gap_conflict_inconclusive_or_error
        == sum(
            e.status in bad_states
            for r in after.results
            for e in r.trace.resolved_effects
        )
    )
    require(
        acceptance.suite_hash_matches
        == (before.inputs.suite_sha256 == after.inputs.suite_sha256)
    )
    require(
        acceptance.all_target_findings_fixed
        == (counts.target_findings == counts.fixed_target_findings)
    )
    require(
        acceptance.zero_new_failures_outside_targets
        == (counts.new_failures_outside_targets == 0)
    )
    require(
        acceptance.zero_protected_regressions == (counts.protected_regressions == 0)
    )
    require(
        not acceptance.no_increase_in_gap_conflict_inconclusive_or_error
        or counts.revised_gap_conflict_inconclusive_or_error
        <= counts.baseline_gap_conflict_inconclusive_or_error
    )
    require(
        acceptance.unrelated_rules_unchanged == (counts.unrelated_rule_changes == 0)
    )
    require(acceptance.holdout_not_worse == (counts.holdout_regressions == 0))
    return bundle


def validate_cached_record(value):
    """Validate a recorded graph; the injected loader authenticates sample identity."""
    from app.domain.models import (
        CompareRevisionRequest,
        EvaluatePolicyRequest,
        ProposeRevisionRequest,
    )

    record = RunRecord.model_validate(value)
    require(record.manifest.mode == "cached")
    require(
        record.stage
        in {
            "complete",
            "completed_no_findings",
            "completed_no_revision",
            "contract_rejected",
            "revision_rejected",
            "coverage_limit_exceeded",
            "failed",
        }
    )
    seen = {}
    payloads = []
    manifests = []
    frozen_suite = None
    frozen_contract = None

    def require_frozen_inputs(inputs):
        require(frozen_suite is not None and frozen_contract is not None)
        require(inputs.suite_sha256 == digest(frozen_suite))
        require(inputs.contract_sha256 == digest(frozen_contract))
        require(inputs.engine_sha256 == record.manifest.engine_sha256)
        require(inputs.run_manifest_sha256 == digest(record.manifest))

    for envelope in record.artifacts:
        envelope = validate_artifact_envelope(envelope)
        require(envelope.run_manifest_id == record.manifest.manifest_id)
        require(set(envelope.parent_hashes) <= seen.keys())
        payload = envelope.payload
        kind = envelope.artifact_type
        if kind == "run_manifest":
            require(payload == record.manifest)
            manifests.append(payload)
        elif kind == "policy_ir":
            require(
                any(
                    a.artifact_type == "policy_document"
                    and a.payload.document_sha256 == payload.document_sha256
                    for a in seen.values()
                )
            )
        elif kind == "policy_contract":
            require(frozen_contract is None)
            frozen_contract = payload
        elif kind == "scenario_suite":
            require(frozen_suite is None and frozen_contract is not None)
            require(payload.policy_contract_sha256 == digest(frozen_contract))
            frozen_suite = payload
            policy = next(
                (
                    a.payload
                    for a in seen.values()
                    if a.artifact_type == "policy_ir"
                    and a.semantic_sha256 == payload.rule_set_sha256
                ),
                None,
            )
            contract = seen.get(payload.policy_contract_sha256)
            require(
                policy is not None
                and contract is not None
                and contract.artifact_type == "policy_contract"
            )
            validate_suite(payload, policy, contract.payload, record.manifest)
            require(
                {digest(policy), digest(contract.payload), digest(record.manifest)}
                <= set(envelope.parent_hashes)
            )
        elif kind in {"evaluation_report", "finding_report", "metrics_report"}:
            inputs = payload.inputs
            require_frozen_inputs(inputs)
            policy = seen.get(inputs.policy_sha256)
            contract = seen.get(inputs.contract_sha256)
            suite = seen.get(inputs.suite_sha256)
            require(policy is not None and policy.artifact_type == "policy_ir")
            require(
                contract is not None and contract.artifact_type == "policy_contract"
            )
            require(suite is not None and suite.artifact_type == "scenario_suite")
            require(
                inputs
                == input_hashes(
                    policy.payload, contract.payload, suite.payload, record.manifest
                )
            )
            require(
                {
                    inputs.policy_sha256,
                    inputs.contract_sha256,
                    inputs.suite_sha256,
                    digest(record.manifest),
                }
                <= set(envelope.parent_hashes)
            )
            if kind == "evaluation_report":
                validate_evaluation(
                    payload,
                    EvaluatePolicyRequest(
                        policy=policy.payload,
                        contract=contract.payload,
                        suite=suite.payload,
                        inputs=inputs,
                        engine_version=record.manifest.engine_version,
                    ),
                )
            else:
                evaluation = next(
                    (
                        a.payload
                        for a in reversed(payloads)
                        if a.artifact_type == "evaluation_report"
                        and a.payload.inputs == inputs
                    ),
                    None,
                )
                require(
                    evaluation is not None
                    and digest(evaluation) in envelope.parent_hashes
                )
                if kind == "finding_report":
                    validate_findings(
                        payload,
                        evaluation,
                        policy.payload,
                        contract.payload,
                        reviewed=True,
                    )
                else:
                    findings = next(
                        (
                            a.payload
                            for a in reversed(payloads)
                            if a.artifact_type == "finding_report"
                            and a.payload.inputs == inputs
                        ),
                        None,
                    )
                    require(
                        findings is not None
                        and digest(findings) in envelope.parent_hashes
                    )
                    validate_metrics(payload, evaluation, findings)
        elif kind == "revision_proposal":
            require(frozen_suite is not None and frozen_contract is not None)
            require(payload.suite_sha256 == digest(frozen_suite))
            require(payload.policy_contract_sha256 == digest(frozen_contract))
            policy = next(
                (
                    a.payload
                    for a in seen.values()
                    if a.artifact_type == "policy_ir"
                    and a.semantic_sha256 == payload.rule_set_sha256
                ),
                None,
            )
            contract = seen.get(payload.policy_contract_sha256)
            suite = seen.get(payload.suite_sha256)
            require(policy is not None and contract is not None and suite is not None)
            findings = next(
                (
                    a.payload
                    for a in reversed(payloads)
                    if a.artifact_type == "finding_report"
                    and a.payload.inputs.policy_sha256 == digest(policy)
                ),
                None,
            )
            require(findings is not None)
            accepted = tuple(
                f for f in findings.findings if f.review_status == "accepted"
            )
            require(
                set(payload.accepted_finding_ids)
                <= {f.finding_id for f in reviewable(findings, suite.payload)}
            )
            validate_proposal(
                payload,
                ProposeRevisionRequest(
                    policy=policy,
                    contract=contract.payload,
                    suite=suite.payload,
                    findings=findings.model_copy(update={"findings": accepted}),
                    decisions=tuple(
                        d for d in record.finding_decisions if d.decision == "accept"
                    ),
                    document_sha256=policy.document_sha256,
                    rule_set_sha256=semantic(policy),
                    policy_contract_sha256=digest(contract.payload),
                    suite_sha256=digest(suite.payload),
                ),
            )
        elif kind in {"regression_report", "patch_acceptance_report"}:
            for inputs in (payload.baseline_inputs, payload.revised_inputs):
                require_frozen_inputs(inputs)
                require(
                    any(
                        a.artifact_type == "evaluation_report"
                        and a.payload.inputs == inputs
                        for a in payloads
                    )
                )
        elif kind == "comparison_bundle":
            before, after = payload.baseline_inputs, payload.revised_inputs
            require_frozen_inputs(before)
            require_frozen_inputs(after)

            def linked(kind, inputs):
                return next(
                    (
                        a.payload
                        for a in reversed(payloads)
                        if a.artifact_type == kind
                        and getattr(a.payload, "inputs", None) == inputs
                    ),
                    None,
                )

            proposal = next(
                (
                    a.payload
                    for a in reversed(payloads)
                    if a.artifact_type == "revision_proposal"
                ),
                None,
            )
            require(proposal is not None)
            require(
                all(
                    h in seen
                    for h in (
                        before.policy_sha256,
                        after.policy_sha256,
                        before.contract_sha256,
                        before.suite_sha256,
                    )
                )
            )
            request = CompareRevisionRequest(
                baseline_policy=seen[before.policy_sha256].payload,
                revised_policy=seen[after.policy_sha256].payload,
                contract=seen[before.contract_sha256].payload,
                suite=seen[before.suite_sha256].payload,
                proposal=proposal,
                baseline_evaluation=linked("evaluation_report", before),
                revised_evaluation=linked("evaluation_report", after),
                baseline_findings=linked("finding_report", before),
                revised_findings=linked("finding_report", after),
            )
            validate_comparison(payload, request)
        seen[envelope.artifact_sha256] = envelope
        payloads.append(envelope)
    require(len(manifests) == 1)
    kinds = {a.artifact_type for a in record.artifacts}
    if record.stage in {
        "complete",
        "completed_no_findings",
        "completed_no_revision",
        "revision_rejected",
    }:
        require(
            {
                "policy_ir",
                "policy_contract",
                "scenario_suite",
                "evaluation_report",
                "finding_report",
                "metrics_report",
            }
            <= kinds
        )
    if record.stage == "complete":
        require("comparison_bundle" in kinds)
    for event in record.events:
        if event.artifact is not None:
            anchor = seen.get(event.artifact.artifact_sha256)
            require(
                anchor is not None
                and anchor.semantic_sha256 == event.artifact.semantic_sha256
                and anchor.artifact_type == event.artifact.artifact_type
            )
    return record
