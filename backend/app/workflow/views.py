"""Display-safe projections of private workflow records."""

from collections import Counter
from collections.abc import Iterable

from app.core.artifacts import complete_payload_projection, validate_artifact_envelope
from app.core.hashing import canonical_sha256
from app.domain.models import (
    ArtifactEnvelope,
    ArtifactRef,
    ArtifactSummary,
    ComparisonBundle,
    ContractConfirmation,
    CoverageCounters,
    CoverageSnapshot,
    EffectStateCounts,
    EvaluationReport,
    Finding,
    FindingReport,
    FindingsConfirmation,
    FindingSummary,
    HoldoutEvidenceSummary,
    MetricsReport,
    PatchAcceptanceReport,
    PolicyContract,
    PolicyIR,
    PublicComparisonMetrics,
    PublicError,
    PublicMetrics,
    RegressionReport,
    RejectionEvidence,
    RevisionConfirmation,
    RevisionOperationSummary,
    RevisionProposal,
    Rule,
    RuleSummary,
    RunEvent,
    RunRecord,
    RunView,
    ScenarioSuite,
    SessionRevisionProvenance,
    SourceSpan,
    TextRuleProvenance,
    UnsupportedClauseEvidence,
    VisibleTraceSummary,
)

from .state_machine import allowed_actions, stage_summary

_PRIVATE_ARTIFACT_TYPES = frozenset({"benchmark_manifest", "benchmark_score"})
_TERMINAL_STAGES = frozenset(
    {
        "complete",
        "completed_no_findings",
        "completed_no_revision",
        "contract_rejected",
        "revision_rejected",
        "coverage_limit_exceeded",
        "failed",
    }
)
_ARTIFACT_TITLES = {
    "policy_document": "Policy source",
    "policy_ir": "Compiled policy",
    "policy_contract": "Confirmed policy contract",
    "scenario_suite": "Scenario suite",
    "evaluation_report": "Evaluation report",
    "finding_report": "Finding report",
    "revision_proposal": "Structured revision proposal",
    "regression_report": "Regression report",
    "patch_acceptance_report": "Patch acceptance report",
    "comparison_bundle": "Revision comparison",
    "metrics_report": "Metrics report",
    "coverage_snapshot": "Coverage snapshot",
    "run_manifest": "Run configuration",
}
_ERROR_MESSAGES = {
    "INVALID_INPUT": "The request input is invalid.",
    "INVALID_STATE": "The run is not ready for that action.",
    "INVALID_POLICY": "The policy could not be validated.",
    "INVALID_CITATION": "A policy citation could not be validated.",
    "MALFORMED_MODEL_OUTPUT": "A generated result could not be validated.",
    "PROVIDER_UNAVAILABLE": "The model provider is temporarily unavailable.",
    "COVERAGE_LIMIT_EXCEEDED": "Required coverage was not reached within the limit.",
    "HASH_MISMATCH": "Stored artifact verification failed.",
    "REVISION_INVALID": "The proposed revision could not be applied.",
    "PROSE_COMPILE_MISMATCH": "The revised wording does not match the structured policy.",
    "RUN_NOT_FOUND": "The run was not found.",
    "INTERNAL_ERROR": "The run could not be completed.",
}
_FINDING_SUMMARIES = {
    "structural_gap": "Policy behavior has a structural gap.",
    "conflict": "Policy rules produce conflicting outcomes.",
    "intent_breach": "Observed behavior breaches a confirmed invariant.",
    "regression": "A previously passing assertion regressed.",
    "unsupported_clause": "A policy clause cannot be evaluated deterministically.",
    "potential_loophole": "A possible loophole requires reviewer attention.",
}


def _payloads(record: RunRecord, payload_type: type):
    return tuple(
        envelope.payload
        for envelope in record.artifacts
        if isinstance(envelope.payload, payload_type)
    )


def _artifact_ref(envelope: ArtifactEnvelope) -> ArtifactRef:
    return ArtifactRef(
        artifact_type=envelope.artifact_type,
        artifact_sha256=envelope.artifact_sha256,
        semantic_sha256=envelope.semantic_sha256,
    )


def _public_metrics(report: MetricsReport) -> PublicMetrics:
    return PublicMetrics(
        scenario_count=report.scenario_count,
        effect_states=report.effect_states,
        assertions=report.assertions,
        unique_finding_count=report.unique_finding_count,
        assertion_pass_percent=report.assertion_pass_percent,
    )


def _public_comparison(bundle: ComparisonBundle) -> PublicComparisonMetrics:
    acceptance = bundle.acceptance
    return PublicComparisonMetrics(
        baseline=_public_metrics(bundle.baseline_metrics),
        revised=_public_metrics(bundle.revised_metrics),
        assertion_transition_counts=bundle.regression.assertion_transition_counts,
        acceptance=acceptance,
        patch_accepted=acceptance.patch_accepted,
        protected_regressions=acceptance.counts.protected_regressions,
        new_failures_outside_targets=acceptance.counts.new_failures_outside_targets,
    )


def _coverage(record: RunRecord, suite: ScenarioSuite | None) -> CoverageCounters:
    snapshot = None
    for envelope in reversed(record.artifacts):
        if isinstance(envelope.payload, CoverageSnapshot):
            snapshot = envelope.payload
            break
        if isinstance(envelope.payload, EvaluationReport):
            snapshot = envelope.payload.coverage
            break
    return CoverageCounters(
        total_rules=snapshot.total_rules if snapshot else 0,
        covered_rules=snapshot.covered_rules if snapshot else 0,
        total_invariants=snapshot.total_invariants if snapshot else 0,
        covered_invariants=snapshot.covered_invariants if snapshot else 0,
        total_predicate_branches=snapshot.total_predicate_branches if snapshot else 0,
        covered_predicate_branches=snapshot.covered_predicate_branches
        if snapshot
        else 0,
        scenario_count=len(suite.scenarios) if suite else 0,
    )


def _visible_findings(
    report: FindingReport | None, visible_scenario_ids: frozenset[str]
) -> tuple[tuple[Finding, FindingSummary], ...]:
    if report is None:
        return ()
    projected = []
    for finding in report.findings:
        witnesses = frozenset(finding.scenario_ids)
        if not witnesses or not witnesses <= visible_scenario_ids:
            continue
        projected.append(
            (
                finding,
                FindingSummary(
                    finding_id=finding.finding_id,
                    finding_type=finding.finding_type,
                    dimension=finding.dimension,
                    summary=_FINDING_SUMMARIES[finding.finding_type],
                    severity=finding.severity,
                    review_status=finding.review_status,
                    witness_count=len(witnesses),
                ),
            )
        )
    return tuple(projected)


def _baseline_citations(policy: PolicyIR | None) -> dict[str, TextRuleProvenance]:
    if policy is None:
        return {}
    return {
        rule.provenance.citation_id: rule.provenance
        for rule in policy.rules
        if isinstance(rule.provenance, TextRuleProvenance)
    }


def _trace_citations(
    provenances: Iterable[TextRuleProvenance | SessionRevisionProvenance],
    baseline_citations: dict[str, TextRuleProvenance],
    evaluated_policy: PolicyIR,
) -> tuple[SourceSpan, ...]:
    result = []
    permitted = tuple(rule.provenance for rule in evaluated_policy.rules)
    for provenance in provenances:
        if provenance not in permitted:
            continue
        if isinstance(provenance, TextRuleProvenance):
            canonical = baseline_citations.get(provenance.citation_id)
            if canonical == provenance:
                result.append(canonical.span)
        elif all(
            citation_id in baseline_citations
            for citation_id in provenance.baseline_citation_ids
        ):
            result.extend(
                baseline_citations[citation_id].span
                for citation_id in provenance.baseline_citation_ids
            )
    return tuple(dict.fromkeys(result))


def _visible_traces(
    record: RunRecord,
    evaluations: tuple[EvaluationReport, ...],
    visible_scenario_ids: frozenset[str],
    baseline_citations: dict[str, TextRuleProvenance],
) -> tuple[VisibleTraceSummary, ...]:
    result = []
    for phase, report in zip(("baseline", "revised"), evaluations, strict=False):
        policy = _evaluation_policy(record, report)
        if policy is None:
            continue
        for evaluation in report.results:
            if evaluation.scenario_id not in visible_scenario_ids:
                continue
            trace = evaluation.trace
            result.append(
                VisibleTraceSummary(
                    scenario_id=evaluation.scenario_id,
                    phase=phase,
                    trace_sha256=trace.trace_sha256,
                    fired_rule_ids=trace.fired_rule_ids,
                    predicate_results=trace.predicate_results,
                    resolved_effects=trace.resolved_effects,
                    compliance_values=trace.compliance_values,
                    source_citations=_trace_citations(
                        trace.source_citations, baseline_citations, policy
                    ),
                )
            )
    return tuple(result)


def _digest(payload) -> str:
    return canonical_sha256(complete_payload_projection(payload))


def _frozen_suite(record: RunRecord) -> ScenarioSuite | None:
    """A conflicting or unverifiable suite establishes no public partition."""
    envelopes = tuple(
        a for a in record.artifacts if isinstance(a.payload, ScenarioSuite)
    )
    if len(envelopes) != 1:
        return None
    try:
        envelope = validate_artifact_envelope(envelopes[0])
    except (ValueError, TypeError):
        return None
    suite = envelope.payload
    return suite if suite.content_sha256 == _digest(suite) else None


def _bound_to_suite(report, suite: ScenarioSuite | None) -> bool:
    return suite is not None and report.inputs.suite_sha256 == _digest(suite)


def _evaluation_policy(record: RunRecord, report: EvaluationReport) -> PolicyIR | None:
    policies = tuple(
        a.payload
        for a in record.artifacts
        if isinstance(a.payload, PolicyIR)
        and _digest(a.payload) == report.inputs.policy_sha256
    )
    return policies[0] if policies else None


def _phase_evaluations(record: RunRecord) -> tuple[EvaluationReport, ...]:
    """Resolve baseline first, then the first evaluation after structured revision."""
    baseline = None
    revised = None
    saw_revision = False
    for envelope in record.artifacts:
        payload = envelope.payload
        if isinstance(payload, PolicyIR) and payload.kind == "structured_revision":
            saw_revision = True
        elif isinstance(payload, EvaluationReport):
            if baseline is None:
                baseline = payload
            elif saw_revision and revised is None:
                revised = payload
    return tuple(report for report in (baseline, revised) if report is not None)


def _effect_counts(
    report: EvaluationReport, holdout_scenario_ids: frozenset[str]
) -> EffectStateCounts:
    counts: Counter[str] = Counter()
    for evaluation in report.results:
        if evaluation.scenario_id in holdout_scenario_ids:
            counts.update(result.status for result in evaluation.trace.resolved_effects)
    return EffectStateCounts(**counts)


def _visible_rejections(
    suite: ScenarioSuite | None, visible_scenario_ids: frozenset[str]
) -> tuple[RejectionEvidence, ...]:
    if suite is None:
        return ()
    return tuple(
        RejectionEvidence(
            item_kind="scenario",
            item_id=rejection.candidate_id,
            source_spans=(),
            reason_code=rejection.reason_code,
            disposition=(
                "merged_duplicate"
                if rejection.reason_code == "duplicate"
                else "excluded"
            ),
        )
        for rejection in suite.statistics.rejections
        if rejection.candidate_id in visible_scenario_ids
    )


def _rule_summary(rule: Rule) -> RuleSummary | None:
    if not isinstance(rule.provenance, TextRuleProvenance):
        return None
    return RuleSummary(
        rule_id=rule.rule_id,
        revision=rule.revision,
        description=rule.description,
        when=rule.when,
        effects=rule.effects,
        overrides=rule.overrides,
        citations=(rule.provenance,),
        confidence_percent=rule.confidence_percent,
    )


def _contract_confirmation(
    pending: ContractConfirmation, baseline_envelope: ArtifactEnvelope | None
) -> ContractConfirmation | None:
    if baseline_envelope is None or not isinstance(baseline_envelope.payload, PolicyIR):
        return None
    policy = baseline_envelope.payload
    summaries = tuple(_rule_summary(rule) for rule in policy.rules)
    if any(summary is None for summary in summaries):
        return None
    return ContractConfirmation(
        baseline_policy_id=policy.policy_id,
        baseline_policy_sha256=baseline_envelope.artifact_sha256,
        document_sha256=policy.document_sha256,
        rules=tuple(summary for summary in summaries if summary is not None),
        invariants=pending.invariants,
        required_dimensions=pending.required_dimensions,
    )


def _revision_confirmation(
    pending: RevisionConfirmation,
    visible_finding_ids: frozenset[str],
    baseline_policy: PolicyIR | None,
) -> RevisionConfirmation | None:
    baseline_rules = (
        {rule.rule_id: rule for rule in baseline_policy.rules}
        if baseline_policy
        else {}
    )
    operations = []
    for summary in pending.operations:
        if not frozenset(summary.operation.finding_ids) <= visible_finding_ids:
            return None
        if summary.operation.kind == "add_rule":
            before = None
        else:
            rule = baseline_rules.get(summary.operation.rule_id)
            before = _rule_summary(rule) if rule else None
            if before is None:
                return None
        operations.append(
            RevisionOperationSummary(operation=summary.operation, before=before)
        )
    return RevisionConfirmation(
        proposal_id=pending.proposal_id,
        operations=tuple(operations),
        draft_policy_wording=pending.draft_policy_wording,
    )


def _pending_confirmation(
    record: RunRecord,
    *,
    projected_findings: tuple[tuple[Finding, FindingSummary], ...],
    baseline_policy: PolicyIR | None,
    baseline_envelope: ArtifactEnvelope | None,
):
    pending = getattr(record, "pending_confirmation", None)
    if record.stage == "awaiting_contract" and isinstance(
        pending, ContractConfirmation
    ):
        return _contract_confirmation(pending, baseline_envelope)
    revision_target_ids = frozenset(
        finding.finding_id
        for finding, _ in projected_findings
        if finding.evidence_level != "candidate" and finding.review_status == "accepted"
    )
    selectable_ids = frozenset(
        finding.finding_id
        for finding, _ in projected_findings
        if finding.evidence_level != "candidate"
    )
    if record.stage == "awaiting_finding_review" and isinstance(
        pending, FindingsConfirmation
    ):
        return FindingsConfirmation(
            finding_ids=tuple(
                finding_id
                for finding_id in pending.finding_ids
                if finding_id in selectable_ids
            )
        )
    if record.stage == "awaiting_revision_confirmation" and isinstance(
        pending, RevisionConfirmation
    ):
        return _revision_confirmation(pending, revision_target_ids, baseline_policy)
    return None


def _artifact_count(
    envelope: ArtifactEnvelope, visible_scenario_ids: frozenset[str]
) -> int | None:
    payload = envelope.payload
    if isinstance(payload, PolicyIR):
        return len(payload.rules)
    if isinstance(payload, PolicyContract):
        return len(payload.invariants)
    if isinstance(payload, ScenarioSuite):
        return len(payload.scenarios)
    if isinstance(payload, EvaluationReport):
        return len(payload.results)
    if isinstance(payload, FindingReport):
        return len(_visible_findings(payload, visible_scenario_ids))
    if isinstance(payload, RevisionProposal):
        return len(payload.operations)
    if isinstance(payload, RegressionReport):
        return len(payload.assertion_transitions)
    if isinstance(payload, (PatchAcceptanceReport, ComparisonBundle)):
        return 7
    if isinstance(payload, MetricsReport):
        return payload.scenario_count
    return None


def _artifact_summaries(
    record: RunRecord, visible_scenario_ids: frozenset[str], suite: ScenarioSuite | None
) -> tuple[ArtifactSummary, ...]:
    return tuple(
        ArtifactSummary(
            artifact=_artifact_ref(envelope),
            title=_ARTIFACT_TITLES[envelope.artifact_type],
            item_count=_artifact_count(
                envelope,
                visible_scenario_ids
                if not isinstance(envelope.payload, FindingReport)
                or _bound_to_suite(envelope.payload, suite)
                else frozenset(),
            ),
        )
        for envelope in record.artifacts
        if envelope.artifact_type not in _PRIVATE_ARTIFACT_TYPES
    )


def _events(record: RunRecord) -> tuple[RunEvent, ...]:
    public_artifact_refs = frozenset(
        _artifact_ref(envelope)
        for envelope in record.artifacts
        if envelope.artifact_type not in _PRIVATE_ARTIFACT_TYPES
    )
    return tuple(
        RunEvent(
            timestamp=event.timestamp,
            stage=event.stage,
            action_summary=stage_summary(event.stage),
            artifact=(
                event.artifact
                if event.artifact is not None and event.artifact in public_artifact_refs
                else None
            ),
            error_id=event.error_id,
        )
        for event in record.events
    )


def _public_error(error: PublicError | None) -> PublicError | None:
    if error is None:
        return None
    return PublicError(
        code=error.code,
        message=_ERROR_MESSAGES[error.code],
        error_id=error.error_id,
        retryable=error.retryable,
    )


def to_run_view(record: RunRecord) -> RunView:
    """Project a stored record into the frozen public run contract."""
    policies = _payloads(record, PolicyIR)
    baseline_envelopes = tuple(
        envelope
        for envelope in record.artifacts
        if isinstance(envelope.payload, PolicyIR)
        and envelope.payload.kind == "compiled_baseline"
    )
    baseline_envelope = baseline_envelopes[0] if baseline_envelopes else None
    baseline_policy = baseline_envelope.payload if baseline_envelope else None
    suites = _payloads(record, ScenarioSuite)
    suite = _frozen_suite(record)
    visible_scenario_ids = (
        frozenset(
            scenario.scenario_id
            for scenario in suite.scenarios
            if scenario.partition == "visible"
        )
        if suite
        else frozenset()
    )
    holdout_scenario_ids = (
        frozenset(
            scenario.scenario_id
            for scenario in suite.scenarios
            if scenario.partition == "holdout"
        )
        if suite
        else frozenset()
    )
    phase_evaluations = _phase_evaluations(record)
    if any(
        not _bound_to_suite(report, suite) or _evaluation_policy(record, report) is None
        for report in phase_evaluations
    ):
        phase_evaluations = ()
    finding_reports = _payloads(record, FindingReport)
    finding_report = finding_reports[-1] if finding_reports else None
    projected_findings = _visible_findings(
        finding_report
        if finding_report is not None and _bound_to_suite(finding_report, suite)
        else None,
        visible_scenario_ids,
    )
    metrics = _payloads(record, MetricsReport)
    comparisons = _payloads(record, ComparisonBundle)
    comparison = comparisons[-1] if comparisons else None
    baseline_metrics = (
        metrics[0] if metrics else comparison.baseline_metrics if comparison else None
    )
    has_private_artifact = any(
        envelope.artifact_type in _PRIVATE_ARTIFACT_TYPES
        for envelope in record.artifacts
    )
    policy = policies[-1] if policies else None
    clauses = ()
    if (
        policy is not None
        and not holdout_scenario_ids
        and not has_private_artifact
        and (not suites or suite is not None)
    ):
        clauses = tuple(
            UnsupportedClauseEvidence(
                clause_id=clause.clause_id,
                span=clause.span,
                reason_code=clause.reason_code,
                affected_dimensions=clause.affected_dimensions,
                when_hint=clause.when_hint,
                disposition=(
                    "pending_review"
                    if clause.review_status == "provisional"
                    else "retained_inconclusive"
                ),
            )
            for clause in policy.unsupported_clauses
        )
    holdout_evidence = None
    if holdout_scenario_ids:
        unknown_rejections = sum(
            rejection.candidate_id not in visible_scenario_ids
            for rejection in suite.statistics.rejections
        )
        holdout_evidence = HoldoutEvidenceSummary(
            scenario_count=len(holdout_scenario_ids),
            unsupported_clause_count=len(policy.unsupported_clauses) if policy else 0,
            rejected_rule_count=0,
            rejected_scenario_count=unknown_rejections,
            baseline_effect_states=(
                _effect_counts(phase_evaluations[0], holdout_scenario_ids)
                if phase_evaluations
                else EffectStateCounts()
            ),
            revised_effect_states=(
                _effect_counts(phase_evaluations[1], holdout_scenario_ids)
                if len(phase_evaluations) > 1
                else None
            ),
        )
    return RunView(
        run_id=record.run_id,
        stage=record.stage,
        allowed_actions=allowed_actions(record.stage),
        mode=record.manifest.mode,
        events=_events(record),
        artifacts=_artifact_summaries(record, visible_scenario_ids, suite),
        pending_confirmation=_pending_confirmation(
            record,
            projected_findings=projected_findings,
            baseline_policy=baseline_policy,
            baseline_envelope=baseline_envelope,
        ),
        coverage=_coverage(record, suite),
        findings=tuple(summary for _, summary in projected_findings),
        unsupported_clauses=clauses,
        rejections=_visible_rejections(suite, visible_scenario_ids),
        traces=_visible_traces(
            record,
            phase_evaluations,
            visible_scenario_ids,
            _baseline_citations(baseline_policy),
        ),
        holdout_evidence=holdout_evidence,
        baseline_metrics=_public_metrics(baseline_metrics)
        if baseline_metrics
        else None,
        comparison_metrics=_public_comparison(comparison) if comparison else None,
        terminal_status=record.stage if record.stage in _TERMINAL_STAGES else None,
        error=_public_error(record.error),
        decision_at=record.decision_at,
    )
