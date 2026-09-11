import pytest

from app.v2.metric.parser import prepare
from app.v2.metric.sample import SAMPLE_POLICY
from app.v2.metric.service import run_case, run_metric
from app.v2.metric_contracts import UnsupportedAction


def test_templates_execute_real_traces_and_find_independent_defects():
    result = run_metric(SAMPLE_POLICY, "run-metric", test_budget=12)
    assert result.generation_method == "rule_templates"
    assert len(result.cases) == 12
    assert {case.category for case in result.cases} == {
        "normal",
        "boundary",
        "compound",
        "cascading",
        "adversarial",
    }
    failures = {case.case_id for case in result.cases if case.verdict == "fail"}
    assert {"overlapping-approvals", "duplicate-journey"} <= failures
    for case in result.cases:
        assert len(case.trace) == len(case.actions)
        for step in case.trace:
            if not step.accepted:
                assert step.before_state_sha256 == step.after_state_sha256
        for first, second in zip(case.trace, case.trace[1:]):
            assert first.after_state_sha256 == second.before_state_sha256


def test_corrected_rules_pass_the_same_cases():
    corrected = SAMPLE_POLICY.model_copy(
        update={
            "description": SAMPLE_POLICY.description.replace(
                "accounting=paid_only", "accounting=paid_and_approved"
            )
            .replace("recheck=off", "recheck=on")
            .replace("scope=claim_id", "scope=journey")
        }
    )
    before = run_metric(SAMPLE_POLICY, "before", test_budget=12)
    after = run_metric(corrected, "after", test_budget=12)
    assert before.suite_sha256 == after.suite_sha256
    assert after.passed == 12 and after.failed == after.unscored == 0


def test_minimized_failures_reproduce_and_are_deletion_minimal():
    result = run_metric(SAMPLE_POLICY, "run-minimal", test_budget=12)
    for case in result.cases:
        if case.verdict != "fail":
            continue
        assert case.minimal_actions
        requirements = tuple(a.requirement_id for a in case.assertions)

        def replay(actions, case=case, requirements=requirements):
            return run_case(
                result.review,
                case.case_id,
                case.title,
                case.category,
                case.plausibility,
                actions,
                requirements,
            )

        assert replay(case.minimal_actions).verdict == "fail"
        for index in range(len(case.minimal_actions)):
            reduced = case.minimal_actions[:index] + case.minimal_actions[index + 1 :]
            if reduced:
                assert replay(reduced).verdict != "fail"


def test_unsupported_policy_is_explicitly_unscored_and_never_passes():
    policy = SAMPLE_POLICY.model_copy(
        update={"description": "Improve transport access."}
    )
    result = run_metric(policy, "run-unknown", test_budget=12)
    assert result.status == "partial" and result.generation_method == "policy_scenarios"
    assert result.pass_rate is None and result.cases
    assert result.passed == result.failed == 0
    assert result.unscored == len(result.cases)
    assert all(not c.trace and not c.assertions for c in result.cases)


def test_employment_scenarios_remain_unscored_and_bound_to_exact_input():
    policy = SAMPLE_POLICY.model_copy(
        update={
            "description": "Synthetic policy: rest between shifts, no retaliation for refusing overtime; emergency exceptions and monthly review."
        }
    )
    first = run_metric(policy, "one", test_budget=12)
    second = run_metric(
        policy.model_copy(update={"description": policy.description + " "}),
        "two",
        test_budget=12,
    )
    assert first.generation_method == "policy_scenarios"
    assert {"normal", "boundary", "compound", "cascading", "adversarial"} <= {
        c.category for c in first.cases
    }
    assert any("rest" in c.plausibility for c in first.cases)
    assert first.suite_sha256 != second.suite_sha256
    assert first.review.rules is None and first.review.status == "needs_clarification"


def test_unsupported_action_is_unscored_even_with_a_reviewed_goal():
    case = run_case(
        prepare(SAMPLE_POLICY),
        "unknown",
        "Unknown action",
        "adversarial",
        "A transfer is outside this model.",
        (UnsupportedAction(action="transfer"),),
        ("G-BUDGET",),
    )
    assert case.verdict == "unscored" and not case.assertions
    assert case.unscored_reason


def test_test_budget_is_independent_of_stakeholder_count():
    policy = SAMPLE_POLICY.model_copy(update={"agent_count": 100})
    result = run_metric(policy, "run-budget", test_budget=3)
    assert len(result.cases) == 3


@pytest.mark.parametrize("mutation", ["completed", "trace", "method", "scored"])
def test_scenario_plan_cannot_be_laundered_into_executed_results(mutation):
    from app.v2.metric_contracts import MetricRunResult

    result = run_metric(
        SAMPLE_POLICY.model_copy(
            update={"description": "Synthetic flexible schedule."}
        ),
        "plan",
    )
    value = result.model_dump(mode="json")
    if mutation == "completed":
        value["status"] = "completed"
    elif mutation == "method":
        value["generation_method"] = "rule_templates"
    elif mutation == "scored":
        value["cases"][0]["verdict"] = "pass"
    else:
        value["cases"][0]["trace"] = (
            run_metric(SAMPLE_POLICY, "other").cases[0].model_dump(mode="json")["trace"]
        )
    with pytest.raises(ValueError):
        MetricRunResult.model_validate(value)
