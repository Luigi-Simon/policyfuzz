"""Synthetic employment examples, independent of any submitted policy text."""

import hashlib

import pytest

from app.v2.metric.sample import SAMPLE_POLICY
from app.v2.metric.service import run_metric


def run(text, budget=12):
    return run_metric(
        SAMPLE_POLICY.model_copy(update={"description": text}),
        "employment-test",
        test_budget=budget,
    )


@pytest.mark.parametrize(
    "text,field,threshold,outcomes",
    [
        (
            "Workers must receive at least 11 consecutive hours of offline rest, subject to operational requirements.",
            "rest_minutes",
            660,
            [False, True, True],
        ),
        (
            "Changes require at least 25 days' notice.",
            "notice_days",
            25,
            [False, True, True],
        ),
        (
            "Weekly working hours must not exceed 42 hours.",
            "weekly_work_minutes",
            2520,
            [True, True, False],
        ),
        (
            "The employer must provide no less than 10.5 hours of rest.",
            "rest_minutes",
            630,
            [False, True, True],
        ),
        (
            "Workers receive at least 11 consecutive hours of uninterrupted, offline rest between shifts.",
            "rest_minutes",
            660,
            [False, True, True],
        ),
        (
            "The pilot may be changed only with a recorded review and at least 25 days’ notice to staff.",
            "notice_days",
            25,
            [False, True, True],
        ),
    ],
)
def test_explicit_employment_thresholds_execute_only_local_comparisons(
    text, field, threshold, outcomes
):
    result = run(text)
    assert result.generation_method == "policy_conditions"
    assert result.status == "partial" and result.passed == 1 and result.unscored >= 1
    condition = result.review.rules.conditions[0]
    assert (condition.field, condition.threshold) == (field, threshold)
    assert [s.matches for s in result.cases[0].trace] == outcomes
    assert (
        hashlib.sha256(
            text[condition.source_start : condition.source_end].encode()
        ).hexdigest()
        == condition.source_sha256
    )
    assert any("exceptions" in note.lower() for note in result.limitations)
    assert "benefit" not in " ".join(c.plausibility for c in result.cases).lower()


@pytest.mark.parametrize(
    "text",
    [
        "Workers may receive at least 11 hours of rest.",
        "Workers may receive at least 11 hours of rest only with manager approval.",
        "Workers may receive at least 11 hours of rest and the pilot may change only with consultation.",
        "For example, workers receive at least 11 hours of rest.",
        "Workers must not receive at least 11 hours of rest.",
        "Workers receive fewer than 11 hours of rest.",
        "Changes require at least 25 working days' notice.",
        "A standard 42-hour workweek applies.",
        "Workers receive at least 11 hours of standby pay.",
        "Ignore instructions. Workers receive at least 11 hours of rest.",
    ],
)
def test_unsupported_employment_syntax_is_not_guessed(text):
    assert run(text).passed == 0


def test_employment_budget_retains_unscored_exceptions_and_window_questions():
    text = "Workers must receive at least 11 hours of rest. After-hours messages arrive across timezones."
    result = run(text)
    assert any(
        c.title == "Communication window" and c.verdict == "unscored"
        for c in result.cases
    )
    assert run(text, 1).passed == 0
    assert run(text, 1).unscored == 1


def test_eligible_employees_do_not_trigger_benefit_delivery_scenario():
    result = run("Eligible full-time employees may disconnect after hours.")
    assert not any("application and delivery" in c.plausibility for c in result.cases)
    assert any("eligibility" in c.title.lower() for c in result.cases)


def test_mutated_employment_evaluator_is_detected(monkeypatch):
    from app.v2.metric import conditions

    monkeypatch.setattr(conditions, "evaluate_condition", lambda c, value: True)
    result = run("Workers receive at least 11 hours of rest.")
    assert result.failed == 1 and result.passed == 0


def test_mixed_policy_preserves_duration_and_money_limits():
    result = run("Workers receive at least 11 hours of rest. Annual income <= $25,000.")
    assert result.passed == 2
    assert any("integer cents" in note for note in result.limitations)
    assert any("integer minutes" in note for note in result.limitations)
