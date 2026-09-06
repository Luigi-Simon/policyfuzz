"""Public workflow projections keep private run state behind a strict whitelist."""

from datetime import UTC, datetime, timedelta

import pytest

from app.core.artifacts import complete_payload_projection, make_artifact_envelope
from app.core.hashing import canonical_sha256
from app.domain import models
from app.workflow.types import StoredRun
from app.workflow.views import to_run_view

HASH = "a" * 64
OTHER_HASH = "b" * 64
NOW = datetime(2026, 9, 6, tzinfo=UTC)


def _manifest(*, mode: models.RunMode = "live") -> models.RunManifest:
    return models.RunManifest(
        manifest_id="manifest-1",
        run_id="run-1",
        engine_version="1.0",
        engine_sha256=HASH,
        prompt_hashes=(
            models.PromptHash(prompt_name="raw_prompt_sentinel", prompt_sha256=HASH),
        ),
        provider="provider_api_key_sentinel",
        model_identifier="private-model-sentinel",
        generation_config=models.GenerationConfig(),
        random_seed=7,
        started_at=NOW,
        mode=mode,
    )


def _record(
    *,
    stage: models.RunStage = "queued",
    artifacts: tuple[models.ArtifactEnvelope, ...] = (),
    events: tuple[models.RunEvent, ...] = (),
    error: models.PublicError | None = None,
    decision_at: datetime | None = None,
) -> models.RunRecord:
    return models.RunRecord(
        run_id="run-1",
        stage=stage,
        manifest=_manifest(),
        created_at=NOW,
        expires_at=NOW + timedelta(minutes=30),
        artifacts=artifacts,
        events=events,
        error=error,
        decision_at=decision_at,
    )


def _envelope(artifact_type: models.ArtifactType, payload: models.ArtifactPayload):
    return make_artifact_envelope(
        artifact_type=artifact_type,
        payload=payload,
        run_manifest_id="manifest-1",
    )


def _span(*, citation: str = "Visible policy citation") -> models.SourceSpan:
    return models.SourceSpan(
        page=1,
        start=0,
        end=len(citation),
        quote=citation,
        quote_sha256=HASH,
        section="1",
    )


def _policy(*, revised: bool = False, unsupported: bool = False) -> models.PolicyIR:
    provenance: models.RuleProvenance
    if revised:
        provenance = models.SessionRevisionProvenance(
            proposal_id="proposal-1",
            operation_index=0,
            confirmed_at=NOW,
            baseline_citation_ids=("citation-visible",),
        )
    else:
        provenance = models.TextRuleProvenance(
            citation_id="citation-visible", span=_span()
        )
    clauses = ()
    if unsupported:
        clauses = (
            models.UnsupportedClause(
                clause_id="private-clause-id",
                span=_span(citation="fulltext_sentinel_private_clause"),
                reason_code="unsupported_logic",
                affected_dimensions=frozenset({"claim_cap_minor"}),
            ),
        )
    return models.PolicyIR(
        policy_id="policy-revised" if revised else "policy-baseline",
        document_sha256=HASH,
        kind="structured_revision" if revised else "compiled_baseline",
        review_status="session_confirmed",
        rules=(
            models.Rule(
                rule_id="rule-meal",
                description="Meal claim cap",
                when=(),
                effects=(models.Effect(dimension="claim_cap_minor", value=5000),),
                provenance=provenance,
            ),
        ),
        unsupported_clauses=clauses,
    )


def _assertion(*, private: bool = False) -> models.Assertion:
    return models.Assertion(
        assertion_id="goldlabel_private" if private else "assertion-visible",
        target_kind="effect_value",
        dimension="claim_cap_minor",
        operator="eq",
        expected_value=9999 if private else 5000,
        origin="gold" if private else "session_confirmed",
        source_invariant_id=None if private else "invariant-visible",
        gold_label_id="goldlabel_private" if private else None,
    )


def _scenario(*, holdout: bool = False) -> models.Scenario:
    return models.Scenario(
        scenario_id="private-case-id" if holdout else "visible-case-id",
        category="boundary",
        origins=frozenset({"gold"} if holdout else {"session"}),
        facts=models.ScenarioFacts(
            employee_role="employee",
            expense_category="meal",
            amount_minor=5000,
            destination_type="domestic",
            booking_days_before=1,
            receipt_present=True,
            approval_roles_present=frozenset(),
            prior_same_day_category_spend_minor=0,
        ),
        target_rule_ids=("rule-meal",),
        assertions=(_assertion(private=holdout),),
        protected=holdout,
        partition="holdout" if holdout else "visible",
    )


def _suite(*, include_holdout: bool = True) -> models.ScenarioSuite:
    scenarios = (
        (_scenario(), _scenario(holdout=True)) if include_holdout else (_scenario(),)
    )
    suite = models.ScenarioSuite(
        suite_id="suite-1",
        content_sha256=HASH,
        seed=7,
        document_sha256=HASH,
        policy_contract_sha256=HASH,
        rule_set_sha256=HASH,
        engine_version="1.0",
        scenarios=scenarios,
        statistics=models.SuiteStatistics(
            generated_count=3,
            rejected_count=1,
            rejections=(
                models.ScenarioRejection(
                    candidate_id="private-reject-id", reason_code="invalid_facts"
                ),
            ),
        ),
    )

    return suite.model_copy(
        update={"content_sha256": canonical_sha256(complete_payload_projection(suite))}
    )


def _inputs(
    *, revised: bool = False, unsupported: bool = False, include_holdout: bool = True
) -> models.InputHashes:
    return models.InputHashes(
        policy_sha256=canonical_sha256(
            complete_payload_projection(
                _policy(revised=revised, unsupported=unsupported)
            )
        ),
        contract_sha256=HASH,
        suite_sha256=canonical_sha256(
            complete_payload_projection(_suite(include_holdout=include_holdout))
        ),
        engine_sha256=HASH,
        run_manifest_sha256=HASH,
    )


def _trace(*, holdout: bool = False, revised: bool = False) -> models.EvaluationTrace:
    scenario_id = "private-case-id" if holdout else "visible-case-id"
    if holdout:
        resolution = models.DimensionResult(
            dimension="claim_cap_minor",
            status="GAP" if revised else "CONFLICT",
            conflicting_values=() if revised else (5000, 9999),
        )
        provenance = (
            models.TextRuleProvenance(
                citation_id="private-citation",
                span=_span(citation="assertionexpectedanswer_private"),
            ),
        )
    elif revised:
        resolution = models.DimensionResult(
            dimension="claim_cap_minor", status="VALUE", value=4500
        )
        provenance = (
            models.SessionRevisionProvenance(
                proposal_id="proposal-1",
                operation_index=0,
                confirmed_at=NOW,
                baseline_citation_ids=("citation-visible",),
            ),
        )
    else:
        resolution = models.DimensionResult(
            dimension="claim_cap_minor", status="VALUE", value=5000
        )
        provenance = (
            models.TextRuleProvenance(citation_id="citation-visible", span=_span()),
        )
    return models.EvaluationTrace(
        scenario_id=scenario_id,
        fired_rule_ids=("rule-meal",),
        predicate_results=(),
        resolved_effects=(resolution,),
        compliance_values=(),
        source_citations=provenance,
        trace_sha256=OTHER_HASH if revised else HASH,
    )


def _evaluation(
    *, revised: bool = False, unknown: bool = False, unsupported: bool = False
):
    rows = [
        models.ScenarioEvaluation(
            scenario_id="visible-case-id",
            trace=_trace(revised=revised),
            verdict="UNSCORED",
        ),
        models.ScenarioEvaluation(
            scenario_id="private-case-id",
            trace=_trace(holdout=True, revised=revised),
            verdict="UNSCORED",
        ),
    ]
    if unknown:
        rows.append(
            models.ScenarioEvaluation(
                scenario_id="unknown-case-id",
                trace=_trace(revised=revised).model_copy(
                    update={"scenario_id": "unknown-case-id"}
                ),
                verdict="UNSCORED",
            )
        )
    return models.EvaluationReport(
        report_id="evaluation-revised" if revised else "evaluation-baseline",
        inputs=_inputs(revised=revised, unsupported=unsupported),
        engine_version="1.0",
        results=tuple(rows),
        coverage=models.CoverageSnapshot(
            total_rules=1,
            covered_rules=1,
            total_invariants=3,
            covered_invariants=2 if revised else 1,
            total_predicate_branches=2,
            covered_predicate_branches=1,
            status="pending",
        ),
    )


def _finding(
    finding_id: str,
    scenario_ids: tuple[str, ...],
    *,
    finding_type: models.FindingType = "structural_gap",
    evidence_level: models.EvidenceLevel = "mechanically_reproduced",
) -> models.Finding:
    return models.Finding(
        finding_id=finding_id,
        fingerprint_sha256=HASH,
        finding_type=finding_type,
        evidence_level=evidence_level,
        scenario_ids=scenario_ids,
        dimension="claim_cap_minor",
        traces=tuple(
            models.TraceRef(scenario_id=scenario_id, trace_sha256=HASH)
            for scenario_id in scenario_ids
        ),
    )


def _findings(*, include_holdout=True) -> models.FindingReport:
    return models.FindingReport(
        report_id="findings-1",
        inputs=_inputs(include_holdout=include_holdout),
        findings=(
            _finding("finding-visible", ("visible-case-id",)),
            _finding("finding-mixed", ("visible-case-id", "private-case-id")),
            _finding("finding-unknown", ("unknown-case-id",)),
            _finding(
                "finding-candidate",
                ("visible-case-id",),
                finding_type="potential_loophole",
                evidence_level="candidate",
            ),
        ),
    )


def _metrics(*, revised: bool = False, pass_percent: int | None = None):
    return models.MetricsReport(
        inputs=_inputs(revised=revised),
        scenario_count=2,
        effect_states=models.EffectStateCounts(VALUE=1, GAP=1),
        assertions=models.AssertionCounts(passed=1, inconclusive=1),
        unique_finding_count=2 if revised else 1,
        coverage=models.CoverageSnapshot(
            total_rules=1,
            covered_rules=1,
            total_invariants=3,
            covered_invariants=3,
            status="satisfied",
        ),
        assertion_pass_percent=pass_percent,
    )


def test_plain_run_record_projects_exact_frozen_shape_without_fake_metrics():
    view = to_run_view(_record())

    assert set(view.model_dump()) == set(models.RunView.model_fields)
    assert view.run_id == "run-1"
    assert view.mode == "live"
    assert view.allowed_actions == ("delete_run",)
    assert view.baseline_metrics is None
    assert view.comparison_metrics is None
    assert view.terminal_status is None
    assert view.pending_confirmation is None


def test_projection_redacts_private_payloads_and_withholds_mixed_findings():
    document = models.PolicyDocument(
        document_id="document-1",
        title="raw_prompt_title_sentinel",
        source_type="pasted_text",
        pages=(
            models.PolicyPage(
                page=1,
                text="fulltext_sentinel provider_api_key_sentinel",
                start=0,
                end=46,
            ),
        ),
        document_sha256=HASH,
    )
    artifacts = (
        _envelope("policy_document", document),
        _envelope("policy_ir", _policy(unsupported=True)),
        _envelope("scenario_suite", _suite()),
        _envelope("evaluation_report", _evaluation(unknown=True, unsupported=True)),
        _envelope("finding_report", _findings()),
    )
    stored = StoredRun(
        **_record(stage="awaiting_finding_review", artifacts=artifacts).model_dump(),
        pending_confirmation=models.FindingsConfirmation(
            finding_ids=(
                "finding-visible",
                "finding-mixed",
                "finding-unknown",
                "finding-candidate",
            )
        ),
    )

    view = to_run_view(stored)
    serialized = view.model_dump_json()

    assert tuple(item.finding_id for item in view.findings) == (
        "finding-visible",
        "finding-candidate",
    )
    assert view.findings[0].summary == "Policy behavior has a structural gap."
    assert view.findings[0].witness_count == 1
    assert view.pending_confirmation == models.FindingsConfirmation(
        finding_ids=("finding-visible",)
    )
    assert tuple(trace.scenario_id for trace in view.traces) == ("visible-case-id",)
    assert view.traces[0].phase == "baseline"
    assert view.unsupported_clauses == ()
    assert view.rejections == ()
    assert view.holdout_evidence == models.HoldoutEvidenceSummary(
        scenario_count=1,
        unsupported_clause_count=1,
        rejected_rule_count=0,
        rejected_scenario_count=1,
        baseline_effect_states=models.EffectStateCounts(CONFLICT=1),
    )
    for forbidden in (
        "raw_prompt",
        "provider_api_key",
        "private-model-sentinel",
        "fulltext_sentinel",
        "private-case-id",
        "private-reject-id",
        "goldlabel_private",
        "assertionexpectedanswer_private",
        '"facts"',
        '"assertions"',
        '"expected_value"',
    ):
        assert forbidden not in serialized


def test_projection_maps_revised_traces_and_authoritative_comparison_metrics():
    baseline_metrics = _metrics()
    revised_metrics = _metrics(revised=True, pass_percent=50)
    baseline_inputs = _inputs()
    revised_inputs = _inputs(revised=True)
    regression = models.RegressionReport(
        report_id="regression-1",
        baseline_inputs=baseline_inputs,
        revised_inputs=revised_inputs,
        baseline_effect_states=models.EffectStateCounts(VALUE=1, CONFLICT=1),
        revised_effect_states=models.EffectStateCounts(VALUE=1, GAP=1),
        assertion_transition_counts=models.AssertionTransitionCounts(
            fail_to_pass=1, pass_to_fail=1
        ),
        assertion_transitions=(),
    )
    acceptance = models.PatchAcceptanceReport(
        baseline_inputs=baseline_inputs,
        revised_inputs=revised_inputs,
        suite_hash_matches=True,
        all_target_findings_fixed=True,
        zero_new_failures_outside_targets=False,
        zero_protected_regressions=False,
        no_increase_in_gap_conflict_inconclusive_or_error=True,
        unrelated_rules_unchanged=True,
        holdout_not_worse=True,
        patch_accepted=False,
        counts=models.PatchAcceptanceCounts(
            new_failures_outside_targets=1, protected_regressions=1
        ),
    )
    comparison = models.ComparisonBundle(
        baseline_inputs=baseline_inputs,
        revised_inputs=revised_inputs,
        regression=regression,
        acceptance=acceptance,
        baseline_metrics=baseline_metrics,
        revised_metrics=revised_metrics,
    )
    artifacts = (
        _envelope("policy_ir", _policy()),
        _envelope("scenario_suite", _suite()),
        _envelope("evaluation_report", _evaluation()),
        _envelope("metrics_report", baseline_metrics),
        _envelope("policy_ir", _policy(revised=True)),
        _envelope("evaluation_report", _evaluation(revised=True)),
        _envelope("comparison_bundle", comparison),
    )

    view = to_run_view(_record(stage="complete", artifacts=artifacts, decision_at=NOW))

    assert tuple((trace.scenario_id, trace.phase) for trace in view.traces) == (
        ("visible-case-id", "baseline"),
        ("visible-case-id", "revised"),
    )
    assert view.traces[1].source_citations == (_span(),)
    assert view.coverage.covered_invariants == 2
    assert view.coverage.scenario_count == 2
    assert view.baseline_metrics is not None
    assert view.baseline_metrics.assertion_pass_percent is None
    assert view.comparison_metrics is not None
    assert view.comparison_metrics.revised.assertion_pass_percent == 50
    assert view.comparison_metrics.assertion_transition_counts.fail_to_pass == 1
    assert view.comparison_metrics.acceptance == acceptance
    assert view.comparison_metrics.patch_accepted is False
    assert view.comparison_metrics.protected_regressions == 1
    assert view.comparison_metrics.new_failures_outside_targets == 1
    assert view.holdout_evidence is not None
    assert view.holdout_evidence.baseline_effect_states.CONFLICT == 1
    assert view.holdout_evidence.revised_effect_states == models.EffectStateCounts(
        GAP=1
    )
    assert view.terminal_status == "complete"
    assert view.decision_at == NOW


def test_projection_uses_safe_event_and_error_text_and_keeps_completed_artifacts():
    policy = _envelope("policy_ir", _policy())
    private_event_artifact = _envelope(
        "benchmark_score",
        models.BenchmarkScore(
            benchmark_id="private-benchmark-id",
            inputs=_inputs(),
            true_positives=1,
            false_positives=0,
            false_negatives=0,
        ),
    )
    events = (
        models.RunEvent(
            timestamp=NOW,
            stage="baseline_execution",
            action_summary="timing=51ms provider_api_key_sentinel raw_prompt",
            artifact=models.ArtifactRef(
                artifact_type=policy.artifact_type,
                artifact_sha256=policy.artifact_sha256,
                semantic_sha256=policy.semantic_sha256,
            ),
        ),
        models.RunEvent(
            timestamp=NOW + timedelta(seconds=1),
            stage="failed",
            action_summary="private exception fulltext_sentinel",
            artifact=models.ArtifactRef(
                artifact_type=private_event_artifact.artifact_type,
                artifact_sha256=private_event_artifact.artifact_sha256,
                semantic_sha256=private_event_artifact.semantic_sha256,
            ),
            error_id="safe-error-id",
        ),
    )
    error = models.PublicError(
        code="PROVIDER_UNAVAILABLE",
        message="provider stack trace provider_api_key_sentinel",
        error_id="safe-error-id",
        retryable=True,
    )

    view = to_run_view(
        _record(
            stage="failed",
            artifacts=(policy, private_event_artifact),
            events=events,
            error=error,
        )
    )
    serialized = view.model_dump_json()

    assert tuple(item.artifact.artifact_type for item in view.artifacts) == (
        "policy_ir",
    )
    assert view.events[0].action_summary == "Baseline execution started."
    assert view.events[1].action_summary == "Run failed."
    assert view.events[0].timestamp == NOW
    assert view.events[1].artifact is None
    assert view.error == models.PublicError(
        code="PROVIDER_UNAVAILABLE",
        message="The model provider is temporarily unavailable.",
        error_id="safe-error-id",
        retryable=True,
    )
    assert view.terminal_status == "failed"
    assert "provider_api_key_sentinel" not in serialized
    assert "fulltext_sentinel" not in serialized
    assert "private-benchmark-id" not in serialized


def test_event_with_unstored_public_artifact_reference_is_withheld():
    event = models.RunEvent(
        timestamp=NOW,
        stage="analyzing",
        action_summary="safe-looking but untrusted",
        artifact=models.ArtifactRef(
            artifact_type="finding_report",
            artifact_sha256=HASH,
            semantic_sha256=OTHER_HASH,
        ),
    )

    view = to_run_view(_record(stage="analyzing", events=(event,)))

    assert view.events[0].artifact is None


def test_pending_confirmation_only_appears_at_its_corresponding_stage():
    pending = models.FindingsConfirmation(finding_ids=("finding-visible",))
    artifacts = (
        _envelope("scenario_suite", _suite(include_holdout=False)),
        _envelope("finding_report", _findings(include_holdout=False)),
    )
    matching = StoredRun(
        **_record(stage="awaiting_finding_review", artifacts=artifacts).model_dump(),
        pending_confirmation=pending,
    )
    wrong_stage = matching.model_copy(update={"stage": "drafting_revision"})

    assert to_run_view(matching).pending_confirmation == pending
    assert to_run_view(wrong_stage).pending_confirmation is None


def test_second_evaluation_is_not_labeled_revised_without_a_structured_revision():
    artifacts = (
        _envelope("policy_ir", _policy()),
        _envelope("scenario_suite", _suite()),
        _envelope("evaluation_report", _evaluation()),
        _envelope("evaluation_report", _evaluation(revised=True)),
    )

    view = to_run_view(_record(stage="baseline_execution", artifacts=artifacts))

    assert tuple(trace.phase for trace in view.traces) == ("baseline",)
    assert view.holdout_evidence is not None
    assert view.holdout_evidence.revised_effect_states is None


def test_revision_confirmation_withholds_candidate_finding_targets():
    operation = models.AddRuleOperation(
        rule_id="rule-new",
        finding_ids=("finding-candidate",),
        rule=models.RevisionRuleDraft(
            description="Candidate change",
            when=(
                models.Predicate(field="expense_category", operator="eq", value="meal"),
            ),
            effects=(models.Effect(dimension="claim_cap_minor", value=4500),),
        ),
    )
    pending = models.RevisionConfirmation(
        proposal_id="proposal-1",
        operations=(models.RevisionOperationSummary(operation=operation),),
        draft_policy_wording="Candidate wording",
    )
    artifacts = (
        _envelope("policy_ir", _policy()),
        _envelope("scenario_suite", _suite(include_holdout=False)),
        _envelope("finding_report", _findings(include_holdout=False)),
    )
    stored = StoredRun(
        **_record(
            stage="awaiting_revision_confirmation", artifacts=artifacts
        ).model_dump(),
        pending_confirmation=pending,
    )

    assert to_run_view(stored).pending_confirmation is None


@pytest.mark.parametrize("citation_id", ["unknown-citation", "citation"])
def test_plain_record_trace_withholds_unknown_or_substituted_citation(citation_id):
    from hashlib import sha256

    from tests.workflow.coordinator_fixtures import cached_record, digest

    record = cached_record()
    sentinel = "SYNTHETIC_HOLDOUT_CITATION_SENTINEL"
    span = models.SourceSpan(
        page=1,
        start=0,
        end=len(sentinel),
        quote=sentinel,
        quote_sha256=sha256(sentinel.encode()).hexdigest(),
    )
    provenance = models.TextRuleProvenance(citation_id=citation_id, span=span)
    artifacts = []
    for envelope in record.artifacts:
        if envelope.artifact_type == "evaluation_report":
            report = envelope.payload
            first = report.results[0]
            trace = first.trace.model_copy(update={"source_citations": (provenance,)})
            trace = trace.model_copy(update={"trace_sha256": digest(trace)})
            report = report.model_copy(
                update={
                    "results": (first.model_copy(update={"trace": trace}),)
                    + report.results[1:]
                }
            )
            envelope = make_artifact_envelope(
                artifact_type="evaluation_report",
                payload=report,
                run_manifest_id=record.manifest.manifest_id,
            )
        artifacts.append(envelope)
    view = to_run_view(record.model_copy(update={"artifacts": tuple(artifacts)}))
    assert sentinel not in view.model_dump_json()
    assert all(not t.source_citations for t in view.traces)


def test_plain_record_appended_suite_cannot_reveal_prior_holdout_evidence():
    from tests.workflow.coordinator_fixtures import cached_holdout_record

    record = cached_holdout_record(append_visible_suite=True)
    view = to_run_view(record)
    serialized = view.model_dump_json()
    assert view.traces == ()
    assert "candidate-0" not in serialized
    assert "candidate-1" not in serialized
    assert "candidate-2" not in serialized
    assert "Meals allowed." not in serialized


def test_coverage_uses_latest_evaluation_after_earlier_targeting_snapshot():
    artifacts = (
        _envelope("policy_ir", _policy()),
        _envelope("scenario_suite", _suite()),
        _envelope(
            "coverage_snapshot",
            models.CoverageSnapshot(total_rules=1, total_invariants=3),
        ),
        _envelope("evaluation_report", _evaluation()),
        _envelope("policy_ir", _policy(revised=True)),
        _envelope("evaluation_report", _evaluation(revised=True)),
    )
    view = to_run_view(_record(stage="complete", artifacts=artifacts))
    assert (
        view.coverage.covered_invariants
        == _evaluation(revised=True).coverage.covered_invariants
    )


def test_plain_record_report_cannot_borrow_visibility_from_unbound_suite():
    from tests.workflow.coordinator_fixtures import cached_holdout_record

    record = cached_holdout_record(append_visible_suite=True)
    # Keep only the new visible suite; report inputs still name the removed holdout suite.
    artifacts = tuple(
        a
        for a in record.artifacts
        if a.artifact_type != "scenario_suite"
        or a.payload.suite_id == "appended-visible-suite"
    )
    view = to_run_view(record.model_copy(update={"artifacts": artifacts}))
    assert view.traces == ()
    assert "candidate-0" not in view.model_dump_json()
    assert "Meals allowed." not in view.model_dump_json()


def test_coverage_uses_latest_standalone_snapshot_after_evaluation():
    latest = models.CoverageSnapshot(
        total_rules=1,
        covered_rules=1,
        total_invariants=3,
        covered_invariants=3,
        status="satisfied",
    )
    artifacts = (
        _envelope("scenario_suite", _suite()),
        _envelope("evaluation_report", _evaluation()),
        _envelope("coverage_snapshot", latest),
    )
    view = to_run_view(_record(stage="complete", artifacts=artifacts))
    assert view.coverage.covered_invariants == latest.covered_invariants


@pytest.mark.parametrize("replace_suite", [False, True])
def test_plain_record_private_findings_cannot_borrow_unbound_suite_visibility(
    replace_suite,
):
    from tests.workflow.coordinator_fixtures import cached_holdout_record

    record = cached_holdout_record(append_visible_suite=True)
    evaluation = next(
        a.payload for a in record.artifacts if a.artifact_type == "evaluation_report"
    )
    row = evaluation.results[0]
    finding = models.Finding(
        finding_id="private-finding-sentinel",
        fingerprint_sha256=HASH,
        finding_type="structural_gap",
        evidence_level="mechanically_reproduced",
        scenario_ids=(row.scenario_id,),
        dimension="eligibility",
        traces=(
            models.TraceRef(
                scenario_id=row.scenario_id, trace_sha256=row.trace.trace_sha256
            ),
        ),
    )
    findings = models.FindingReport(
        report_id="private-findings", inputs=evaluation.inputs, findings=(finding,)
    )
    artifacts = tuple(
        a
        for a in record.artifacts
        if not replace_suite
        or a.artifact_type != "scenario_suite"
        or a.payload.suite_id == "appended-visible-suite"
    )
    artifacts += (
        make_artifact_envelope(
            artifact_type="finding_report",
            payload=findings,
            run_manifest_id=record.manifest.manifest_id,
        ),
    )
    stored = StoredRun(
        **record.model_copy(
            update={"stage": "awaiting_finding_review", "artifacts": artifacts}
        ).model_dump(),
        pending_confirmation=models.FindingsConfirmation(
            finding_ids=(finding.finding_id,)
        ),
    )
    view = to_run_view(stored)
    assert view.findings == ()
    assert not view.pending_confirmation or not view.pending_confirmation.finding_ids
    assert "private-finding-sentinel" not in view.model_dump_json()
    assert view.artifacts[-1].item_count == 0
