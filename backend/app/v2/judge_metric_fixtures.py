"""Authored Metric evidence for Judge adapter tests; this does not run a policy."""

from app.core.hashing import canonical_sha256

from .metric.parser import prepare
from .metric_contracts import (
    ApproveAction,
    AssertionResult,
    ClaimRecord,
    MetricCaseResult,
    MetricRunResult,
    MetricState,
    ParticipantTotals,
    PayAction,
    SubmitAction,
    TraceStep,
)
from .run_models import RunPolicyInput


def _snapshot(statuses: tuple[str, ...], paid: int, reserved: int) -> MetricState:
    """Serialize a declared fixture snapshot; no policy rules are evaluated."""
    if not statuses:
        return MetricState()
    return MetricState(
        claims=tuple(
            ClaimRecord(
                claim_id=f"C{index}",
                participant_id="P1",
                journey_id=f"J{index}",
                amount_cents=10_000,
                status=status,
            )
            for index, status in enumerate(statuses, 1)
        ),
        participants=(
            ParticipantTotals(
                participant_id="P1",
                paid_cents=paid,
                reserved_cents=reserved,
            ),
        ),
    )


def _case(two_claims: bool) -> MetricCaseResult:
    submit = lambda index: SubmitAction(
        claim_id=f"C{index}",
        participant_id="P1",
        journey_id=f"J{index}",
        amount_cents=10_000,
    )
    if two_claims:
        actions = (
            submit(1),
            submit(2),
            ApproveAction(claim_id="C1"),
            ApproveAction(claim_id="C2"),
            PayAction(claim_id="C1"),
            PayAction(claim_id="C2"),
        )
        declarations = (
            ((), 0, 0),
            (("submitted",), 0, 0),
            (("submitted", "submitted"), 0, 0),
            (("approved", "submitted"), 0, 10_000),
            (("approved", "approved"), 0, 20_000),
            (("paid", "approved"), 10_000, 10_000),
            (("paid", "paid"), 20_000, 0),
        )
    else:
        actions = (submit(1), ApproveAction(claim_id="C1"), PayAction(claim_id="C1"))
        declarations = (
            ((), 0, 0),
            (("submitted",), 0, 0),
            (("approved",), 0, 10_000),
            (("paid",), 10_000, 0),
        )
    snapshots = tuple(_snapshot(*item) for item in declarations)
    trace = tuple(
        TraceStep(
            step_id=f"S{index + 1}",
            action_index=index,
            action=action,
            accepted=True,
            detail=f"Authored fixture: {action.action} {action.claim_id} is shown as accepted.",
            before_state_sha256=canonical_sha256(snapshots[index]),
            after_state_sha256=canonical_sha256(snapshots[index + 1]),
            participant_paid_cents_before=declarations[index][1],
            participant_paid_cents_after=declarations[index + 1][1],
            participant_reserved_cents_before=declarations[index][2],
            participant_reserved_cents_after=declarations[index + 1][2],
        )
        for index, action in enumerate(actions)
    )
    return MetricCaseResult(
        case_id="fixture-budget-failure" if two_claims else "fixture-valid-claim",
        title="Authored budget failure" if two_claims else "Authored passing claim",
        category="compound" if two_claims else "normal",
        plausibility="Synthetic adapter fixture only: two approvals before payment."
        if two_claims
        else "Synthetic adapter fixture only: one valid claim is paid.",
        initial_state=snapshots[0],
        actions=actions,
        trace=trace,
        assertions=(
            AssertionResult(
                requirement_id="G-BUDGET",
                passed=not two_claims,
                expected="Participant payouts are at most SGD 150.00.",
                actual="Authored fixture payout: SGD 200.00."
                if two_claims
                else "Authored fixture payout: SGD 100.00.",
                step_refs=(trace[-1].step_id,),
            ),
        ),
        verdict="fail" if two_claims else "pass",
    )


def make_metric_fixture(policy: RunPolicyInput, run_id: str) -> MetricRunResult:
    review = prepare(policy)
    ready = review.status == "ready"
    cases = (_case(False), _case(True)) if ready else ()
    suite = tuple({"case_id": c.case_id, "actions": c.actions} for c in cases)
    return MetricRunResult(
        run_id=run_id,
        policy_text_sha256=review.policy_text_sha256,
        review_fingerprint=review.review_fingerprint,
        generation_method="authored_fixture",
        status="completed" if ready else "needs_clarification",
        review=review,
        suite_sha256=canonical_sha256(suite),
        cases=cases,
        passed=1 if ready else 0,
        failed=1 if ready else 0,
        unscored=0,
        pass_rate=0.5 if ready else None,
        limitations=(
            "Authored Metric fixture for Judge adapter development; no policy runner or generator was executed.",
        ),
    )
