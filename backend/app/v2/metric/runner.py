"""Deterministic state replay, independent assertions, and bounded shrinking."""

from __future__ import annotations

from dataclasses import dataclass, replace

from app.core.hashing import canonical_sha256
from app.v2.metric_contracts import (
    ApproveAction,
    AssertionResult,
    CancelAction,
    ClaimRecord,
    ClaimStatus,
    MetricAction,
    MetricCaseResult,
    MetricReview,
    MetricRules,
    MetricRunResult,
    MetricState,
    ParticipantTotals,
    PayAction,
    PolicyGoal,
    SubmitAction,
    TraceStep,
    UnsupportedAction,
)

from .generator import CaseTemplate, generate_templates

_MAX_CLAIMS = 64
_MAX_PARTICIPANTS = 32
_SUPPORTED_ASSERTION_IDS = frozenset(
    {"G-BUDGET", "G-JOURNEY", "G-CANCELLED", "G-LONE-VALID", "G-AMOUNT"}
)


@dataclass
class _Claim:
    claim_id: str
    participant_id: str
    journey_id: str
    amount_cents: int
    status: ClaimStatus


@dataclass
class _Totals:
    paid_cents: int = 0
    reserved_cents: int = 0


@dataclass
class _Runtime:
    claims: dict[str, _Claim]
    participants: dict[str, _Totals]


def _load_state(state: MetricState) -> tuple[_Runtime | None, str | None]:
    claims = {
        item.claim_id: _Claim(
            item.claim_id,
            item.participant_id,
            item.journey_id,
            item.amount_cents,
            item.status,
        )
        for item in state.claims
    }
    participants = {
        item.participant_id: _Totals(item.paid_cents, item.reserved_cents)
        for item in state.participants
    }
    if any(claim.participant_id not in participants for claim in claims.values()):
        return None, "Initial state claim participants are not fully declared."
    expected = {participant_id: _Totals() for participant_id in participants}
    for claim in claims.values():
        if claim.amount_cents <= 0:
            return None, "Initial state contains a non-positive claim amount."
        totals = expected[claim.participant_id]
        if claim.status is ClaimStatus.PAID:
            totals.paid_cents += claim.amount_cents
        elif claim.status is ClaimStatus.APPROVED:
            totals.reserved_cents += claim.amount_cents
    if any(
        participants[participant_id] != totals
        for participant_id, totals in expected.items()
    ):
        return None, "Initial state counters do not match claim records."
    return _Runtime(claims, participants), None


def _state(runtime: _Runtime) -> MetricState:
    return MetricState(
        claims=tuple(
            ClaimRecord(
                claim_id=claim.claim_id,
                participant_id=claim.participant_id,
                journey_id=claim.journey_id,
                amount_cents=claim.amount_cents,
                status=claim.status,
            )
            for claim in sorted(runtime.claims.values(), key=lambda item: item.claim_id)
        ),
        participants=tuple(
            ParticipantTotals(
                participant_id=participant_id,
                paid_cents=totals.paid_cents,
                reserved_cents=totals.reserved_cents,
            )
            for participant_id, totals in sorted(runtime.participants.items())
        ),
    )


def _participant_for_action(runtime: _Runtime, action: MetricAction) -> str | None:
    if isinstance(action, SubmitAction):
        return action.participant_id
    if isinstance(action, (ApproveAction, PayAction, CancelAction)):
        claim = runtime.claims.get(action.claim_id)
        return None if claim is None else claim.participant_id
    return None


def _sums(runtime: _Runtime, participant_id: str | None) -> tuple[int, int]:
    if participant_id is None:
        return 0, 0
    totals = runtime.participants.get(participant_id, _Totals())
    return totals.paid_cents, totals.reserved_cents


def _apply_submit(
    runtime: _Runtime, rules: MetricRules, action: SubmitAction
) -> tuple[bool, str]:
    if action.claim_id in runtime.claims:
        return False, "The claim ID already exists; the submission was rejected."
    if action.amount_cents <= 0 or action.amount_cents > rules.per_claim_limit_cents:
        return (
            False,
            "The claim amount is outside the configured bounds; the submission was rejected.",
        )
    runtime.participants.setdefault(action.participant_id, _Totals())
    runtime.claims[action.claim_id] = _Claim(
        action.claim_id,
        action.participant_id,
        action.journey_id,
        action.amount_cents,
        ClaimStatus.SUBMITTED,
    )
    return True, "The claim was submitted."


def _apply_approve(
    runtime: _Runtime, rules: MetricRules, action: ApproveAction
) -> tuple[bool, str]:
    claim = runtime.claims.get(action.claim_id)
    if claim is None:
        return False, "The claim does not exist; approval was rejected."
    if claim.status is not ClaimStatus.SUBMITTED:
        return False, "Only a submitted claim can be approved."
    if rules.duplicate_scope == "journey" and any(
        other.claim_id != claim.claim_id
        and other.participant_id == claim.participant_id
        and other.journey_id == claim.journey_id
        and other.status in {ClaimStatus.APPROVED, ClaimStatus.PAID}
        for other in runtime.claims.values()
    ):
        return False, "Another approved or paid claim already covers this journey."
    totals = runtime.participants[claim.participant_id]
    counted = totals.paid_cents
    if rules.approval_budget_accounting == "paid_and_approved":
        counted += totals.reserved_cents
    if counted + claim.amount_cents > rules.participant_allowance_cents:
        return False, "The approval would exceed the participant allowance."
    claim.status = ClaimStatus.APPROVED
    totals.reserved_cents += claim.amount_cents
    return True, "The claim was approved and its amount was reserved."


def _apply_pay(
    runtime: _Runtime, rules: MetricRules, action: PayAction
) -> tuple[bool, str]:
    claim = runtime.claims.get(action.claim_id)
    if claim is None:
        return False, "The claim does not exist; payment was rejected."
    if claim.status is not ClaimStatus.APPROVED:
        return False, "Only an approved unpaid claim can be paid."
    totals = runtime.participants[claim.participant_id]
    if (
        rules.payment_budget_recheck
        and totals.paid_cents + claim.amount_cents > rules.participant_allowance_cents
    ):
        return False, "The payment recheck found that the allowance would be exceeded."
    claim.status = ClaimStatus.PAID
    totals.reserved_cents -= claim.amount_cents
    totals.paid_cents += claim.amount_cents
    return True, "The approved claim was paid once."


def _apply_cancel(runtime: _Runtime, action: CancelAction) -> tuple[bool, str]:
    claim = runtime.claims.get(action.claim_id)
    if claim is None:
        return False, "The claim does not exist; cancellation was rejected."
    if claim.status is ClaimStatus.PAID:
        return False, "A paid claim cannot be cancelled or refunded."
    if claim.status is ClaimStatus.CANCELLED:
        return False, "The claim is already cancelled."
    if claim.status is ClaimStatus.APPROVED:
        runtime.participants[claim.participant_id].reserved_cents -= claim.amount_cents
    claim.status = ClaimStatus.CANCELLED
    return True, "The claim was cancelled and any reservation was released."


def _apply(
    runtime: _Runtime, rules: MetricRules, action: MetricAction
) -> tuple[bool, str]:
    if isinstance(action, SubmitAction):
        return _apply_submit(runtime, rules, action)
    if isinstance(action, ApproveAction):
        return _apply_approve(runtime, rules, action)
    if isinstance(action, PayAction):
        return _apply_pay(runtime, rules, action)
    if isinstance(action, CancelAction):
        return _apply_cancel(runtime, action)
    return False, "The action is unsupported; execution stopped without scoring."


def _capacity_error(runtime: _Runtime, action: MetricAction) -> str | None:
    if not isinstance(action, SubmitAction) or action.claim_id in runtime.claims:
        return None
    if len(runtime.claims) >= _MAX_CLAIMS or (
        action.participant_id not in runtime.participants
        and len(runtime.participants) >= _MAX_PARTICIPANTS
    ):
        return "Execution exceeded the bounded state capacity."
    return None


def _execute(
    rules: MetricRules,
    initial_state: MetricState,
    actions: tuple[MetricAction, ...],
) -> tuple[tuple[TraceStep, ...], MetricState | None, str | None]:
    runtime, invalid_reason = _load_state(initial_state)
    if runtime is None:
        return (), None, invalid_reason
    trace: list[TraceStep] = []
    for index, action in enumerate(actions):
        participant_id = _participant_for_action(runtime, action)
        before = _state(runtime)
        paid_before, reserved_before = _sums(runtime, participant_id)
        capacity_error = _capacity_error(runtime, action)
        if capacity_error is None:
            accepted, detail = _apply(runtime, rules, action)
        else:
            accepted = False
            detail = "The bounded runner cannot add another claim or participant."
        after = _state(runtime)
        paid_after, reserved_after = _sums(runtime, participant_id)
        trace.append(
            TraceStep(
                step_id=f"S{index + 1:02d}",
                action_index=index,
                action=action,
                accepted=accepted,
                detail=detail,
                before_state_sha256=canonical_sha256(before),
                after_state_sha256=canonical_sha256(after),
                participant_paid_cents_before=paid_before,
                participant_paid_cents_after=paid_after,
                participant_reserved_cents_before=reserved_before,
                participant_reserved_cents_after=reserved_after,
            )
        )
        if capacity_error is not None:
            return tuple(trace), after, capacity_error
        if isinstance(action, UnsupportedAction):
            return (
                tuple(trace),
                after,
                "Unsupported action prevents complete execution.",
            )
    return tuple(trace), _state(runtime), None


def _assert_budget(
    goal: PolicyGoal, rules: MetricRules, state: MetricState, refs: tuple[str, ...]
) -> AssertionResult:
    largest = max((item.paid_cents for item in state.participants), default=0)
    passed = largest <= rules.participant_allowance_cents
    actual = (
        f"The largest participant payout was {largest} cents, within the "
        f"{rules.participant_allowance_cents}-cent allowance."
        if passed
        else f"A participant received {largest} cents, above the {rules.participant_allowance_cents}-cent allowance."
    )
    return AssertionResult(
        requirement_id=goal.id,
        passed=passed,
        expected=goal.text,
        actual=actual,
        step_refs=refs,
    )


def _assert_journey(
    goal: PolicyGoal, state: MetricState, refs: tuple[str, ...]
) -> AssertionResult:
    paid_pairs = [
        (claim.participant_id, claim.journey_id)
        for claim in state.claims
        if claim.status is ClaimStatus.PAID
    ]
    duplicates = len(paid_pairs) - len(set(paid_pairs))
    return AssertionResult(
        requirement_id=goal.id,
        passed=duplicates == 0,
        expected=goal.text,
        actual=(
            "No participant received two payments for one journey."
            if duplicates == 0
            else f"The final state contained {duplicates} extra payment for a participant and journey pair."
        ),
        step_refs=refs,
    )


def _assert_cancelled(
    goal: PolicyGoal, trace: tuple[TraceStep, ...], refs: tuple[str, ...]
) -> AssertionResult:
    cancelled: set[str] = set()
    paid_after_cancel: set[str] = set()
    for step in trace:
        if not step.accepted:
            continue
        if isinstance(step.action, CancelAction):
            cancelled.add(step.action.claim_id)
        elif isinstance(step.action, PayAction) and step.action.claim_id in cancelled:
            paid_after_cancel.add(step.action.claim_id)
    return AssertionResult(
        requirement_id=goal.id,
        passed=not paid_after_cancel,
        expected=goal.text,
        actual=(
            "No cancelled claim was paid."
            if not paid_after_cancel
            else "A claim was paid after its accepted cancellation."
        ),
        step_refs=refs,
    )


def _assert_lone_valid(
    goal: PolicyGoal, state: MetricState, refs: tuple[str, ...]
) -> AssertionResult:
    passed = len(state.claims) == 1 and state.claims[0].status is ClaimStatus.PAID
    return AssertionResult(
        requirement_id=goal.id,
        passed=passed,
        expected=goal.text,
        actual=(
            "The lone valid claim reached paid status."
            if passed
            else "The lone valid claim did not reach paid status."
        ),
        step_refs=refs,
    )


def _assert_amount(
    goal: PolicyGoal, rules: MetricRules, state: MetricState, refs: tuple[str, ...]
) -> AssertionResult:
    invalid_paid = [
        claim
        for claim in state.claims
        if claim.status is ClaimStatus.PAID
        and not 1 <= claim.amount_cents <= rules.per_claim_limit_cents
    ]
    return AssertionResult(
        requirement_id=goal.id,
        passed=not invalid_paid,
        expected=goal.text,
        actual=(
            "Every paid claim was within the stated amount bounds."
            if not invalid_paid
            else "A claim outside the stated amount bounds was paid."
        ),
        step_refs=refs,
    )


def _assertions(
    review: MetricReview,
    requirement_ids: tuple[str, ...],
    trace: tuple[TraceStep, ...],
    final_state: MetricState,
) -> tuple[AssertionResult, ...]:
    if review.rules is None:
        return ()
    goals = {goal.id: goal for goal in review.goals}
    refs = tuple(step.step_id for step in trace)
    results: list[AssertionResult] = []
    for requirement_id in requirement_ids:
        goal = goals[requirement_id]
        if requirement_id == "G-BUDGET":
            result = _assert_budget(goal, review.rules, final_state, refs)
        elif requirement_id == "G-JOURNEY":
            result = _assert_journey(goal, final_state, refs)
        elif requirement_id == "G-CANCELLED":
            result = _assert_cancelled(goal, trace, refs)
        elif requirement_id == "G-LONE-VALID":
            result = _assert_lone_valid(goal, final_state, refs)
        elif requirement_id == "G-AMOUNT":
            result = _assert_amount(goal, review.rules, final_state, refs)
        else:  # guarded before replay
            raise ValueError("unsupported reviewed requirement")
        results.append(result)
    return tuple(results)


def _unscored(
    template: CaseTemplate,
    trace: tuple[TraceStep, ...],
    reason: str,
) -> MetricCaseResult:
    return MetricCaseResult(
        case_id=template.case_id,
        title=template.title,
        category=template.category,
        plausibility=template.plausibility,
        initial_state=template.initial_state,
        actions=template.actions,
        trace=trace,
        assertions=(),
        verdict="unscored",
        unscored_reason=reason,
        minimal_actions=None,
    )


def _evaluate_core(review: MetricReview, template: CaseTemplate) -> MetricCaseResult:
    if review.rules is None:
        return _unscored(template, (), "Reviewed executable rules are unavailable.")
    if not template.requirement_ids:
        return _unscored(template, (), "No reviewed requirements were supplied.")
    goal_ids = {goal.id for goal in review.goals}
    if not set(template.requirement_ids) <= goal_ids:
        return _unscored(template, (), "A required reviewed goal is unavailable.")
    if not set(template.requirement_ids) <= _SUPPORTED_ASSERTION_IDS:
        return _unscored(
            template,
            (),
            "Reviewed requirement assertion semantics are unavailable.",
        )
    trace, final_state, error = _execute(
        review.rules, template.initial_state, template.actions
    )
    if error is not None or final_state is None:
        return _unscored(template, trace, error or "Execution was invalid.")
    assertions = _assertions(review, template.requirement_ids, trace, final_state)
    verdict = "pass" if all(assertion.passed for assertion in assertions) else "fail"
    return MetricCaseResult(
        case_id=template.case_id,
        title=template.title,
        category=template.category,
        plausibility=template.plausibility,
        initial_state=template.initial_state,
        actions=template.actions,
        trace=trace,
        assertions=assertions,
        verdict=verdict,
        unscored_reason=None,
        minimal_actions=None,
    )


def _failed_requirements(result: MetricCaseResult) -> frozenset[str]:
    return frozenset(
        assertion.requirement_id
        for assertion in result.assertions
        if not assertion.passed
    )


def _shrink(
    review: MetricReview,
    template: CaseTemplate,
    failures: frozenset[str],
) -> tuple[MetricAction, ...]:
    actions = template.actions
    while len(actions) > 1:
        removed = False
        for index in range(len(actions)):
            candidate_actions = actions[:index] + actions[index + 1 :]
            candidate = _evaluate_core(
                review, replace(template, actions=candidate_actions)
            )
            if (
                candidate.verdict == "fail"
                and _failed_requirements(candidate) == failures
            ):
                actions = candidate_actions
                removed = True
                break
        if not removed:
            break
    return actions


def evaluate_case(
    review: MetricReview,
    template: CaseTemplate,
    *,
    shrink: bool = True,
) -> MetricCaseResult:
    """Replay one case, score cited goals, and optionally shrink failures."""
    result = _evaluate_core(review, template)
    if not shrink or result.verdict != "fail":
        return result
    minimal_actions = _shrink(review, template, _failed_requirements(result))
    return MetricCaseResult.model_validate(
        result.model_dump() | {"minimal_actions": minimal_actions}
    )


def _suite_projection(
    templates: tuple[CaseTemplate, ...],
) -> tuple[dict[str, object], ...]:
    return tuple(
        {
            "case_id": template.case_id,
            "title": template.title,
            "category": str(template.category),
            "plausibility": template.plausibility,
            "initial_state": template.initial_state,
            "actions": template.actions,
            "requirement_ids": template.requirement_ids,
        }
        for template in templates
    )


def execute_metric_suite(review: MetricReview) -> MetricRunResult:
    """Generate and execute the fixed bounded suite for a ready review."""
    if review.rules is None or review.status != "ready":
        raise ValueError("Metric suite requires a ready reviewed policy")
    templates = generate_templates(review.rules)
    suite_sha256 = canonical_sha256(_suite_projection(templates))
    cases = tuple(evaluate_case(review, template) for template in templates)
    passed = sum(case.verdict == "pass" for case in cases)
    failed = sum(case.verdict == "fail" for case in cases)
    unscored = sum(case.verdict == "unscored" for case in cases)
    denominator = passed + failed
    return MetricRunResult(
        run_id=f"metric-{canonical_sha256({'review': review.review_fingerprint, 'suite': suite_sha256})[:16]}",
        policy_text_sha256=review.policy_text_sha256,
        review_fingerprint=review.review_fingerprint,
        generation_method="rule_templates",
        status="completed",
        review=review,
        suite_sha256=suite_sha256,
        cases=cases,
        passed=passed,
        failed=failed,
        unscored=unscored,
        pass_rate=None if denominator == 0 else passed / denominator,
        limitations=(
            "Cases use deterministic rule templates in a bounded reimbursement domain.",
            "Action sequences are ordered and do not model concurrent infrastructure load.",
            "Failed counterexamples are action-deletion 1-minimal, not globally minimal.",
        ),
    )


__all__ = ["CaseTemplate", "evaluate_case", "execute_metric_suite"]
