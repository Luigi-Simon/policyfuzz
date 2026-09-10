from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.v2.metric_contracts import (
    AssertionResult,
    MetricCaseResult,
    MetricReview,
    MetricRules,
    MetricRunResult,
    MetricState,
    PolicyClause,
    PolicyGoal,
    SubmitAction,
    TraceStep,
)


def _review() -> MetricReview:
    return MetricReview(
        policy_text_sha256="a" * 64,
        review_fingerprint="b" * 64,
        status="ready",
        clauses=(PolicyClause(id="C1", text="Claims have a stated limit."),),
        goals=(
            PolicyGoal(
                id="G1",
                text="A valid claim can be paid.",
                clause_ids=("C1",),
            ),
        ),
        rules=MetricRules(
            per_claim_limit_cents=10_000,
            participant_allowance_cents=15_000,
            approval_budget_accounting="paid_only",
            payment_budget_recheck=False,
            duplicate_scope="claim_id",
        ),
        assumptions=("Money values use integer SGD cents.",),
        limitations=("Only the bounded reimbursement domain is interpreted.",),
    )


def _step() -> TraceStep:
    return TraceStep(
        step_id="S1",
        action_index=0,
        action=SubmitAction(
            claim_id="CL1",
            participant_id="P1",
            journey_id="J1",
            amount_cents=1,
        ),
        accepted=True,
        detail="The claim was submitted.",
        before_state_sha256="c" * 64,
        after_state_sha256="d" * 64,
        participant_paid_cents_before=0,
        participant_paid_cents_after=0,
        participant_reserved_cents_before=0,
        participant_reserved_cents_after=0,
    )


def _case(*, verdict: str = "pass") -> MetricCaseResult:
    return MetricCaseResult(
        case_id="CASE1",
        title="Valid claim",
        category="normal",
        plausibility="A participant submits one ordinary claim.",
        initial_state=MetricState(),
        actions=(
            SubmitAction(
                claim_id="CL1",
                participant_id="P1",
                journey_id="J1",
                amount_cents=1,
            ),
        ),
        trace=(_step(),),
        assertions=(
            AssertionResult(
                requirement_id="G1",
                passed=verdict == "pass",
                expected="The valid claim is accepted.",
                actual="The claim was accepted.",
                step_refs=("S1",),
            ),
        ),
        verdict=verdict,
        unscored_reason=None,
        minimal_actions=None,
    )


def test_actions_forbid_generated_expected_outcomes() -> None:
    with pytest.raises(ValidationError):
        SubmitAction.model_validate(
            {
                "action": "submit",
                "claim_id": "CL1",
                "participant_id": "P1",
                "journey_id": "J1",
                "amount_cents": 100,
                "expected_outcome": "accepted",
            }
        )


def test_case_verdict_requires_real_assertions_and_step_references() -> None:
    with pytest.raises(ValidationError, match="pass requires"):
        MetricCaseResult.model_validate(_case().model_dump() | {"assertions": ()})

    with pytest.raises(ValidationError, match="unknown trace step"):
        MetricCaseResult.model_validate(
            _case().model_dump()
            | {
                "assertions": [
                    _case()
                    .assertions[0]
                    .model_copy(update={"step_refs": ("MISSING",)})
                    .model_dump()
                ]
            }
        )


def test_run_result_validates_counts_denominator_and_goal_citations() -> None:
    payload = {
        "run_id": "RUN1",
        "policy_text_sha256": "a" * 64,
        "review_fingerprint": "b" * 64,
        "status": "completed",
        "review": _review(),
        "suite_sha256": "e" * 64,
        "cases": (_case(),),
        "passed": 1,
        "failed": 0,
        "unscored": 0,
        "pass_rate": 1.0,
        "limitations": ("Deterministic templates cover a bounded domain.",),
    }
    result = MetricRunResult(**payload)
    assert result.policy_version == "1"
    assert result.schema_version == "2.0"

    with pytest.raises(ValidationError, match="counts"):
        MetricRunResult(**(payload | {"passed": 0}))
    with pytest.raises(ValidationError, match="pass_rate"):
        MetricRunResult(**(payload | {"pass_rate": 0.5}))
    with pytest.raises(ValidationError, match="unknown reviewed goal"):
        bad_case = _case().model_copy(
            update={
                "assertions": (
                    _case()
                    .assertions[0]
                    .model_copy(update={"requirement_id": "MISSING"}),
                )
            }
        )
        MetricRunResult(**(payload | {"cases": (bad_case,)}))


def test_zero_denominator_requires_null_rate() -> None:
    result = MetricRunResult(
        run_id="RUN1",
        policy_text_sha256="a" * 64,
        review_fingerprint="b" * 64,
        status="needs_clarification",
        review=MetricReview.model_validate(
            _review().model_dump()
            | {"status": "needs_clarification", "rules": None, "goals": ()}
        ),
        suite_sha256="e" * 64,
        cases=(),
        passed=0,
        failed=0,
        unscored=0,
        pass_rate=None,
        limitations=("No scored cases were produced before review.",),
    )
    assert result.pass_rate is None
