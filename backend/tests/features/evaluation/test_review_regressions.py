"""Negative reproductions from the first deterministic-evaluation review."""

import importlib.util
from pathlib import Path

import pytest
from test_findings_patches import patch_request

from app.domain.models import (
    AddRuleOperation,
    AnalyzeFindingsRequest,
    ApplyRevisionRequest,
    CompareRevisionRequest,
    Effect,
    OverrideRef,
    Predicate,
    ReplaceRuleOperation,
    RevisionProposal,
    RevisionRuleDraft,
    UnsupportedClause,
)
from app.features.evaluation.engine import (
    DeterministicEvaluationEngine,
    evaluate_scenario,
    payload_hash,
)
from app.features.evaluation.findings import DeterministicFindingAnalyzer
from app.features.evaluation.patches import DeterministicRevisionApplier
from app.features.evaluation.regression import DeterministicRegressionAnalyzer


def test_new_fingerprint_does_not_fix_unchanged_gap(
    request_factory, policy_factory, rule_factory
):
    request = patch_request(request_factory, policy_factory, rule_factory)
    operation = AddRuleOperation(
        rule_id="nonmatching",
        finding_ids=request.proposal.accepted_finding_ids,
        rule=RevisionRuleDraft(
            description="A rule that misses the failing boundary",
            when=(Predicate(field="amount_minor", operator="eq", value=1),),
            effects=(Effect(dimension="eligibility", value="allow"),),
        ),
    )
    request = request.model_copy(
        update={
            "proposal": request.proposal.model_copy(update={"operations": (operation,)})
        }
    )
    applied = DeterministicRevisionApplier().apply_revision(request)
    assert applied.applied
    baseline_request = request_factory(request.policy)
    before = DeterministicEvaluationEngine().evaluate(baseline_request)
    after = DeterministicEvaluationEngine().evaluate(
        baseline_request.model_copy(
            update={
                "policy": applied.revised_policy,
                "inputs": baseline_request.inputs.model_copy(
                    update={"policy_sha256": payload_hash(applied.revised_policy)}
                ),
            }
        )
    )

    def analyze(policy, evaluation):
        return DeterministicFindingAnalyzer().analyze(
            AnalyzeFindingsRequest(
                policy=policy,
                contract=request.contract,
                suite=request.suite,
                evaluation=evaluation,
            )
        )

    old_findings, new_findings = (
        analyze(request.policy, before),
        analyze(applied.revised_policy, after),
    )
    assert (
        old_findings.findings[0].fingerprint_sha256
        != new_findings.findings[0].fingerprint_sha256
    )
    assert (
        before.results[0].trace.resolved_effects[0]
        == after.results[0].trace.resolved_effects[0]
    )
    comparison = DeterministicRegressionAnalyzer().compare(
        CompareRevisionRequest(
            baseline_policy=request.policy,
            revised_policy=applied.revised_policy,
            contract=request.contract,
            suite=request.suite,
            proposal=request.proposal,
            baseline_evaluation=before,
            revised_evaluation=after,
            baseline_findings=old_findings,
            revised_findings=new_findings,
        )
    )
    assert not comparison.acceptance.all_target_findings_fixed
    assert comparison.acceptance.counts.fixed_target_findings == 0
    assert not comparison.acceptance.patch_accepted


def test_replace_cannot_smuggle_unaccepted_dimension_override(
    request_factory, policy_factory, rule_factory
):
    r1 = rule_factory(
        "r1",
        value="deny",
        when=(Predicate(field="amount_minor", operator="gte", value=1),),
    )
    r1 = r1.model_copy(
        update={
            "effects": r1.effects
            + (Effect(dimension="approval_requirement", value="none"),)
        }
    )
    policy = policy_factory(
        [
            r1,
            rule_factory("r2", value="allow"),
            rule_factory("b", "approval_requirement", "manager"),
        ]
    )
    evaluate = request_factory(policy)
    findings = DeterministicFindingAnalyzer().analyze(
        AnalyzeFindingsRequest(
            policy=policy,
            contract=evaluate.contract,
            suite=evaluate.suite,
            evaluation=DeterministicEvaluationEngine().evaluate(evaluate),
        )
    )
    target = next(f for f in findings.findings if f.dimension == "eligibility")
    original = patch_request(request_factory, policy_factory, rule_factory)
    proposal = RevisionProposal(
        proposal_id="smuggled-override",
        document_sha256=policy.document_sha256,
        rule_set_sha256=evaluate.suite.rule_set_sha256,
        policy_contract_sha256=payload_hash(evaluate.contract),
        suite_sha256=payload_hash(evaluate.suite),
        accepted_finding_ids=(target.finding_id,),
        draft_policy_wording="Synthetic correction",
        operations=(
            ReplaceRuleOperation(
                rule_id="r1",
                expected_revision=r1.revision,
                finding_ids=(target.finding_id,),
                rule=RevisionRuleDraft(
                    description="Fix only accepted eligibility",
                    when=r1.when,
                    effects=(
                        Effect(dimension="eligibility", value="allow"),
                        Effect(dimension="approval_requirement", value="none"),
                    ),
                    overrides=(
                        OverrideRef(
                            dimension="approval_requirement", target_rule_id="b"
                        ),
                    ),
                ),
            ),
        ),
    )
    request = ApplyRevisionRequest(
        policy=policy,
        contract=evaluate.contract,
        suite=evaluate.suite,
        proposal=proposal,
        confirmed_at=original.confirmed_at,
    )
    before = policy.model_dump()
    result = DeterministicRevisionApplier().apply_revision(request)
    assert not result.applied
    assert result.revised_policy is None and result.changed_rule_ids == ()
    assert policy.model_dump() == before


@pytest.mark.parametrize(
    "hint,required,status",
    [
        (None, False, "NOT_APPLICABLE"),
        (None, True, "INCONCLUSIVE"),
        (
            (Predicate(field="expense_category", operator="eq", value="meal"),),
            False,
            "INCONCLUSIVE",
        ),
        ((), False, "INCONCLUSIVE"),
    ],
)
def test_unknown_unsupported_only_blocks_required_dimension(
    policy_factory, rule_factory, contract, scenario_factory, hint, required, status
):
    clause = UnsupportedClause(
        clause_id="u",
        span=rule_factory().provenance.span,
        reason_code="ambiguous_language",
        affected_dimensions=frozenset({"daily_category_cap_minor"}),
        when_hint=hint,
    )
    policy = policy_factory(unsupported_clauses=(clause,))
    if required:
        contract = contract.model_copy(
            update={
                "required_dimensions": contract.required_dimensions
                | {"daily_category_cap_minor"}
            }
        )
    result = evaluate_scenario(policy, contract, scenario_factory())
    dimension = next(
        d
        for d in result.trace.resolved_effects
        if d.dimension == "daily_category_cap_minor"
    )
    assert dimension.status == status
    assert dimension.unsupported_clause_ids == (
        () if status == "NOT_APPLICABLE" else ("u",)
    )


@pytest.mark.parametrize("change", ["fingerprint", "witness", "target"])
def test_benchmark_answer_key_does_not_follow_analyzer(monkeypatch, change):
    path = (
        Path(__file__).resolve().parents[4]
        / "team/person-4-evaluation/build_benchmarks.py"
    )
    spec = importlib.util.spec_from_file_location("evaluation_benchmark_builder", path)
    builder = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(builder)
    original = builder.DeterministicFindingAnalyzer.analyze

    def corrupt(self, request):
        report = original(self, request)
        changed = []
        for finding in report.findings:
            if finding.finding_type == "structural_gap":
                updates = (
                    {"fingerprint_sha256": "f" * 64}
                    if change == "fingerprint"
                    else (
                        {"rule_ids": (request.policy.rules[0].rule_id,)}
                        if change == "target"
                        else {
                            "scenario_ids": ("receipt-above",),
                            "traces": tuple(
                                t.model_copy(update={"scenario_id": "receipt-above"})
                                for t in finding.traces
                            ),
                        }
                    )
                )
                finding = finding.model_copy(update=updates)
            changed.append(finding)
        return report.model_copy(update={"findings": tuple(changed)})

    monkeypatch.setattr(builder.DeterministicFindingAnalyzer, "analyze", corrupt)
    emitted = []
    monkeypatch.setattr(builder, "write_json", lambda *args: emitted.append(args))
    with pytest.raises(ValueError):
        builder.build("development")
    assert emitted == []


def test_replace_cannot_add_override_outside_accepted_conflict_endpoints(
    request_factory, policy_factory, rule_factory
):
    rule = rule_factory(
        "r1",
        value="deny",
        when=(Predicate(field="amount_minor", operator="gte", value=1),),
    )
    other = rule_factory(
        "outside", when=(Predicate(field="amount_minor", operator="eq", value=1),)
    )
    policy = policy_factory([rule, rule_factory("r2", value="allow"), other])
    evaluate = request_factory(policy)
    findings = DeterministicFindingAnalyzer().analyze(
        AnalyzeFindingsRequest(
            policy=policy,
            contract=evaluate.contract,
            suite=evaluate.suite,
            evaluation=DeterministicEvaluationEngine().evaluate(evaluate),
        )
    )
    target = next(f for f in findings.findings if f.finding_type == "conflict")
    original = patch_request(request_factory, policy_factory, rule_factory)
    proposal = original.proposal.model_copy(
        update={
            "rule_set_sha256": evaluate.suite.rule_set_sha256,
            "suite_sha256": payload_hash(evaluate.suite),
            "accepted_finding_ids": (target.finding_id,),
            "operations": (
                ReplaceRuleOperation(
                    rule_id="r1",
                    expected_revision=rule.revision,
                    finding_ids=(target.finding_id,),
                    rule=RevisionRuleDraft(
                        description="An out-of-scope precedence edge",
                        when=rule.when,
                        effects=(Effect(dimension="eligibility", value="allow"),),
                        overrides=(
                            OverrideRef(
                                dimension="eligibility", target_rule_id="outside"
                            ),
                        ),
                    ),
                ),
            ),
        }
    )
    applied = DeterministicRevisionApplier().apply_revision(
        ApplyRevisionRequest(
            policy=policy,
            contract=evaluate.contract,
            suite=evaluate.suite,
            proposal=proposal,
            confirmed_at=original.confirmed_at,
        )
    )
    assert not applied.applied
    assert applied.revised_policy is None
