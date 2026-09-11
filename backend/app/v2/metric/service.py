"""Bounded rule-template generation and deterministic reimbursement execution."""

from collections import Counter

from app.core.hashing import canonical_sha256
from app.v2.metric_contracts import (
    ApproveAction,
    AssertionResult,
    CancelAction,
    ClaimRecord,
    MetricCaseResult,
    MetricRules,
    MetricRunResult,
    MetricState,
    ParticipantTotals,
    PayAction,
    SubmitAction,
    TraceStep,
)

from .conditions import run_policy_conditions
from .parser import prepare


def _state(claims):
    ids = sorted({claim.participant_id for claim in claims.values()})
    return MetricState(
        claims=tuple(claims[key] for key in sorted(claims)),
        participants=tuple(
            ParticipantTotals(
                participant_id=pid,
                paid_cents=sum(
                    c.amount_cents
                    for c in claims.values()
                    if c.participant_id == pid and c.status == "paid"
                ),
                reserved_cents=sum(
                    c.amount_cents
                    for c in claims.values()
                    if c.participant_id == pid and c.status == "approved"
                ),
            )
            for pid in ids
        ),
    )


def _totals(state, pid):
    return next(
        (p for p in state.participants if p.participant_id == pid),
        ParticipantTotals(participant_id=pid, paid_cents=0, reserved_cents=0),
    )


def _apply(claims, action, rules):
    if not isinstance(action, (SubmitAction, ApproveAction, PayAction, CancelAction)):
        return False, "Action is outside the supported execution domain."
    claim = claims.get(action.claim_id)
    if isinstance(action, SubmitAction):
        if claim is not None:
            return False, "Claim ID already exists."
        if not 0 < action.amount_cents <= rules.per_claim_limit_cents:
            return False, "Amount is outside the per-claim bounds."
        if rules.duplicate_scope == "journey" and any(
            c.participant_id == action.participant_id
            and c.journey_id == action.journey_id
            and c.status != "cancelled"
            for c in claims.values()
        ):
            return False, "A claim already exists for this participant and journey."
        claims[action.claim_id] = ClaimRecord(
            **action.model_dump(exclude={"action"}), status="submitted"
        )
        return True, "Claim submitted."
    if claim is None:
        return False, "Claim does not exist."
    totals = _totals(_state(claims), claim.participant_id)
    if isinstance(action, ApproveAction):
        if claim.status != "submitted":
            return False, "Approval requires a submitted claim."
        used = totals.paid_cents
        if rules.approval_budget_accounting == "paid_and_approved":
            used += totals.reserved_cents
        if used + claim.amount_cents > rules.participant_allowance_cents:
            return False, "Approval would exceed the configured allowance basis."
        status = "approved"
    elif isinstance(action, PayAction):
        if claim.status != "approved":
            return False, "Payment requires an approved, unpaid claim."
        if rules.payment_budget_recheck and (
            totals.paid_cents + claim.amount_cents > rules.participant_allowance_cents
        ):
            return False, "Payment would exceed the participant allowance."
        status = "paid"
    else:
        if claim.status not in {"submitted", "approved"}:
            return False, "Only submitted or approved claims can be cancelled."
        status = "cancelled"
    claims[action.claim_id] = claim.model_copy(update={"status": status})
    return True, f"Claim {status}."


def run_case(review, case_id, title, category, circumstances, actions, requirements):
    """Run from an empty state; score only explicitly cited, supported goals."""
    claims, trace, snapshots = {}, [], []
    known_goals = {goal.id for goal in review.goals}
    supported_goals = {
        "G-BUDGET",
        "G-JOURNEY",
        "G-CANCELLED",
        "G-AMOUNT",
        "G-LONE-VALID",
    }
    unsupported = (
        not isinstance(review.rules, MetricRules)
        or not requirements
        or not set(requirements) <= known_goals & supported_goals
        or any(
            not isinstance(
                action, (SubmitAction, ApproveAction, PayAction, CancelAction)
            )
            for action in actions
        )
    )
    cancelled_ids = set()
    paid_cancelled = False
    for index, action in enumerate(actions):
        before = _state(claims)
        claim = claims.get(getattr(action, "claim_id", ""))
        pid = (
            action.participant_id
            if isinstance(action, SubmitAction)
            else (claim.participant_id if claim else "P1")
        )
        paid_before = _totals(before, pid)
        accepted, detail = (
            _apply(claims, action, review.rules)
            if isinstance(review.rules, MetricRules)
            else (False, "Executable policy interpretation is unavailable.")
        )
        if accepted and isinstance(action, CancelAction):
            cancelled_ids.add(action.claim_id)
        if (
            accepted
            and isinstance(action, PayAction)
            and action.claim_id in cancelled_ids
        ):
            paid_cancelled = True
        after = _state(claims)
        snapshots.append(after)
        paid_after = _totals(after, pid)
        trace.append(
            TraceStep(
                step_id=f"S{index + 1}",
                action_index=index,
                action=action,
                accepted=accepted,
                detail=detail,
                before_state_sha256=canonical_sha256(before),
                after_state_sha256=canonical_sha256(after),
                participant_paid_cents_before=paid_before.paid_cents,
                participant_paid_cents_after=paid_after.paid_cents,
                participant_reserved_cents_before=paid_before.reserved_cents,
                participant_reserved_cents_after=paid_after.reserved_cents,
            )
        )
    assertions = []
    if not unsupported:
        max_paid = max(
            (p.paid_cents for s in snapshots for p in s.participants), default=0
        )
        paid_claims = [c for c in claims.values() if c.status == "paid"]
        journeys = Counter((c.participant_id, c.journey_id) for c in paid_claims)
        checks = {
            "G-BUDGET": (
                max_paid <= review.rules.participant_allowance_cents,
                f"Each participant's payouts remain at most {review.rules.participant_allowance_cents} SGD cents.",
                f"Maximum participant payout observed: {max_paid} SGD cents.",
            ),
            "G-JOURNEY": (
                max(journeys.values(), default=0) <= 1,
                "At most one payment per participant and journey.",
                f"Maximum payments per participant and journey: {max(journeys.values(), default=0)}.",
            ),
            "G-CANCELLED": (
                not paid_cancelled,
                "Cancelled claims are never paid.",
                f"Payment of a previously cancelled claim observed: {paid_cancelled}.",
            ),
            "G-AMOUNT": (
                all(
                    0 < c.amount_cents <= review.rules.per_claim_limit_cents
                    for c in paid_claims
                ),
                "Payments respect the stated amount bounds.",
                f"Paid amounts in SGD cents: {[c.amount_cents for c in paid_claims]}.",
            ),
            "G-LONE-VALID": (
                len(paid_claims) == 1,
                "The lone valid claim receives one payment.",
                f"Paid claims observed: {len(paid_claims)}.",
            ),
        }
        for goal in requirements:
            passed, expected, actual = checks[goal]
            assertions.append(
                AssertionResult(
                    requirement_id=goal,
                    passed=passed,
                    expected=expected,
                    actual=actual,
                    step_refs=tuple(step.step_id for step in trace),
                )
            )
    return MetricCaseResult(
        case_id=case_id,
        title=title,
        category=category,
        plausibility=circumstances,
        initial_state=MetricState(),
        actions=actions,
        trace=tuple(trace),
        assertions=tuple(assertions),
        verdict="unscored"
        if unsupported
        else ("pass" if all(a.passed for a in assertions) else "fail"),
        unscored_reason="No supported, reviewed assertion is available for every action."
        if unsupported
        else None,
    )


def templates(rules):
    """Neutral circumstances may enter Sandbox; assertions and results must not."""
    amount = min(rules.per_claim_limit_cents, rules.participant_allowance_cents)
    overlap = min(
        rules.per_claim_limit_cents, rules.participant_allowance_cents // 2 + 1
    )
    duplicate = max(
        1, min(rules.per_claim_limit_cents, rules.participant_allowance_cents // 3)
    )

    def submit(n=1, cents=amount, journey=None, participant="P1"):
        return SubmitAction(
            claim_id=f"C{n}",
            participant_id=participant,
            journey_id=journey or f"J{n}",
            amount_cents=cents,
        )

    def pay(n=1):
        return (ApproveAction(claim_id=f"C{n}"), PayAction(claim_id=f"C{n}"))

    common = ("G-BUDGET", "G-JOURNEY", "G-CANCELLED", "G-AMOUNT")
    return (
        (
            "normal-claim",
            "One valid claim",
            "normal",
            "A participant submits one ordinary reimbursement claim.",
            (submit(), *pay()),
            (*common, "G-LONE-VALID"),
        ),
        (
            "zero-amount",
            "Zero amount",
            "boundary",
            "A participant submits a claim with a zero amount.",
            (submit(cents=0), *pay()),
            common,
        ),
        (
            "above-claim-limit",
            "Amount above the claim limit",
            "boundary",
            "A claim amount is one cent above the stated per-claim limit.",
            (submit(cents=rules.per_claim_limit_cents + 1), *pay()),
            common,
        ),
        (
            "overlapping-approvals",
            "Overlapping approvals",
            "compound",
            "Two claims for different journeys are approved before either payment is processed.",
            (
                submit(cents=overlap),
                submit(2, overlap),
                ApproveAction(claim_id="C1"),
                ApproveAction(claim_id="C2"),
                PayAction(claim_id="C1"),
                PayAction(claim_id="C2"),
            ),
            common,
        ),
        (
            "duplicate-journey",
            "Two claims for one journey",
            "adversarial",
            "A participant uses distinct claim IDs for the same journey.",
            (submit(cents=duplicate), *pay(), submit(2, duplicate, "J1"), *pay(2)),
            common,
        ),
        (
            "cancel-then-pay",
            "Cancellation before payment",
            "cascading",
            "An approved claim is cancelled before a payment request arrives.",
            (
                submit(),
                ApproveAction(claim_id="C1"),
                CancelAction(claim_id="C1"),
                PayAction(claim_id="C1"),
            ),
            common,
        ),
        (
            "cancel-release",
            "Cancellation and a new claim",
            "cascading",
            "An approval is cancelled and a different journey claim follows.",
            (
                submit(),
                ApproveAction(claim_id="C1"),
                CancelAction(claim_id="C1"),
                submit(2),
                *pay(2),
            ),
            common,
        ),
        (
            "duplicate-claim-id",
            "Resubmission of a claim ID",
            "adversarial",
            "A participant resubmits an already paid claim ID.",
            (submit(), *pay(), submit(), *pay()),
            common,
        ),
        (
            "repeated-payment",
            "Repeated payment request",
            "adversarial",
            "The same payment request arrives twice.",
            (submit(), *pay(), PayAction(claim_id="C1")),
            common,
        ),
        (
            "premature-payment",
            "Payment before approval",
            "compound",
            "A payment request arrives before the claim's approval.",
            (submit(), PayAction(claim_id="C1"), *pay()),
            common,
        ),
        (
            "independent-participants",
            "Separate participant allowances",
            "normal",
            "Two participants each submit one claim for different journeys.",
            (submit(), *pay(), submit(2, participant="P2"), *pay(2)),
            common,
        ),
        (
            "negative-amount",
            "Negative claim amount",
            "boundary",
            "A participant submits a negative claim amount.",
            (submit(cents=-1), *pay()),
            common,
        ),
    )


def run_metric(policy, run_id, *, test_budget=12):
    if type(test_budget) is not int or not 1 <= test_budget <= 12:
        raise ValueError("Metric test budget must be between 1 and 12")
    review = prepare(policy)
    if review.rules is None and not policy.description.lstrip().startswith(
        "POLICY_FORMAT="
    ):
        prose = run_policy_conditions(policy, run_id, test_budget=test_budget)
        if prose is not None:
            return prose
        from .scenarios import plan_scenarios

        return plan_scenarios(policy, run_id, review, test_budget=test_budget)
    plans = templates(review.rules)[:test_budget] if review.rules else ()
    cases = []
    for case_id, title, category, circumstances, actions, requirements in plans:
        result = run_case(
            review, case_id, title, category, circumstances, actions, requirements
        )
        if result.verdict == "fail":
            # Preserve a specific violated goal while reducing, so the reduction
            # cannot turn into a different (for example, liveness) failure.
            violated = tuple(
                a.requirement_id for a in result.assertions if not a.passed
            )
            minimal, index = actions, 0
            while index < len(minimal) and len(minimal) > 1:
                candidate = minimal[:index] + minimal[index + 1 :]
                reduced = run_case(
                    review, case_id, title, category, circumstances, candidate, violated
                )
                if reduced.verdict == "fail":
                    minimal, index = candidate, 0
                else:
                    index += 1
            result = result.model_copy(update={"minimal_actions": minimal})
        cases.append(result)
    passed = sum(c.verdict == "pass" for c in cases)
    failed = sum(c.verdict == "fail" for c in cases)
    return MetricRunResult(
        run_id=run_id,
        policy_text_sha256=review.policy_text_sha256,
        review_fingerprint=review.review_fingerprint,
        review=review,
        status="completed" if review.rules else "needs_clarification",
        suite_sha256=canonical_sha256(plans),
        cases=tuple(cases),
        passed=passed,
        failed=failed,
        unscored=sum(c.verdict == "unscored" for c in cases),
        pass_rate=passed / (passed + failed) if passed + failed else None,
        limitations=(
            *review.limitations,
            "Finite deterministic rule templates are not exhaustive policy testing.",
            "Counterexamples are minimal under action deletion, not globally minimal.",
            *(
                ("The selected test budget omits some template categories.",)
                if test_budget < 12
                else ()
            ),
        ),
    )
