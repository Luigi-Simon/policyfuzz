import pytest
from pydantic import BaseModel, ValidationError

import app.domain.models as models  # noqa: PLR0402 - public contract import boundary
from app.domain.models import ArtifactEnvelope, GenerationConfig, RunView

from .factories import HASH, make_policy

REQUIRED = [
    "RuleDraft",
    "PolicyExtraction",
    "CompilePolicyRequest",
    "PolicyCompilation",
    "GenerateInitialScenariosRequest",
    "GenerateTargetedScenariosRequest",
    "AssembleSuiteRequest",
    "EvaluatePolicyRequest",
    "AnalyzeFindingsRequest",
    "ProposeRevisionRequest",
    "ApplyRevisionRequest",
    "PatchApplicationResult",
    "CompareRevisionRequest",
    "ComparisonBundle",
    "MetricsRequest",
    "MetricsReport",
    "ScoreBenchmarkRequest",
    "BenchmarkManifest",
    "BenchmarkScore",
    "CoverageEvidence",
    "CoverageSnapshot",
]


@pytest.mark.parametrize("name", REQUIRED)
def test_stage_contracts_are_concrete_and_generate_json_schema(name):
    model = getattr(models, name)
    assert issubclass(model, BaseModel)
    assert model.model_json_schema()["additionalProperties"] is False


def test_envelope_requires_typed_payload_and_round_trips():
    envelope = ArtifactEnvelope(
        artifact_type="policy_ir",
        artifact_sha256=HASH,
        semantic_sha256=HASH,
        parent_hashes=(),
        run_manifest_id="manifest-1",
        payload=make_policy(),
    )
    assert ArtifactEnvelope.model_validate_json(envelope.model_dump_json()) == envelope
    with pytest.raises(ValidationError):
        ArtifactEnvelope(
            artifact_type="policy_ir",
            artifact_sha256=HASH,
            semantic_sha256=HASH,
            parent_hashes=(),
            run_manifest_id="manifest-1",
            payload={"secret": ["unchecked"]},
        )


def test_envelope_rejects_wrong_hash_or_payload_kind():
    with pytest.raises(ValidationError):
        ArtifactEnvelope(
            artifact_type="scenario_suite",
            artifact_sha256=HASH,
            semantic_sha256=HASH,
            parent_hashes=(),
            run_manifest_id="manifest-1",
            payload=make_policy(),
        )
    with pytest.raises(ValidationError):
        ArtifactEnvelope(
            artifact_type="policy_ir",
            artifact_sha256="invalid",
            semantic_sha256=HASH,
            parent_hashes=(),
            run_manifest_id="manifest-1",
            payload=make_policy(),
        )


def test_run_view_excludes_private_artifact_types_recursively():
    schema = RunView.model_json_schema()
    assert not (
        {
            "PolicyDocument",
            "RunManifest",
            "BenchmarkManifest",
            "ScenarioFacts",
            "Assertion",
        }
        & set(schema.get("$defs", {}))
    )
    view = RunView(run_id="run-1", stage="queued", mode="cached")
    with pytest.raises(ValidationError):
        RunView(**view.model_dump(), raw_text="secret")
    assert RunView.model_validate_json(view.model_dump_json()) == view


def test_generation_config_is_finite_integer_configuration():
    with pytest.raises(ValidationError):
        GenerationConfig(top_p_percent=50.5)
    with pytest.raises(ValidationError):
        GenerationConfig(temperature_milli=True)


def test_every_exported_model_can_be_used_by_future_schema_exporter():
    for name in models.__all__:
        model = getattr(models, name)
        if isinstance(model, type) and issubclass(model, BaseModel):
            schema = model.model_json_schema()
            assert schema["additionalProperties"] is False, name
            assert schema["properties"]["schema_version"]["const"] == "1.0", name


def test_complete_typed_artifacts_and_stage_requests_round_trip():
    from .factories import (
        make_inputs,
        make_policy_contract,
        make_scenario_suite,
        make_trace,
    )
    from .test_revision_models import FLAGS, operation, proposal

    policy, contract, suite, inputs = (
        make_policy(),
        make_policy_contract(),
        make_scenario_suite(),
        make_inputs(),
    )
    evaluation = models.EvaluationReport(
        report_id="eval-1",
        inputs=inputs,
        engine_version="1.0",
        results=(
            models.ScenarioEvaluation(
                scenario_id="scenario-0", trace=make_trace(), verdict="UNSCORED"
            ),
        ),
        coverage=models.CoverageSnapshot(),
    )
    findings = models.FindingReport(report_id="findings-1", inputs=inputs, findings=())
    revision = proposal((operation(),))
    metrics = models.MetricsReport(
        inputs=inputs,
        scenario_count=1,
        effect_states=models.EffectStateCounts(VALUE=1),
        assertions=models.AssertionCounts(),
        unique_finding_count=0,
        coverage=models.CoverageSnapshot(),
    )
    regression = models.RegressionReport(
        report_id="regression-1",
        baseline_inputs=inputs,
        revised_inputs=inputs,
        baseline_effect_states=models.EffectStateCounts(VALUE=1),
        revised_effect_states=models.EffectStateCounts(VALUE=1),
        assertion_transition_counts=models.AssertionTransitionCounts(),
        assertion_transitions=(),
    )
    acceptance = models.PatchAcceptanceReport(
        baseline_inputs=inputs,
        revised_inputs=inputs,
        **dict.fromkeys(FLAGS, True),
        patch_accepted=True,
    )
    comparison = models.ComparisonBundle(
        baseline_inputs=inputs,
        revised_inputs=inputs,
        regression=regression,
        acceptance=acceptance,
        baseline_metrics=metrics,
        revised_metrics=metrics,
    )
    manifest = models.RunManifest(
        manifest_id="manifest-1",
        run_id="run-1",
        engine_version="1.0",
        engine_sha256=HASH,
        prompt_hashes=(models.PromptHash(prompt_name="extract", prompt_sha256=HASH),),
        provider="fake",
        model_identifier="offline",
        generation_config=models.GenerationConfig(),
        random_seed=42,
        started_at="2026-09-06T00:00:00Z",
        mode="cached",
    )
    requests = (
        models.GenerateInitialScenariosRequest(
            policy=policy, contract=contract, seed=42
        ),
        models.EvaluatePolicyRequest(
            policy=policy,
            contract=contract,
            suite=suite,
            inputs=inputs,
            engine_version="1.0",
        ),
        models.AnalyzeFindingsRequest(
            policy=policy, contract=contract, suite=suite, evaluation=evaluation
        ),
        models.ApplyRevisionRequest(
            policy=policy,
            contract=contract,
            suite=suite,
            proposal=revision,
            confirmed_at="2026-09-06T00:01:00Z",
        ),
        models.MetricsRequest(evaluation=evaluation, findings=findings),
    )
    artifacts = {
        "policy_ir": policy,
        "policy_contract": contract,
        "scenario_suite": suite,
        "evaluation_report": evaluation,
        "finding_report": findings,
        "revision_proposal": revision,
        "metrics_report": metrics,
        "regression_report": regression,
        "patch_acceptance_report": acceptance,
        "comparison_bundle": comparison,
        "run_manifest": manifest,
    }
    envelopes = tuple(
        ArtifactEnvelope(
            artifact_type=kind,
            artifact_sha256=HASH,
            semantic_sha256=HASH,
            parent_hashes=(HASH,),
            run_manifest_id="manifest-1",
            payload=payload,
        )
        for kind, payload in artifacts.items()
    )
    record = models.RunRecord(
        run_id="run-1",
        stage="queued",
        manifest=manifest,
        created_at="2026-09-06T00:00:00Z",
        expires_at="2026-09-06T01:00:00Z",
        artifacts=envelopes,
    )
    for value in (*requests, *envelopes, record):
        assert value.model_validate_json(value.model_dump_json()) == value
    assert isinstance(record.manifest.prompt_hashes, tuple)
    with pytest.raises(ValidationError):
        record.manifest.generation_config.max_output_tokens = 1


@pytest.mark.parametrize(
    "changes",
    [
        {"text": " "},
        {"text": "x" * 50001},
        {"text": "policy", "non_confidential_confirmed": False},
        {"text": "policy", "sample_id": "sample-1"},
        {"source_type": "pdf", "text": "policy"},
    ],
)
def test_create_run_enforces_pasted_input_and_consent_boundary(changes):
    with pytest.raises(ValidationError):
        models.CreateRunRequest(
            **(
                {
                    "source_type": "pasted_text",
                    "title": "Synthetic",
                    "text": "policy",
                    "non_confidential_confirmed": True,
                }
                | changes
            )
        )


def test_rejected_contract_cannot_smuggle_confirmed_rules():
    assert models.ConfirmContractRequest(decision="reject").baseline_policy_id is None
    with pytest.raises(ValidationError):
        models.ConfirmContractRequest(decision="reject", policy=make_policy())
    with pytest.raises(ValidationError):
        models.ConfirmContractRequest(decision="confirm", policy=make_policy())


def test_pasted_text_accepts_exact_approved_limit():
    request = models.CreateRunRequest(
        source_type="pasted_text",
        title="Synthetic",
        text="x" * 50_000,
        non_confidential_confirmed=True,
    )
    assert len(request.text) == 50_000
    assert (
        request.model_json_schema()["properties"]["text"]["anyOf"][0]["maxLength"]
        == 50_000
    )


def review_rule():
    from .factories import make_rule

    rule = make_rule()
    return models.RuleSummary(
        rule_id=rule.rule_id,
        revision=rule.revision,
        description=rule.description,
        when=rule.when,
        effects=rule.effects,
        overrides=rule.overrides,
        citations=(rule.provenance,),
        confidence_percent=rule.confidence_percent,
    )


def review_invariant(index):
    return models.InvariantSummary(
        invariant_id=f"invariant-{index}",
        description="Synthetic cap intent",
        when=(models.Predicate(field="expense_category", operator="eq", value="meal"),),
        assertion=models.AssertionContent(
            assertion_id=f"assertion-{index}",
            target_kind="effect_value",
            dimension="claim_cap_minor",
            operator="lte",
            expected_value=5000,
        ),
        severity="high",
    )


def test_public_contract_review_can_form_anchored_confirmation_without_policy():
    confirmation = models.ContractConfirmation(
        baseline_policy_id="policy-1",
        baseline_policy_sha256=HASH,
        document_sha256=HASH,
        rules=(review_rule(),),
        invariants=tuple(review_invariant(index) for index in range(3)),
        required_dimensions=frozenset({"claim_cap_minor"}),
    )
    view = RunView(
        run_id="run-1",
        stage="awaiting_contract",
        mode="cached",
        pending_confirmation=confirmation,
    )
    public = RunView.model_validate_json(view.model_dump_json()).pending_confirmation
    request = models.ConfirmContractRequest(
        decision="confirm",
        baseline_policy_id=public.baseline_policy_id,
        baseline_policy_sha256=public.baseline_policy_sha256,
        invariants=public.invariants,
        required_dimensions=public.required_dimensions,
    )
    assert (
        models.ConfirmContractRequest.model_validate_json(request.model_dump_json())
        == request
    )
    assert request.invariants[0].assertion.expected_value == 5000
    assert public.rules[0].effects[0].value == 5000
    assert public.rules[0].citations[0].span.quote == "Meals capped"
    assert "PolicyIR" not in request.model_json_schema().get("$defs", {})
    for changes in (
        {"baseline_policy_id": None},
        {"baseline_policy_sha256": None},
        {"baseline_policy_sha256": "invalid"},
        {"invariants": request.invariants[:2]},
        {"invariants": request.invariants * 2},
        {"required_dimensions": frozenset()},
        {"invariants": (request.invariants[0],) * 3},
        {"decision": "reject"},
        {"policy": make_policy()},
    ):
        with pytest.raises(ValidationError):
            models.ConfirmContractRequest(**(request.model_dump() | changes))


@pytest.mark.parametrize("kind", ["add_rule", "replace_rule", "add_override"])
def test_public_revision_review_carries_typed_before_and_after_changes(kind):
    draft = models.RevisionRuleDraft(
        description="Synthetic meal cap",
        when=review_invariant(0).when,
        effects=(models.Effect(dimension="claim_cap_minor", value=4500),),
    )
    common = {"rule_id": "rule-meal", "finding_ids": ("finding-1",)}
    if kind == "add_rule":
        operation = models.AddRuleOperation(**common, rule=draft)
    elif kind == "replace_rule":
        operation = models.ReplaceRuleOperation(
            **common, expected_revision=0, rule=draft
        )
    else:
        operation = models.AddOverrideOperation(
            **common, dimension="claim_cap_minor", target_rule_id="rule-other"
        )
    summary = models.RevisionOperationSummary(
        operation=operation, before=None if kind == "add_rule" else review_rule()
    )
    confirmation = models.RevisionConfirmation(
        proposal_id="proposal-1",
        operations=(summary,),
        draft_policy_wording="Draft suggestion",
    )
    view = RunView(
        run_id="run-1",
        stage="awaiting_revision_confirmation",
        mode="cached",
        pending_confirmation=confirmation,
    )
    parsed = RunView.model_validate_json(view.model_dump_json()).pending_confirmation
    assert parsed.operations[0].operation == operation
    if kind == "add_override":
        assert parsed.operations[0].operation.target_rule_id == "rule-other"
    else:
        assert parsed.operations[0].operation.rule.effects[0].value == 4500
    for operations in ((), (summary,) * 4):
        with pytest.raises(ValidationError):
            models.RevisionConfirmation(
                **(confirmation.model_dump() | {"operations": operations})
            )
    with pytest.raises(ValidationError):
        models.RevisionOperationSummary(
            operation=operation, before=review_rule() if kind == "add_rule" else None
        )


def test_run_view_represents_safe_evidence_and_explicit_holdout_aggregates():
    from .factories import make_span

    clause = models.UnsupportedClauseEvidence(
        clause_id="clause-1",
        span=make_span(),
        reason_code="unsupported_logic",
        affected_dimensions=frozenset({"claim_cap_minor"}),
        when_hint=review_invariant(0).when,
        disposition="retained_inconclusive",
    )
    rejection = models.RejectionEvidence(
        item_kind="rule",
        item_id="rule-rejected",
        source_spans=(make_span(),),
        reason_code="invalid_citation",
        disposition="excluded",
    )
    scenario_rejection = models.RejectionEvidence(
        item_kind="scenario",
        item_id="candidate-1",
        source_spans=(),
        reason_code="invalid_facts",
        disposition="excluded",
    )
    trace = models.VisibleTraceSummary(
        scenario_id="scenario-1",
        phase="baseline",
        trace_sha256=HASH,
        fired_rule_ids=("rule-meal",),
        predicate_results=(
            models.PredicateResult(
                rule_id="rule-meal", predicate_index=0, matched=True
            ),
        ),
        resolved_effects=(
            models.DimensionResult(
                dimension="claim_cap_minor", status="VALUE", value=5000
            ),
        ),
        compliance_values=(
            models.ComplianceResult(dimension="claim_cap_minor", status="COMPLIANT"),
        ),
        source_citations=(make_span(),),
    )
    holdout = models.HoldoutEvidenceSummary(
        scenario_count=2,
        unsupported_clause_count=1,
        rejected_rule_count=1,
        rejected_scenario_count=1,
        baseline_effect_states=models.EffectStateCounts(INCONCLUSIVE=2),
    )
    view = RunView(
        run_id="run-1",
        stage="baseline_execution",
        mode="cached",
        unsupported_clauses=(clause,),
        rejections=(rejection, scenario_rejection),
        traces=(trace,),
        holdout_evidence=holdout,
    )
    assert RunView.model_validate_json(view.model_dump_json()) == view
    assert view.rejections[0].source_spans[0].start == 0
    for value in (clause, rejection, trace):
        with pytest.raises(ValidationError):
            type(value)(**(value.model_dump() | {"partition": "holdout"}))
    for forbidden in (
        "scenario_id",
        "facts",
        "assertions",
        "source_citations",
        "trace_sha256",
        "gold_label_id",
        "expected_value",
    ):
        with pytest.raises(ValidationError):
            models.HoldoutEvidenceSummary(
                **(holdout.model_dump() | {forbidden: "hidden"})
            )
    schema = RunView.model_json_schema()
    assert {
        "SourceSpan",
        "Predicate",
        "Effect",
        "RevisionRuleDraft",
        "DimensionResult",
    } <= set(schema["$defs"])
    assert not {
        "PolicyIR",
        "PolicyDocument",
        "PolicyPage",
        "RunManifest",
        "BenchmarkManifest",
        "ScenarioFacts",
        "Scenario",
        "Assertion",
        "InvariantDraft",
        "EvaluationTrace",
    } & set(schema["$defs"])


@pytest.mark.parametrize(
    "changes",
    [
        {"expected_value": True},
        {"expected_value": 50.5},
        {"dimension": "eligibility", "expected_value": "allow", "operator": "lte"},
        {"origin": "gold"},
        {"gold_label_id": "private-label"},
    ],
)
def test_reviewed_invariant_assertion_is_typed_and_has_no_oracle_metadata(changes):
    with pytest.raises(ValidationError):
        models.AssertionContent(
            **(review_invariant(0).assertion.model_dump() | changes)
        )


@pytest.mark.parametrize("changes", [{"rule_id": "different-rule"}, {"revision": 1}])
def test_revision_diff_rejects_mismatched_baseline_identity_or_revision(changes):
    operation = models.ReplaceRuleOperation(
        rule_id="rule-meal",
        expected_revision=0,
        rule=models.RevisionRuleDraft(
            description="Synthetic change",
            when=review_invariant(0).when,
            effects=(models.Effect(dimension="claim_cap_minor", value=4500),),
        ),
        finding_ids=("finding-1",),
    )
    with pytest.raises(ValidationError):
        models.RevisionOperationSummary(
            operation=operation,
            before=models.RuleSummary(**(review_rule().model_dump() | changes)),
        )


def public_comparison():
    from .factories import make_inputs

    metrics = models.PublicMetrics(
        scenario_count=5,
        effect_states=models.EffectStateCounts(VALUE=5),
        assertions=models.AssertionCounts(passed=2, failed=2, inconclusive=1),
        unique_finding_count=2,
    )
    acceptance = models.PatchAcceptanceReport(
        baseline_inputs=make_inputs(),
        revised_inputs=make_inputs(),
        suite_hash_matches=True,
        all_target_findings_fixed=True,
        zero_new_failures_outside_targets=False,
        zero_protected_regressions=False,
        no_increase_in_gap_conflict_inconclusive_or_error=True,
        unrelated_rules_unchanged=True,
        holdout_not_worse=True,
        patch_accepted=False,
        counts=models.PatchAcceptanceCounts(
            target_findings=1,
            fixed_target_findings=1,
            new_failures_outside_targets=1,
            protected_regressions=1,
        ),
    )
    return models.PublicComparisonMetrics(
        baseline=metrics,
        revised=metrics,
        acceptance=acceptance,
        assertion_transition_counts=models.AssertionTransitionCounts(
            pass_to_pass=1,
            fail_to_pass=1,
            pass_to_fail=1,
            fail_to_fail=1,
            inconclusive_or_error=1,
        ),
        patch_accepted=False,
        protected_regressions=1,
        new_failures_outside_targets=1,
    )


def test_public_comparison_contains_safe_aggregate_transitions_and_acceptance():
    comparison = public_comparison()
    assert comparison.assertion_transition_counts.pass_to_fail == 1
    assert comparison.acceptance.counts.protected_regressions == 1
    assert (
        models.PublicComparisonMetrics.model_validate_json(comparison.model_dump_json())
        == comparison
    )
    definitions = RunView.model_json_schema()["$defs"]
    assert {
        "PatchAcceptanceReport",
        "InputHashes",
        "AssertionTransitionCounts",
    } <= definitions.keys()
    assert (
        not {"AssertionTransition", "RegressionReport", "ComparisonBundle"}
        & definitions.keys()
    )


@pytest.mark.parametrize(
    "changes",
    [
        {"patch_accepted": True},
        {"protected_regressions": 0},
        {"new_failures_outside_targets": 0},
    ],
)
def test_public_comparison_rejects_contradictory_duplicate_evidence(changes):
    with pytest.raises(ValidationError, match="must match acceptance"):
        models.PublicComparisonMetrics(**(public_comparison().model_dump() | changes))
