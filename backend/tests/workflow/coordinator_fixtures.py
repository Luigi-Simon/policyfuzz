"""Small authored synthetic workflow, never provider output."""

from datetime import UTC, datetime
from hashlib import sha256

from app.core.artifacts import complete_payload_projection
from app.core.hashing import canonical_sha256
from app.domain.models import (
    AnalyzeFindingsRequest,
    ArtifactRef,
    AssembleSuiteRequest,
    Assertion,
    AssertionContent,
    AssertionCounts,
    AssertionResult,
    AssertionTransition,
    AssertionTransitionCounts,
    ComparisonBundle,
    CompilePolicyRequest,
    ConfirmContractRequest,
    CoverageEvidence,
    CoverageSnapshot,
    CreateRunRequest,
    DimensionResult,
    Effect,
    EffectStateCounts,
    EvaluatePolicyRequest,
    EvaluationReport,
    EvaluationTrace,
    Finding,
    FindingDecision,
    FindingReport,
    GenerateInitialScenariosRequest,
    GenerationConfig,
    InputHashes,
    Invariant,
    InvariantSuggestion,
    MetricsReport,
    MetricsRequest,
    PatchAcceptanceCounts,
    PatchAcceptanceReport,
    PatchApplicationResult,
    PolicyCompilation,
    PolicyContract,
    PolicyDocument,
    PolicyIR,
    PolicyPage,
    Predicate,
    RegressionReport,
    ReplaceRuleOperation,
    RevisionProposal,
    RevisionRuleDraft,
    Rule,
    RunManifest,
    RunRecord,
    Scenario,
    ScenarioBatch,
    ScenarioCandidate,
    ScenarioEvaluation,
    ScenarioFacts,
    ScenarioSuite,
    SelectFindingsRequest,
    SourceSpan,
    TextRuleProvenance,
    TraceRef,
)


class Clock:
    tick = 0.0

    def wall_now(self):
        return datetime(2026, 9, 6, tzinfo=UTC)

    def monotonic(self):
        return self.tick


def digest(value):
    return canonical_sha256(complete_payload_projection(value))


def request():
    return CreateRunRequest(
        source_type="pasted_text",
        title="Synthetic",
        text="Meals allowed.",
        non_confidential_confirmed=True,
    )


def document(command):
    text = command.text or "Meals allowed."
    return PolicyDocument(
        document_id="document",
        title="Synthetic",
        source_type=command.source_type,
        pages=(PolicyPage(page=1, text=text, start=0, end=len(text)),),
        document_sha256=sha256(text.encode()).hexdigest(),
    )


def compilation(command):
    doc = command.document
    quote = doc.pages[0].text
    span = SourceSpan(
        page=1,
        start=0,
        end=len(quote),
        quote=quote,
        quote_sha256=sha256(quote.encode()).hexdigest(),
    )
    rule = Rule(
        rule_id="rule",
        description="Meals allowed",
        when=(),
        effects=(Effect(dimension="eligibility", value="allow"),),
        provenance=TextRuleProvenance(citation_id="citation", span=span),
    )
    suggestions = tuple(
        InvariantSuggestion(
            invariant_id=f"inv-{i}",
            description="Review intent",
            rationale="Untrusted rationale",
            when=(Predicate(field="amount_minor", operator="gte", value=i),),
            assertion=AssertionContent(
                assertion_id=f"assert-{i}",
                target_kind="effect_value",
                dimension="eligibility",
                operator="eq",
                expected_value="allow",
            ),
        )
        for i in range(3)
    )
    return PolicyCompilation(
        policy=PolicyIR(
            policy_id="baseline",
            document_sha256=doc.document_sha256,
            review_status="provisional",
            rules=(rule,),
        ),
        invariant_drafts=suggestions,
    )


def manifest(run_id, mode):
    return RunManifest(
        manifest_id="manifest-" + run_id,
        run_id=run_id,
        engine_version="1.0",
        engine_sha256="e" * 64,
        prompt_hashes=(),
        provider="fake",
        model_identifier="synthetic",
        generation_config=GenerationConfig(),
        random_seed=42,
        started_at=Clock().wall_now(),
        mode=mode,
    )


def confirm(view, severity="high"):
    pending = view.pending_confirmation
    return ConfirmContractRequest(
        decision="confirm",
        baseline_policy_id=pending.baseline_policy_id,
        baseline_policy_sha256=pending.baseline_policy_sha256,
        invariants=tuple(
            i.model_copy(update={"severity": severity}) for i in pending.invariants
        ),
        required_dimensions=pending.required_dimensions,
    )


def batch(value):
    return ScenarioBatch(
        candidates=tuple(
            ScenarioCandidate(
                candidate_id=f"candidate-{i}",
                category="normal",
                origins=frozenset({"session"}),
                facts=ScenarioFacts(
                    employee_role="employee",
                    expense_category="meal",
                    amount_minor=100 + i,
                    destination_type="domestic",
                    booking_days_before=10,
                    receipt_present=True,
                    approval_roles_present=frozenset(),
                    prior_same_day_category_spend_minor=0,
                ),
                assertions=(inv.assertion,),
            )
            for i, inv in enumerate(value.contract.invariants)
        )
    )


def assemble(value):
    suite = ScenarioSuite(
        suite_id=value.suite_id,
        content_sha256="0" * 64,
        seed=value.seed,
        document_sha256=value.document_sha256,
        policy_contract_sha256=value.policy_contract_sha256,
        rule_set_sha256=value.rule_set_sha256,
        engine_version=value.engine_version,
        scenarios=tuple(
            Scenario(
                scenario_id=c.candidate_id, **c.model_dump(exclude={"candidate_id"})
            )
            for c in value.candidates
        ),
    )
    return suite.model_copy(update={"content_sha256": digest(suite)})


def evaluate(value, missing=False):
    results = []
    for scenario in value.suite.scenarios:
        trace = EvaluationTrace(
            scenario_id=scenario.scenario_id,
            fired_rule_ids=tuple(r.rule_id for r in value.policy.rules),
            predicate_results=(),
            resolved_effects=(
                DimensionResult(
                    dimension="eligibility",
                    status="VALUE",
                    value="allow",
                    applicable_rule_ids=("rule",),
                ),
            ),
            compliance_values=(),
            source_citations=(),
            trace_sha256="0" * 64,
        )
        trace = trace.model_copy(update={"trace_sha256": digest(trace)})
        results.append(
            ScenarioEvaluation(
                scenario_id=scenario.scenario_id,
                trace=trace,
                assertion_results=tuple(
                    AssertionResult(assertion_id=a.assertion_id, status="PASS")
                    for a in scenario.assertions
                ),
                verdict="PASS",
            )
        )
    evidence = [
        CoverageEvidence(
            target_kind="rule",
            target_id=r.rule_id,
            scenario_ids=tuple(s.scenario_id for s in value.suite.scenarios),
        )
        for r in value.policy.rules
    ]
    for inv in value.contract.invariants:
        evidence.append(
            CoverageEvidence(
                target_kind="invariant",
                target_id=inv.invariant_id,
                scenario_ids=tuple(
                    s.scenario_id
                    for s in value.suite.scenarios
                    if any(
                        a.source_invariant_id == inv.invariant_id for a in s.assertions
                    )
                ),
            )
        )
    if missing:
        evidence = evidence[:-1]
    coverage = CoverageSnapshot(
        total_rules=len(value.policy.rules),
        covered_rules=len(value.policy.rules),
        total_invariants=3,
        covered_invariants=2 if missing else 3,
        evidence=tuple(evidence),
        missing_invariant_ids=(value.contract.invariants[-1].invariant_id,)
        if missing
        else (),
        status="pending" if missing else "satisfied",
    )
    return EvaluationReport(
        report_id="evaluation-" + value.policy.policy_id,
        inputs=value.inputs,
        engine_version=value.engine_version,
        results=tuple(results),
        coverage=coverage,
    )


def findings(value):
    return FindingReport(
        report_id="findings-" + value.policy.policy_id,
        inputs=value.evaluation.inputs,
        findings=(),
    )


def metrics(value):
    count = len(value.evaluation.results)
    return MetricsReport(
        inputs=value.evaluation.inputs,
        scenario_count=count,
        effect_states=EffectStateCounts(VALUE=count),
        assertions=AssertionCounts(
            passed=sum(len(r.assertion_results) for r in value.evaluation.results)
        ),
        unique_finding_count=len(
            {
                f.fingerprint_sha256
                for f in value.findings.findings
                if f.evidence_level != "candidate"
                and f.finding_type != "potential_loophole"
            }
        ),
        coverage=value.evaluation.coverage,
        assertion_pass_percent=100,
    )


def harness(**overrides):
    from types import SimpleNamespace

    from app.workflow.coordinator import RunCoordinator
    from app.workflow.fake_stages import (
        FakeEvaluationEngine,
        FakeFindingAnalyzer,
        FakePolicyCompiler,
        FakeRegressionAnalyzer,
        FakeRevisionApplier,
        FakeRevisionPlanner,
        FakeScenarioPlanner,
    )
    from app.workflow.store import RunStore

    clock = Clock()
    store = RunStore(clock)
    parts = {
        "policy_compiler": FakePolicyCompiler([compilation]),
        "scenario_planner": FakeScenarioPlanner(
            initial=[batch],
            targeted=[ScenarioBatch(candidates=())],
            suites=[assemble, assemble],
        ),
        "evaluation_engine": FakeEvaluationEngine(
            [evaluate, evaluate, evaluate, evaluate]
        ),
        "finding_analyzer": FakeFindingAnalyzer([findings, findings]),
        "revision_planner": FakeRevisionPlanner(),
        "revision_applier": FakeRevisionApplier(),
        "regression_analyzer": FakeRegressionAnalyzer(),
        "ingest": document,
        "metrics": metrics,
        "manifest_factory": manifest,
        "draft_severity": "low",
        "run_id_factory": lambda: "run",
    }
    parts.update(overrides)
    return RunCoordinator(store=store, clock=clock, **parts), SimpleNamespace(
        store=store, clock=clock, **parts
    )


async def baseline(coordinator):
    created = await coordinator.create_run(request())
    await coordinator.start(created.run_id)
    return await coordinator.confirm_contract(
        created.run_id, confirm(await coordinator.get_run(created.run_id))
    )


def one_finding(value, kind="structural_gap", private=False):
    row = value.evaluation.results[0]
    return FindingReport(
        report_id="findings-" + value.policy.policy_id,
        inputs=value.evaluation.inputs,
        findings=(
            Finding(
                finding_id="finding",
                fingerprint_sha256="f" * 64,
                finding_type=kind,
                evidence_level="candidate"
                if kind == "potential_loophole"
                else "mechanically_reproduced",
                scenario_ids=(row.scenario_id,),
                rule_ids=("rule",),
                dimension="eligibility",
                invariant_id="inv-0" if kind == "intent_breach" else None,
                traces=(
                    TraceRef(
                        scenario_id=row.scenario_id, trace_sha256=row.trace.trace_sha256
                    ),
                ),
            ),
        ),
    )


def proposal(value):
    rule = value.policy.rules[0]
    draft = RevisionRuleDraft(
        description="Clarify synthetic rule",
        when=(Predicate(field="expense_category", operator="eq", value="meal"),),
        effects=rule.effects,
    )
    return RevisionProposal(
        proposal_id="proposal",
        document_sha256=value.document_sha256,
        rule_set_sha256=value.rule_set_sha256,
        policy_contract_sha256=value.policy_contract_sha256,
        suite_sha256=value.suite_sha256,
        accepted_finding_ids=tuple(d.finding_id for d in value.decisions),
        operations=(
            ReplaceRuleOperation(
                rule_id=rule.rule_id,
                expected_revision=rule.revision,
                rule=draft,
                finding_ids=("finding",),
            ),
        ),
        draft_policy_wording="Unverified synthetic draft wording",
    )


def apply(value):
    rule = value.policy.rules[0]
    revised = value.policy.model_copy(
        update={
            "policy_id": "revised",
            "kind": "structured_revision",
            "rules": (rule.model_copy(update={"revision": 1}),),
        }
    )
    return PatchApplicationResult(
        proposal_id=value.proposal.proposal_id,
        applied=True,
        revised_policy=revised,
        changed_rule_ids=(rule.rule_id,),
    )


def compare(value):
    before = value.baseline_evaluation
    after = value.revised_evaluation
    bm = metrics(MetricsRequest(evaluation=before, findings=value.baseline_findings))
    rm = metrics(MetricsRequest(evaluation=after, findings=value.revised_findings))
    transitions = tuple(
        AssertionTransition(
            scenario_id=r.scenario_id,
            assertion_id=a.assertion_id,
            before="PASS",
            after="PASS",
            protected=False,
            targeted=r.scenario_id == before.results[0].scenario_id,
        )
        for r in before.results
        for a in r.assertion_results
    )
    regression = RegressionReport(
        report_id="regression",
        baseline_inputs=before.inputs,
        revised_inputs=after.inputs,
        baseline_effect_states=bm.effect_states,
        revised_effect_states=rm.effect_states,
        assertion_transition_counts=AssertionTransitionCounts(
            pass_to_pass=len(transitions)
        ),
        assertion_transitions=transitions,
    )
    acceptance = PatchAcceptanceReport(
        baseline_inputs=before.inputs,
        revised_inputs=after.inputs,
        suite_hash_matches=True,
        all_target_findings_fixed=True,
        zero_new_failures_outside_targets=True,
        zero_protected_regressions=True,
        no_increase_in_gap_conflict_inconclusive_or_error=True,
        unrelated_rules_unchanged=True,
        holdout_not_worse=True,
        patch_accepted=True,
        counts=PatchAcceptanceCounts(target_findings=1, fixed_target_findings=1),
    )
    return ComparisonBundle(
        baseline_inputs=before.inputs,
        revised_inputs=after.inputs,
        regression=regression,
        acceptance=acceptance,
        baseline_metrics=bm,
        revised_metrics=rm,
    )


def revision_harness(**overrides):
    from app.workflow.fake_stages import (
        FakeFindingAnalyzer,
        FakeRegressionAnalyzer,
        FakeRevisionApplier,
        FakeRevisionPlanner,
    )

    return harness(
        **(
            {
                "finding_analyzer": FakeFindingAnalyzer([one_finding, findings]),
                "revision_planner": FakeRevisionPlanner([proposal]),
                "revision_applier": FakeRevisionApplier([apply]),
                "regression_analyzer": FakeRegressionAnalyzer([compare]),
            }
            | overrides
        )
    )


def selection(severity="high", decision="accept"):
    return SelectFindingsRequest(
        decisions=(
            FindingDecision(
                finding_id="finding", decision=decision, reviewer_severity=severity
            ),
        )
    )


def cached_record():
    from datetime import timedelta

    from app.core.artifacts import make_artifact_envelope, semantic_payload_projection

    m = manifest("recorded", "cached")
    doc = document(request())
    policy = compilation(CompilePolicyRequest(document=doc)).policy.model_copy(
        update={"review_status": "session_confirmed"}
    )
    invs = compilation(CompilePolicyRequest(document=doc)).invariant_drafts
    contract = PolicyContract(
        contract_id="recorded-contract",
        required_dimensions=frozenset({"eligibility"}),
        invariants=tuple(
            Invariant(
                invariant_id=i.invariant_id,
                description=i.description,
                when=i.when,
                assertion=Assertion(
                    **i.assertion.model_dump(),
                    origin="session_confirmed",
                    source_invariant_id=i.invariant_id,
                ),
                severity="high",
            )
            for i in invs
        ),
    )
    candidates = batch(
        GenerateInitialScenariosRequest(policy=policy, contract=contract, seed=42)
    ).candidates
    suite = assemble(
        AssembleSuiteRequest(
            suite_id="recorded-suite",
            document_sha256=doc.document_sha256,
            policy_contract_sha256=digest(contract),
            rule_set_sha256=canonical_sha256(semantic_payload_projection(policy)),
            engine_version=m.engine_version,
            seed=42,
            candidates=candidates,
        )
    )
    inputs = InputHashes(
        policy_sha256=digest(policy),
        contract_sha256=digest(contract),
        suite_sha256=digest(suite),
        engine_sha256=m.engine_sha256,
        run_manifest_sha256=digest(m),
    )
    evaluation = evaluate(
        EvaluatePolicyRequest(
            policy=policy,
            contract=contract,
            suite=suite,
            inputs=inputs,
            engine_version=m.engine_version,
        )
    )
    report = findings(
        AnalyzeFindingsRequest(
            policy=policy, contract=contract, suite=suite, evaluation=evaluation
        )
    )
    metric = metrics(MetricsRequest(evaluation=evaluation, findings=report))
    envelopes = []
    for kind, payload in (
        ("run_manifest", m),
        ("policy_document", doc),
        ("policy_ir", policy),
        ("policy_contract", contract),
        ("scenario_suite", suite),
        ("evaluation_report", evaluation),
        ("finding_report", report),
        ("metrics_report", metric),
    ):
        refs = tuple(
            ArtifactRef(
                artifact_type=a.artifact_type,
                artifact_sha256=a.artifact_sha256,
                semantic_sha256=a.semantic_sha256,
            )
            for a in envelopes
        )
        envelopes.append(
            make_artifact_envelope(
                artifact_type=kind,
                payload=payload,
                parent_refs=refs,
                run_manifest_id=m.manifest_id,
            )
        )
    return RunRecord(
        run_id="recorded",
        stage="completed_no_findings",
        manifest=m,
        created_at=m.started_at,
        expires_at=m.started_at + timedelta(seconds=3600),
        artifacts=tuple(envelopes),
    )


def cached_holdout_record(*, append_visible_suite=False):
    """Authored canonical cache graph used to test frozen partition boundaries."""
    from app.core.artifacts import make_artifact_envelope

    record = cached_record()
    original_suite = next(
        a.payload for a in record.artifacts if a.artifact_type == "scenario_suite"
    )
    holdout_suite = original_suite.model_copy(
        update={
            "scenarios": tuple(
                s.model_copy(update={"partition": "holdout"})
                for s in original_suite.scenarios
            )
        }
    )
    holdout_suite = holdout_suite.model_copy(
        update={"content_sha256": digest(holdout_suite)}
    )
    artifacts = []
    for original in record.artifacts:
        payload = original.payload
        if original.artifact_type == "scenario_suite":
            payload = holdout_suite
        elif original.artifact_type in {
            "evaluation_report",
            "finding_report",
            "metrics_report",
        }:
            payload = payload.model_copy(
                update={
                    "inputs": payload.inputs.model_copy(
                        update={"suite_sha256": digest(holdout_suite)}
                    )
                }
            )
            if original.artifact_type == "evaluation_report":
                policy = next(
                    a.payload for a in artifacts if a.artifact_type == "policy_ir"
                )
                rows = []
                for row in payload.results:
                    trace = row.trace.model_copy(
                        update={"source_citations": (policy.rules[0].provenance,)}
                    )
                    trace = trace.model_copy(update={"trace_sha256": digest(trace)})
                    rows.append(row.model_copy(update={"trace": trace}))
                payload = payload.model_copy(update={"results": tuple(rows)})
        refs = tuple(
            ArtifactRef(
                artifact_type=a.artifact_type,
                artifact_sha256=a.artifact_sha256,
                semantic_sha256=a.semantic_sha256,
            )
            for a in artifacts
        )
        artifacts.append(
            make_artifact_envelope(
                artifact_type=original.artifact_type,
                payload=payload,
                parent_refs=refs,
                run_manifest_id=record.manifest.manifest_id,
            )
        )
    if append_visible_suite:
        visible_suite = original_suite.model_copy(
            update={"suite_id": "appended-visible-suite"}
        )
        visible_suite = visible_suite.model_copy(
            update={"content_sha256": digest(visible_suite)}
        )
        refs = tuple(
            ArtifactRef(
                artifact_type=a.artifact_type,
                artifact_sha256=a.artifact_sha256,
                semantic_sha256=a.semantic_sha256,
            )
            for a in artifacts
        )
        artifacts.append(
            make_artifact_envelope(
                artifact_type="scenario_suite",
                payload=visible_suite,
                parent_refs=refs,
                run_manifest_id=record.manifest.manifest_id,
            )
        )
    return record.model_copy(update={"artifacts": tuple(artifacts)})
