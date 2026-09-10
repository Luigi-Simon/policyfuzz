"""Stable numeric rule templates for the bounded reimbursement domain."""

from __future__ import annotations

from dataclasses import dataclass

from app.v2.metric_contracts import (
    ApproveAction,
    CancelAction,
    CaseCategory,
    MetricAction,
    MetricRules,
    MetricState,
    PayAction,
    SubmitAction,
)


@dataclass(frozen=True)
class CaseTemplate:
    case_id: str
    title: str
    category: CaseCategory | str
    plausibility: str
    initial_state: MetricState
    actions: tuple[MetricAction, ...]
    requirement_ids: tuple[str, ...]


def _claim(claim_id: str, participant: str, journey: str, amount: int):
    return SubmitAction(
        claim_id=claim_id,
        participant_id=participant,
        journey_id=journey,
        amount_cents=amount,
    )


def _lifecycle(claim_id: str, participant: str, journey: str, amount: int):
    return (
        _claim(claim_id, participant, journey, amount),
        ApproveAction(claim_id=claim_id),
        PayAction(claim_id=claim_id),
    )


def generate_templates(rules: MetricRules) -> tuple[CaseTemplate, ...]:
    """Generate cases from numeric limits only, independent of safety flags."""
    limit = rules.per_claim_limit_cents
    allowance = rules.participant_allowance_cents
    safe = min(limit, allowance)
    overspend = min(limit, allowance // 2 + 1)
    duplicate = min(limit, max(1, allowance // 2))
    secondary = min(limit, max(1, allowance // 3))
    empty = MetricState()
    return (
        CaseTemplate(
            "normal-lone-valid",
            "Lone valid claim",
            "normal",
            "One participant submits and completes one claim within both limits.",
            empty,
            _lifecycle("C01", "P01", "J01", safe),
            ("G-LONE-VALID", "G-BUDGET", "G-AMOUNT"),
        ),
        CaseTemplate(
            "boundary-exact-limit",
            "Exact per-claim limit",
            "boundary",
            "A claim uses the exact configured per-claim limit.",
            empty,
            _lifecycle("C02", "P02", "J02", limit),
            ("G-AMOUNT", "G-BUDGET"),
        ),
        CaseTemplate(
            "boundary-over-limit",
            "Above per-claim limit",
            "boundary",
            "A claim exceeds the configured per-claim limit by one cent.",
            empty,
            _lifecycle("C03", "P03", "J03", limit + 1),
            ("G-AMOUNT",),
        ),
        CaseTemplate(
            "boundary-zero",
            "Zero-value claim",
            "boundary",
            "A participant attempts a zero-value claim.",
            empty,
            _lifecycle("C04", "P04", "J04", 0),
            ("G-AMOUNT",),
        ),
        CaseTemplate(
            "compound-two-approvals",
            "Two approvals before payment",
            "compound",
            "One participant obtains two approvals before either payment is attempted.",
            empty,
            (
                _claim("C05A", "P05", "J05A", overspend),
                _claim("C05B", "P05", "J05B", overspend),
                ApproveAction(claim_id="C05A"),
                ApproveAction(claim_id="C05B"),
                PayAction(claim_id="C05A"),
                PayAction(claim_id="C05B"),
            ),
            ("G-BUDGET",),
        ),
        CaseTemplate(
            "compound-same-journey",
            "Distinct claims for one journey",
            "compound",
            "One participant submits distinct claim IDs for the same journey.",
            empty,
            (
                _claim("C06A", "P06", "J06", duplicate),
                _claim("C06B", "P06", "J06", duplicate),
                ApproveAction(claim_id="C06A"),
                ApproveAction(claim_id="C06B"),
                PayAction(claim_id="C06A"),
                PayAction(claim_id="C06B"),
            ),
            ("G-JOURNEY", "G-BUDGET"),
        ),
        CaseTemplate(
            "cascading-payment-retry",
            "Repeated payment attempt",
            "cascading",
            "A participant retries payment after a completed payment.",
            empty,
            _lifecycle("C07", "P07", "J07", safe) + (PayAction(claim_id="C07"),),
            ("G-JOURNEY", "G-BUDGET"),
        ),
        CaseTemplate(
            "cascading-cancel-release",
            "Cancellation releases approval",
            "cascading",
            "An approved claim is cancelled before a replacement claim is submitted.",
            empty,
            (
                _claim("C08A", "P08", "J08A", safe),
                ApproveAction(claim_id="C08A"),
                CancelAction(claim_id="C08A"),
                _claim("C08B", "P08", "J08B", safe),
                ApproveAction(claim_id="C08B"),
                PayAction(claim_id="C08B"),
            ),
            ("G-CANCELLED", "G-BUDGET"),
        ),
        CaseTemplate(
            "normal-two-participants",
            "Independent participant allowances",
            "normal",
            "Two participants independently submit claims against their own allowances.",
            empty,
            (
                _claim("C09A", "P09A", "J09A", safe),
                _claim("C09B", "P09B", "J09B", safe),
                ApproveAction(claim_id="C09A"),
                ApproveAction(claim_id="C09B"),
                PayAction(claim_id="C09A"),
                PayAction(claim_id="C09B"),
            ),
            ("G-BUDGET",),
        ),
        CaseTemplate(
            "adversarial-claim-replay",
            "Claim identifier replay",
            "adversarial",
            "A participant reuses a claim ID with different journey details.",
            empty,
            (
                _claim("C10", "P10", "J10A", safe),
                _claim("C10", "P10", "J10B", secondary),
                ApproveAction(claim_id="C10"),
                PayAction(claim_id="C10"),
            ),
            ("G-BUDGET", "G-JOURNEY", "G-AMOUNT"),
        ),
        CaseTemplate(
            "adversarial-cancel-paid",
            "Cancellation after payment",
            "adversarial",
            "A participant attempts to cancel a claim after payment.",
            empty,
            _lifecycle("C11", "P11", "J11", safe) + (CancelAction(claim_id="C11"),),
            ("G-CANCELLED", "G-BUDGET"),
        ),
        CaseTemplate(
            "adversarial-extreme-interleaving",
            "Interleaved approvals, duplicate journey, cancellation, and retry",
            "adversarial",
            "Two participants create an extreme but plausible ordered combination of claims.",
            empty,
            (
                _claim("C12A", "P12A", "J12X", overspend),
                _claim("C12B", "P12A", "J12X", overspend),
                _claim("C12C", "P12A", "J12Y", overspend),
                _claim("C12D", "P12B", "J12Z", safe),
                ApproveAction(claim_id="C12A"),
                ApproveAction(claim_id="C12B"),
                ApproveAction(claim_id="C12C"),
                CancelAction(claim_id="C12C"),
                ApproveAction(claim_id="C12D"),
                PayAction(claim_id="C12A"),
                PayAction(claim_id="C12B"),
                PayAction(claim_id="C12B"),
                CancelAction(claim_id="C12C"),
                _claim("C12E", "P12A", "J12Y", secondary),
                ApproveAction(claim_id="C12E"),
                PayAction(claim_id="C12E"),
                PayAction(claim_id="C12D"),
            ),
            ("G-BUDGET", "G-JOURNEY", "G-CANCELLED"),
        ),
    )


__all__ = ["CaseTemplate", "generate_templates"]
