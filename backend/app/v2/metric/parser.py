"""Strict parser for the controlled reimbursement policy format."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass

from app.core.hashing import canonical_sha256
from app.v2.metric_contracts import (
    MetricReview,
    MetricRules,
    PolicyClause,
    PolicyGoal,
)
from app.v2.run_models import RunPolicyInput

_CLARIFICATION = "Use exactly the documented line-based reimbursement policy format, including every required operative clause and explicit Goal clause."
_ASSUMPTIONS = (
    "Money values use strict integer SGD cents.",
    "Each participant has an independent allowance.",
    "Execution models ordered actions rather than concurrent infrastructure load.",
    "Claim IDs are unique, and resubmission cannot overwrite an existing claim.",
    "Approval requires a submitted claim; payment requires approval and cannot repeat.",
    "Cancellation voids a submitted or approved claim and releases its reservation; cancelling a paid claim is rejected without a refund.",
    "A rejected action preserves the complete prior state.",
    "Eligibility is defined only by the stated amount, lifecycle, budget, and duplicate rules; no separate eligibility flag is inferred.",
)
_LIMITATIONS = (
    "Interpretation is limited to the bounded synthetic reimbursement domain.",
    "The controlled format does not establish legal or real-policy provenance.",
)

_CLAUSE_LAYOUT = (
    (
        "C-AMOUNT",
        "per_claim_limit_cents",
        "Claim amounts must be positive and no greater than the configured per-claim limit.",
    ),
    (
        "C-ALLOWANCE",
        "participant_allowance_cents",
        "Each participant has a separate configured total payment allowance.",
    ),
    (
        "C-APPROVAL-BUDGET",
        "approval_budget_accounting",
        "Approval budget checks use the configured accounting basis.",
    ),
    (
        "C-PAYMENT-RECHECK",
        "payment_budget_recheck",
        "Payment uses the configured allowance recheck setting.",
    ),
    (
        "C-DUPLICATE",
        "duplicate_scope",
        "Duplicate rejection uses the configured identity scope for the same participant.",
    ),
    (
        "C-LIFECYCLE",
        "actions",
        "Claims follow ordered submission, approval, payment, and cancellation rules.",
    ),
)
_GOAL_LAYOUT = (
    (
        "G-BUDGET",
        ("C-ALLOWANCE", "C-APPROVAL-BUDGET", "C-PAYMENT-RECHECK"),
        "Total participant payouts must not exceed that participant's allowance.",
    ),
    (
        "G-JOURNEY",
        ("C-DUPLICATE",),
        "A participant must receive at most one payment for the same journey.",
    ),
    (
        "G-CANCELLED",
        ("C-LIFECYCLE",),
        "A cancelled claim must not be paid.",
    ),
    (
        "G-LONE-VALID",
        ("C-AMOUNT", "C-ALLOWANCE", "C-LIFECYCLE"),
        "A lone valid claim within the limits can be paid.",
    ),
    (
        "G-AMOUNT",
        ("C-AMOUNT",),
        "No payment may occur for a claim outside the stated amount bounds.",
    ),
)


@dataclass(frozen=True)
class _Interpretation:
    clauses: tuple[PolicyClause, ...]
    goals: tuple[PolicyGoal, ...]
    rules: MetricRules


def _parse(policy_text: str) -> _Interpretation | None:
    lines = policy_text.splitlines()
    if len(lines) != 1 + len(_CLAUSE_LAYOUT) + len(_GOAL_LAYOUT):
        return None
    if lines[0] != "POLICY_FORMAT=1" or any(
        not line or len(line) > 1_000 for line in lines
    ):
        return None

    clauses: list[PolicyClause] = []
    values: dict[str, str] = {}
    for line, (clause_id, key, display_text) in zip(
        lines[1 : 1 + len(_CLAUSE_LAYOUT)], _CLAUSE_LAYOUT, strict=True
    ):
        prefix = f"CLAUSE {clause_id} | {key}="
        suffix = f" | {display_text}"
        if not line.startswith(prefix) or not line.endswith(suffix):
            return None
        value = line[len(prefix) : -len(suffix)]
        if not value or "|" in value or value.strip() != value:
            return None
        values[key] = value
        clauses.append(PolicyClause(id=clause_id, text=display_text))

    goals: list[PolicyGoal] = []
    for line, (goal_id, clause_ids, goal_text) in zip(
        lines[1 + len(_CLAUSE_LAYOUT) :], _GOAL_LAYOUT, strict=True
    ):
        expected = f"GOAL {goal_id} | {','.join(clause_ids)} | {goal_text}"
        if line != expected:
            return None
        goals.append(PolicyGoal(id=goal_id, text=goal_text, clause_ids=clause_ids))

    try:
        if values["actions"] != "submit,approve,pay,cancel":
            return None
        if values["approval_budget_accounting"] not in {
            "paid_only",
            "paid_and_approved",
        }:
            return None
        if values["payment_budget_recheck"] not in {"on", "off"}:
            return None
        if values["duplicate_scope"] not in {"claim_id", "journey"}:
            return None
        if (
            not values["per_claim_limit_cents"].isascii()
            or not values["per_claim_limit_cents"].isdigit()
        ):
            return None
        if (
            not values["participant_allowance_cents"].isascii()
            or not values["participant_allowance_cents"].isdigit()
        ):
            return None
        rules = MetricRules(
            per_claim_limit_cents=int(values["per_claim_limit_cents"]),
            participant_allowance_cents=int(values["participant_allowance_cents"]),
            approval_budget_accounting=values["approval_budget_accounting"],
            payment_budget_recheck=values["payment_budget_recheck"] == "on",
            duplicate_scope=values["duplicate_scope"],
        )
    except (KeyError, ValueError):
        return None
    return _Interpretation(tuple(clauses), tuple(goals), rules)


def _fingerprint_payload(
    policy: RunPolicyInput,
    interpretation: _Interpretation | None,
) -> dict[str, object]:
    interpreted: dict[str, object]
    if interpretation is None:
        interpreted = {
            "status": "needs_clarification",
            "clauses": (),
            "goals": (),
            "rules": None,
            "assumptions": (),
            "limitations": _CLARIFICATION,
        }
    else:
        interpreted = {
            "status": "ready",
            "clauses": interpretation.clauses,
            "goals": interpretation.goals,
            "rules": interpretation.rules,
            "assumptions": _ASSUMPTIONS,
            "limitations": _LIMITATIONS,
        }
    exact_input = json.dumps(
        {
            "title": policy.title,
            "description": policy.description,
            "agent_seed": policy.agent_seed,
            "agent_count": policy.agent_count,
        },
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    return {
        "exact_input_sha256": hashlib.sha256(exact_input).hexdigest(),
        "policy_text_sha256": hashlib.sha256(
            policy.description.encode("utf-8")
        ).hexdigest(),
        "policy": {
            "title": policy.title,
            "description": policy.description,
            "agent_seed": policy.agent_seed,
            "agent_count": policy.agent_count,
        },
        "interpretation": interpreted,
    }


def prepare(policy: RunPolicyInput) -> MetricReview:
    """Return the exact controlled-format interpretation for review."""
    interpretation = _parse(policy.description)
    fingerprint = canonical_sha256(_fingerprint_payload(policy, interpretation))
    policy_hash = hashlib.sha256(policy.description.encode("utf-8")).hexdigest()
    if interpretation is None:
        return MetricReview(
            policy_text_sha256=policy_hash,
            review_fingerprint=fingerprint,
            status="needs_clarification",
            clauses=(),
            goals=(),
            rules=None,
            assumptions=(),
            limitations=(_CLARIFICATION,),
        )
    return MetricReview(
        policy_text_sha256=policy_hash,
        review_fingerprint=fingerprint,
        status="ready",
        clauses=interpretation.clauses,
        goals=interpretation.goals,
        rules=interpretation.rules,
        assumptions=_ASSUMPTIONS,
        limitations=_LIMITATIONS,
    )


__all__ = ["prepare"]
