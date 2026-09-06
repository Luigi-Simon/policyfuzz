import pytest
from test_findings_patches import patch_request

from app.domain.models import (
    AnalyzeFindingsRequest,
    AssertionResult,
    CompareRevisionRequest,
)
from app.features.evaluation.engine import DeterministicEvaluationEngine, payload_hash
from app.features.evaluation.findings import DeterministicFindingAnalyzer
from app.features.evaluation.patches import DeterministicRevisionApplier
from app.features.evaluation.regression import (
    DeterministicRegressionAnalyzer,
    compare_assertion_outcomes,
)


@pytest.mark.parametrize("before", ["PASS", "FAIL", "INCONCLUSIVE", "ERROR"])
@pytest.mark.parametrize("after", ["PASS", "FAIL", "INCONCLUSIVE", "ERROR"])
def test_all_transitions(before, after):
    transition = compare_assertion_outcomes(
        AssertionResult(assertion_id="a", status=before),
        AssertionResult(assertion_id="a", status=after),
        scenario_id="s",
        protected=True,
    )
    assert (transition.before, transition.after) == (before, after)


def comparison_request(request_factory, policy_factory, rule_factory):
    apply = patch_request(request_factory, policy_factory, rule_factory)
    applied = DeterministicRevisionApplier().apply_revision(apply)
    baseline_request = request_factory(apply.policy)
    revised_request = baseline_request.model_copy(
        update={
            "policy": applied.revised_policy,
            "inputs": baseline_request.inputs.model_copy(
                update={"policy_sha256": payload_hash(applied.revised_policy)}
            ),
        }
    )
    before = DeterministicEvaluationEngine().evaluate(baseline_request)
    after = DeterministicEvaluationEngine().evaluate(revised_request)
    findings = lambda policy, evaluation: DeterministicFindingAnalyzer().analyze(
        AnalyzeFindingsRequest(
            policy=policy,
            contract=apply.contract,
            suite=apply.suite,
            evaluation=evaluation,
        )
    )
    return CompareRevisionRequest(
        baseline_policy=apply.policy,
        revised_policy=applied.revised_policy,
        contract=apply.contract,
        suite=apply.suite,
        proposal=apply.proposal,
        baseline_evaluation=before,
        revised_evaluation=after,
        baseline_findings=findings(apply.policy, before),
        revised_findings=findings(applied.revised_policy, after),
    )


def test_fixed_boundary_passes_all_seven_gates(
    request_factory, policy_factory, rule_factory
):
    request = comparison_request(request_factory, policy_factory, rule_factory)
    result = DeterministicRegressionAnalyzer().compare(request)
    assert result.acceptance.patch_accepted
    assert result.acceptance.counts.fixed_target_findings == 1


def test_missing_dimension_pair_rejected(request_factory, policy_factory, rule_factory):
    request = comparison_request(request_factory, policy_factory, rule_factory)
    result = request.revised_evaluation.results[0]
    trace = result.trace.model_copy(
        update={"resolved_effects": result.trace.resolved_effects[:-1]}
    )
    request = request.model_copy(
        update={
            "revised_evaluation": request.revised_evaluation.model_copy(
                update={"results": (result.model_copy(update={"trace": trace}),)}
            )
        }
    )
    with pytest.raises(ValueError):
        DeterministicRegressionAnalyzer().compare(request)


def test_forged_findings_rejected(request_factory, policy_factory, rule_factory):
    request = comparison_request(request_factory, policy_factory, rule_factory)
    original = request.baseline_findings.findings[0]
    forged = original.model_copy(
        update={
            "scenario_ids": ("invented",),
            "traces": tuple(
                t.model_copy(update={"scenario_id": "invented"})
                for t in original.traces
            ),
        }
    )
    request = request.model_copy(
        update={
            "baseline_findings": request.baseline_findings.model_copy(
                update={"findings": (forged,)}
            )
        }
    )
    with pytest.raises(ValueError, match="finding"):
        DeterministicRegressionAnalyzer().compare(request)


def test_unrelated_rule_change_rejected_by_gate(
    request_factory, policy_factory, rule_factory
):
    request = comparison_request(request_factory, policy_factory, rule_factory)
    # The valid operation touches only r1. An extra uncited semantic rule cannot be smuggled in.
    extra = rule_factory("unrelated", "receipt_requirement", "required")
    revised = request.revised_policy.model_copy(
        update={"rules": request.revised_policy.rules + (extra,)}
    )
    evaluation_request = request_factory(request.baseline_policy).model_copy(
        update={
            "policy": revised,
            "inputs": request.revised_evaluation.inputs.model_copy(
                update={"policy_sha256": payload_hash(revised)}
            ),
        }
    )
    evaluation = DeterministicEvaluationEngine().evaluate(evaluation_request)
    findings = DeterministicFindingAnalyzer().analyze(
        AnalyzeFindingsRequest(
            policy=revised,
            contract=request.contract,
            suite=request.suite,
            evaluation=evaluation,
        )
    )
    request = request.model_copy(
        update={
            "revised_policy": revised,
            "revised_evaluation": evaluation,
            "revised_findings": findings,
        }
    )
    result = DeterministicRegressionAnalyzer().compare(request)
    assert not result.acceptance.unrelated_rules_unchanged
    assert not result.acceptance.patch_accepted


def test_equal_bad_totals_do_not_hide_relocation(
    request_factory, policy_factory, rule_factory, scenario_factory, facts
):
    from app.domain.models import Predicate

    original = patch_request(request_factory, policy_factory, rule_factory)
    scenarios = [
        scenario_factory(),
        scenario_factory(
            "protected",
            facts=facts.model_copy(update={"amount_minor": 4999}),
            protected=True,
            partition="holdout",
        ),
    ]
    baseline_request = request_factory(original.policy, scenarios)
    op = original.proposal.operations[0]
    op = op.model_copy(
        update={
            "rule": op.rule.model_copy(
                update={
                    "when": (
                        Predicate(field="amount_minor", operator="gte", value=5000),
                    )
                }
            )
        }
    )
    proposal = original.proposal.model_copy(
        update={
            "suite_sha256": payload_hash(baseline_request.suite),
            "operations": (op,),
        }
    )
    apply = original.model_copy(
        update={"suite": baseline_request.suite, "proposal": proposal}
    )
    applied = DeterministicRevisionApplier().apply_revision(apply)
    assert applied.applied
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

    def findings(policy, evaluation):
        return DeterministicFindingAnalyzer().analyze(
            AnalyzeFindingsRequest(
                policy=policy,
                contract=apply.contract,
                suite=apply.suite,
                evaluation=evaluation,
            )
        )

    result = DeterministicRegressionAnalyzer().compare(
        CompareRevisionRequest(
            baseline_policy=apply.policy,
            revised_policy=applied.revised_policy,
            contract=apply.contract,
            suite=apply.suite,
            proposal=proposal,
            baseline_evaluation=before,
            revised_evaluation=after,
            baseline_findings=findings(apply.policy, before),
            revised_findings=findings(applied.revised_policy, after),
        )
    )
    assert (
        result.regression.baseline_effect_states.GAP
        == result.regression.revised_effect_states.GAP
        == 1
    )
    assert not result.acceptance.no_increase_in_gap_conflict_inconclusive_or_error
    assert not result.acceptance.zero_protected_regressions
    assert not result.acceptance.holdout_not_worse
    assert not result.acceptance.zero_new_failures_outside_targets
    assert not result.acceptance.patch_accepted


def test_revised_rule_must_match_confirmed_operation(
    request_factory, policy_factory, rule_factory
):
    from app.domain.models import Effect

    request = comparison_request(request_factory, policy_factory, rule_factory)
    rule = request.revised_policy.rules[0].model_copy(
        update={"effects": (Effect(dimension="eligibility", value="deny"),)}
    )
    revised = request.revised_policy.model_copy(update={"rules": (rule,)})
    evaluated = DeterministicEvaluationEngine().evaluate(
        request_factory(request.baseline_policy).model_copy(
            update={
                "policy": revised,
                "inputs": request.revised_evaluation.inputs.model_copy(
                    update={"policy_sha256": payload_hash(revised)}
                ),
            }
        )
    )
    findings = DeterministicFindingAnalyzer().analyze(
        AnalyzeFindingsRequest(
            policy=revised,
            contract=request.contract,
            suite=request.suite,
            evaluation=evaluated,
        )
    )
    request = request.model_copy(
        update={
            "revised_policy": revised,
            "revised_evaluation": evaluated,
            "revised_findings": findings,
        }
    )
    result = DeterministicRegressionAnalyzer().compare(request)
    assert not result.acceptance.unrelated_rules_unchanged
    assert not result.acceptance.patch_accepted
