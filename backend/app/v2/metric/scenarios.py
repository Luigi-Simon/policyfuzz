"""Bounded, unscored scenario planning when no executable interpretation exists.

Topic matches select questions, never requirements or expected outcomes. Source
offsets and hashes bind matches without publishing the submitted policy text.
"""

import hashlib
import re

from app.core.hashing import canonical_sha256
from app.v2.metric_contracts import (
    MetricCaseResult,
    MetricRunResult,
    MetricState,
    UnsupportedAction,
)

_TOPICS = (
    (
        r"\b(disconnect|after.hours|blackout|delayed sending)\b",
        "Communication window",
        "boundary",
        "A message arrives just before, at, or just after a communication window, including a cross-timezone recipient.",
    ),
    (
        r"\b(rest|shift|working hours|work week|workweek)\b",
        "Hours and rest",
        "boundary",
        "A participant's schedule crosses a working-hours or rest boundary; include an overnight shift.",
    ),
    (
        r"\b(overtime|standby|compensation)\b",
        "Standby and compensation",
        "compound",
        "A participant monitors messages on standby and then handles a work request; examine how the two activities are recorded.",
    ),
    (
        r"\b(retaliation|discrimination|caregiv\w*)\b",
        "Unequal treatment",
        "adversarial",
        "Two participants make the same request but have different caring responsibilities or work arrangements; compare their treatment.",
    ),
    (
        r"\b(emergenc\w*|exception\w*|essential)\b",
        "Operational exception",
        "compound",
        "An ordinary request and an urgent operational request arrive together; examine how each is handled and documented.",
    ),
    (
        r"\b(voucher\w*|benefit\w*|eligib\w*|income|property)\b",
        "Eligibility and changing circumstances",
        "compound",
        "A participant's circumstances change; examine whether the policy still applies and how overlapping eligibility conditions are handled, if present.",
    ),
    (
        r"\b(review|pilot|notice|monthly)\b",
        "Review and transition",
        "cascading",
        "A case remains open when a review or implementation period ends; examine notice, monitoring and transition handling.",
    ),
)
_BASE = (
    (
        "Ordinary use",
        "normal",
        "A participant follows the ordinary process described by the submitted policy.",
    ),
    (
        "Boundary ambiguity",
        "boundary",
        "Two otherwise similar participants fall on opposite sides of an applicable policy boundary, if one exists.",
    ),
    (
        "Overlapping circumstances",
        "compound",
        "One participant encounters two applicable policy circumstances at the same time.",
    ),
    (
        "Interrupted process",
        "cascading",
        "A request is interrupted and resumed after a participant's circumstances change.",
    ),
    (
        "Repeated request",
        "adversarial",
        "A participant repeats a request through different channels; examine consistent treatment and record keeping.",
    ),
)
_LIMITS = (
    "Metric prepared unscored scenario questions, not executed policy tests. No supported executable interpretation or authoritative expected outcomes are available.",
    "Topic matching does not extract provisions, establish omissions, or resolve exceptions. Review each scenario against the actual policy and supply testable requirements before scoring.",
    "These bounded scenario templates are exploratory, not exhaustive coverage. They contain no verified policy findings or pass/fail conclusions.",
)


def plan_scenarios(policy, run_id, review, *, test_budget):
    plans = []
    for pattern, title, category, circumstances in _TOPICS:
        match = re.search(pattern, policy.description, re.IGNORECASE)
        if match:
            source = f"topic_offset={match.start()}:{match.end()};sha256={hashlib.sha256(match.group().encode()).hexdigest()}"
            plans.append((title, category, circumstances, source))
    plans.extend((*item, "generic_exploration") for item in _BASE)
    plans = plans[:test_budget]
    fingerprint = canonical_sha256(
        {
            "planner": "topic_questions_v1",
            "input_review": review.review_fingerprint,
            "plans": plans,
        }
    )
    review = review.model_copy(
        update={"review_fingerprint": fingerprint, "limitations": _LIMITS}
    )
    cases = tuple(
        MetricCaseResult(
            case_id=f"scenario-{i}",
            title=title,
            category=category,
            plausibility=circumstances,
            initial_state=MetricState(),
            actions=(
                UnsupportedAction(action="review_scenario", parameters=(source,)),
            ),
            verdict="unscored",
            unscored_reason="No executable rule or authoritative expected outcome is available for this scenario. Human review and a supported test adapter are required before scoring.",
        )
        for i, (title, category, circumstances, source) in enumerate(plans, 1)
    )
    return MetricRunResult(
        run_id=run_id,
        policy_text_sha256=review.policy_text_sha256,
        review_fingerprint=fingerprint,
        generation_method="policy_scenarios",
        status="partial",
        review=review,
        suite_sha256=canonical_sha256({"review": fingerprint, "cases": cases}),
        cases=cases,
        passed=0,
        failed=0,
        unscored=len(cases),
        pass_rate=None,
        limitations=_LIMITS,
    )
