from __future__ import annotations

from dataclasses import replace

from app.v2.metric.runner import CaseTemplate, evaluate_case
from app.v2.metric.sample import SAMPLE_POLICY
from app.v2.metric.service import prepare_policy, run_metric
from app.v2.metric_contracts import (
    ApproveAction,
    CancelAction,
    ClaimRecord,
    MetricState,
    ParticipantTotals,
    PayAction,
    PolicyGoal,
    SubmitAction,
    UnsupportedAction,
)


def _fixed_policy():
    return SAMPLE_POLICY.model_copy(
        update={
            "description": SAMPLE_POLICY.description.replace(
                "approval_budget_accounting=paid_only",
                "approval_budget_accounting=paid_and_approved",
            )
            .replace("payment_budget_recheck=off", "payment_budget_recheck=on")
            .replace("duplicate_scope=claim_id", "duplicate_scope=journey")
        }
    )


def _budget_fixed_policy():
    return SAMPLE_POLICY.model_copy(
        update={
            "description": SAMPLE_POLICY.description.replace(
                "approval_budget_accounting=paid_only",
                "approval_budget_accounting=paid_and_approved",
            ).replace("payment_budget_recheck=off", "payment_budget_recheck=on")
        }
    )


def _failed_requirements(case) -> set[str]:
    return {
        assertion.requirement_id
        for assertion in case.assertions
        if not assertion.passed
    }


def test_weak_and_fixed_rules_execute_an_identical_bounded_suite() -> None:
    weak_review = prepare_policy(SAMPLE_POLICY)
    fixed_review = prepare_policy(_fixed_policy())
    weak = run_metric(SAMPLE_POLICY, weak_review.review_fingerprint)
    fixed = run_metric(_fixed_policy(), fixed_review.review_fingerprint)

    assert weak.status == fixed.status == "completed"
    assert weak.suite_sha256 == fixed.suite_sha256
    assert [case.actions for case in weak.cases] == [
        case.actions for case in fixed.cases
    ]
    assert 10 <= len(weak.cases) <= 14
    assert {case.category.value for case in weak.cases} == {
        "normal",
        "boundary",
        "compound",
        "cascading",
        "adversarial",
    }
    weak_failures = set().union(*(_failed_requirements(case) for case in weak.cases))
    fixed_failures = set().union(*(_failed_requirements(case) for case in fixed.cases))
    assert {"G-BUDGET", "G-JOURNEY"} <= weak_failures
    assert "G-BUDGET" not in fixed_failures
    assert "G-JOURNEY" not in fixed_failures
    assert weak.passed + weak.failed + weak.unscored == len(weak.cases)
    assert fixed.passed + fixed.failed + fixed.unscored == len(fixed.cases)

    budget_review = prepare_policy(_budget_fixed_policy())
    budget_fixed = run_metric(_budget_fixed_policy(), budget_review.review_fingerprint)
    budget_failures = set().union(
        *(_failed_requirements(case) for case in budget_fixed.cases)
    )
    assert "G-BUDGET" not in budget_failures
    assert "G-JOURNEY" in budget_failures


def test_boundaries_use_integer_cents_and_include_required_sequences() -> None:
    review = prepare_policy(SAMPLE_POLICY)
    result = run_metric(SAMPLE_POLICY, review.review_fingerprint)
    by_id = {case.case_id: case for case in result.cases}

    exact = by_id["boundary-exact-limit"].actions[0]
    over = by_id["boundary-over-limit"].actions[0]
    zero = by_id["boundary-zero"].actions[0]
    assert isinstance(exact, SubmitAction) and exact.amount_cents == 10_000
    assert isinstance(over, SubmitAction) and over.amount_cents == 10_001
    assert isinstance(zero, SubmitAction) and zero.amount_cents == 0
    assert by_id["normal-lone-valid"].verdict == "pass"
    assert by_id["cascading-cancel-release"].verdict == "pass"
    assert by_id["adversarial-extreme-interleaving"].category == "adversarial"


def test_rejected_actions_are_atomic_and_cancellation_releases_reservation() -> None:
    review = prepare_policy(_fixed_policy())
    actions = (
        SubmitAction(
            claim_id="C1", participant_id="P1", journey_id="J1", amount_cents=500
        ),
        ApproveAction(claim_id="C1"),
        SubmitAction(
            claim_id="C1", participant_id="P1", journey_id="J2", amount_cents=600
        ),
        CancelAction(claim_id="C1"),
        PayAction(claim_id="C1"),
    )
    case = evaluate_case(
        review,
        CaseTemplate(
            case_id="atomic-cancel",
            title="Atomic rejection and cancellation",
            category="cascading",
            plausibility="A participant corrects a claim after cancellation.",
            initial_state=MetricState(),
            actions=actions,
            requirement_ids=("G-CANCELLED", "G-BUDGET"),
        ),
    )

    assert [step.accepted for step in case.trace] == [True, True, False, True, False]
    assert case.trace[2].before_state_sha256 == case.trace[2].after_state_sha256
    assert case.trace[3].participant_reserved_cents_before == 500
    assert case.trace[3].participant_reserved_cents_after == 0
    assert case.trace[4].before_state_sha256 == case.trace[4].after_state_sha256
    assert case.verdict == "pass"


def test_unknown_action_invalid_state_and_missing_requirements_are_unscored() -> None:
    review = prepare_policy(SAMPLE_POLICY)
    base = CaseTemplate(
        case_id="unsupported",
        title="Unsupported execution",
        category="adversarial",
        plausibility="A malformed external scenario is rejected as unscored.",
        initial_state=MetricState(),
        actions=(UnsupportedAction(action="refund", parameters=("C1",)),),
        requirement_ids=("G-BUDGET",),
    )
    unknown = evaluate_case(review, base)
    assert unknown.verdict == "unscored"
    assert unknown.assertions == ()
    assert unknown.unscored_reason == "Unsupported action prevents complete execution."

    invalid_state = MetricState(
        claims=(
            ClaimRecord(
                claim_id="C1",
                participant_id="P1",
                journey_id="J1",
                amount_cents=100,
                status="approved",
            ),
        ),
        participants=(
            ParticipantTotals(participant_id="P1", paid_cents=0, reserved_cents=0),
        ),
    )
    invalid = evaluate_case(review, replace(base, initial_state=invalid_state))
    assert invalid.verdict == "unscored"
    assert (
        invalid.unscored_reason == "Initial state counters do not match claim records."
    )

    missing = evaluate_case(
        review,
        replace(base, actions=(PayAction(claim_id="C1"),), requirement_ids=()),
    )
    assert missing.verdict == "unscored"
    assert missing.unscored_reason == "No reviewed requirements were supplied."


def test_state_capacity_exhaustion_is_unscored_and_preserves_prior_trace() -> None:
    review = prepare_policy(SAMPLE_POLICY)
    full_claim_state = MetricState(
        claims=tuple(
            ClaimRecord(
                claim_id=f"C{index}",
                participant_id="P0",
                journey_id=f"J{index}",
                amount_cents=1,
                status="submitted",
            )
            for index in range(64)
        ),
        participants=(
            ParticipantTotals(participant_id="P0", paid_cents=0, reserved_cents=0),
        ),
    )
    claim_capacity = evaluate_case(
        review,
        CaseTemplate(
            case_id="claim-capacity",
            title="Claim capacity",
            category="adversarial",
            plausibility="A bounded runner receives one more valid claim.",
            initial_state=full_claim_state,
            actions=(
                ApproveAction(claim_id="C0"),
                SubmitAction(
                    claim_id="CNEW",
                    participant_id="P0",
                    journey_id="JNEW",
                    amount_cents=1,
                ),
            ),
            requirement_ids=("G-BUDGET",),
        ),
    )
    assert claim_capacity.verdict == "unscored"
    assert claim_capacity.unscored_reason == (
        "Execution exceeded the bounded state capacity."
    )
    assert [step.accepted for step in claim_capacity.trace] == [True, False]
    assert (
        claim_capacity.trace[0].after_state_sha256
        == claim_capacity.trace[1].before_state_sha256
        == claim_capacity.trace[1].after_state_sha256
    )
    assert claim_capacity.trace[-1].participant_reserved_cents_after == 1

    full_participant_state = MetricState(
        claims=tuple(
            ClaimRecord(
                claim_id=f"PC{index}",
                participant_id=f"P{index}",
                journey_id=f"PJ{index}",
                amount_cents=1,
                status="submitted",
            )
            for index in range(32)
        ),
        participants=tuple(
            ParticipantTotals(
                participant_id=f"P{index}", paid_cents=0, reserved_cents=0
            )
            for index in range(32)
        ),
    )
    participant_capacity = evaluate_case(
        review,
        CaseTemplate(
            case_id="participant-capacity",
            title="Participant capacity",
            category="adversarial",
            plausibility="A bounded runner receives one more participant.",
            initial_state=full_participant_state,
            actions=(
                SubmitAction(
                    claim_id="PCNEW",
                    participant_id="PNEW",
                    journey_id="PJNEW",
                    amount_cents=1,
                ),
            ),
            requirement_ids=("G-BUDGET",),
        ),
    )
    assert participant_capacity.verdict == "unscored"
    assert participant_capacity.unscored_reason == (
        "Execution exceeded the bounded state capacity."
    )
    assert participant_capacity.trace[0].accepted is False
    assert (
        participant_capacity.trace[0].before_state_sha256
        == participant_capacity.trace[0].after_state_sha256
    )


def test_reviewed_goal_without_assertion_semantics_is_unscored() -> None:
    review = prepare_policy(SAMPLE_POLICY)
    custom_goal = PolicyGoal(
        id="G-CUSTOM",
        text="A custom reviewed outcome is required.",
        clause_ids=("C-AMOUNT",),
    )
    custom_review = type(review).model_validate(
        review.model_dump() | {"goals": (*review.goals, custom_goal)}
    )
    result = evaluate_case(
        custom_review,
        CaseTemplate(
            case_id="custom-goal",
            title="Unavailable assertion semantics",
            category="adversarial",
            plausibility="A reviewed custom goal has no deterministic assertion.",
            initial_state=MetricState(),
            actions=(PayAction(claim_id="MISSING"),),
            requirement_ids=("G-CUSTOM",),
        ),
    )
    assert result.verdict == "unscored"
    assert result.assertions == ()
    assert result.unscored_reason == (
        "Reviewed requirement assertion semantics are unavailable."
    )


def test_failed_counterexample_is_action_deletion_one_minimal() -> None:
    review = prepare_policy(SAMPLE_POLICY)
    result = run_metric(SAMPLE_POLICY, review.review_fingerprint)
    failed = next(
        case for case in result.cases if case.case_id == "compound-two-approvals"
    )
    assert failed.verdict == "fail"
    assert failed.minimal_actions
    required_failures = _failed_requirements(failed)

    template = CaseTemplate(
        case_id="minimal-check",
        title="Minimal check",
        category="compound",
        plausibility="The reduced sequence is checked one deletion at a time.",
        initial_state=failed.initial_state,
        actions=failed.minimal_actions,
        requirement_ids=tuple(sorted(required_failures)),
    )
    for index in range(len(template.actions)):
        candidate = evaluate_case(
            review,
            replace(
                template,
                actions=template.actions[:index] + template.actions[index + 1 :],
            ),
            shrink=False,
        )
        assert (
            candidate.verdict != "fail"
            or _failed_requirements(candidate) != required_failures
        )


def test_maximum_supported_numeric_policy_does_not_overflow_observable_state() -> None:
    extreme = SAMPLE_POLICY.model_copy(
        update={
            "description": SAMPLE_POLICY.description.replace(
                "per_claim_limit_cents=10000", "per_claim_limit_cents=10000000"
            ).replace(
                "participant_allowance_cents=15000",
                "participant_allowance_cents=100000000",
            )
        }
    )
    review = prepare_policy(extreme)
    result = run_metric(extreme, review.review_fingerprint)
    assert result.status == "completed"
    assert result.passed + result.failed + result.unscored == len(result.cases)

    approved = tuple(
        ClaimRecord(
            claim_id=f"MAX{index}",
            participant_id="PMAX",
            journey_id=f"JMAX{index}",
            amount_cents=10_000_000,
            status="approved",
        )
        for index in range(11)
    )
    overspend_case = evaluate_case(
        review,
        CaseTemplate(
            case_id="maximum-observable-overspend",
            title="Maximum supported observable overspend",
            category="adversarial",
            plausibility="Previously approved maximum claims are paid in bounded order.",
            initial_state=MetricState(
                claims=approved,
                participants=(
                    ParticipantTotals(
                        participant_id="PMAX",
                        paid_cents=0,
                        reserved_cents=110_000_000,
                    ),
                ),
            ),
            actions=tuple(PayAction(claim_id=claim.claim_id) for claim in approved),
            requirement_ids=("G-BUDGET",),
        ),
    )
    assert overspend_case.verdict == "fail"
    assert overspend_case.trace[-1].participant_paid_cents_after == 110_000_000
