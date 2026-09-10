from __future__ import annotations

import hashlib

from app.v2.metric.sample import SAMPLE_POLICY
from app.v2.metric.service import prepare_policy, run_metric


def test_authored_sample_prepares_all_rules_and_cited_goals() -> None:
    review = prepare_policy(SAMPLE_POLICY)

    assert review.status == "ready"
    assert review.rules is not None
    assert review.rules.per_claim_limit_cents == 10_000
    assert review.rules.participant_allowance_cents == 15_000
    assert review.rules.approval_budget_accounting == "paid_only"
    assert review.rules.payment_budget_recheck is False
    assert review.rules.duplicate_scope == "claim_id"
    assert {goal.id for goal in review.goals} == {
        "G-AMOUNT",
        "G-BUDGET",
        "G-CANCELLED",
        "G-JOURNEY",
        "G-LONE-VALID",
    }
    clause_ids = {clause.id for clause in review.clauses}
    assert all(set(goal.clause_ids) <= clause_ids for goal in review.goals)


def test_numeric_limits_are_strict_integer_cents_and_parameterized() -> None:
    varied = SAMPLE_POLICY.model_copy(
        update={
            "description": SAMPLE_POLICY.description.replace(
                "per_claim_limit_cents=10000", "per_claim_limit_cents=9999"
            ).replace(
                "participant_allowance_cents=15000",
                "participant_allowance_cents=25001",
            )
        }
    )
    rules = prepare_policy(varied).rules
    assert rules is not None
    assert rules.per_claim_limit_cents == 9_999
    assert rules.participant_allowance_cents == 25_001

    fractional = SAMPLE_POLICY.model_copy(
        update={
            "description": SAMPLE_POLICY.description.replace(
                "per_claim_limit_cents=10000", "per_claim_limit_cents=100.5"
            )
        }
    )
    review = prepare_policy(fractional)
    assert review.status == "needs_clarification"
    assert review.rules is None


def test_unknown_or_missing_lines_need_fixed_clarification_without_raw_echo() -> None:
    secret_line = "PRIVATE_UNSUPPORTED_VALUE=do-not-repeat"
    unsupported = SAMPLE_POLICY.model_copy(
        update={"description": SAMPLE_POLICY.description + "\n" + secret_line}
    )
    review = prepare_policy(unsupported)
    assert review.status == "needs_clarification"
    assert review.rules is None
    assert secret_line not in repr(review.model_dump())
    assert review.limitations == (
        "Use exactly the documented line-based reimbursement policy format, including every required operative clause and explicit Goal clause.",
    )

    missing_goal = SAMPLE_POLICY.model_copy(
        update={
            "description": "\n".join(
                line
                for line in SAMPLE_POLICY.description.splitlines()
                if "GOAL G-BUDGET" not in line
            )
        }
    )
    assert prepare_policy(missing_goal).status == "needs_clarification"


def test_review_fingerprint_binds_all_four_inputs_and_interpretation() -> None:
    base = prepare_policy(SAMPLE_POLICY).review_fingerprint
    variants = (
        SAMPLE_POLICY.model_copy(update={"title": "Another synthetic title"}),
        SAMPLE_POLICY.model_copy(
            update={"description": SAMPLE_POLICY.description.replace("10000", "10001")}
        ),
        SAMPLE_POLICY.model_copy(update={"agent_seed": "Another personality seed."}),
        SAMPLE_POLICY.model_copy(update={"agent_count": 3}),
    )
    assert all(prepare_policy(policy).review_fingerprint != base for policy in variants)


def test_policy_hash_uses_exact_utf8_and_fingerprint_distinguishes_nfc_inputs() -> None:
    composed = SAMPLE_POLICY.model_copy(
        update={"description": "unsupported caf\N{LATIN SMALL LETTER E WITH ACUTE}"}
    )
    decomposed = SAMPLE_POLICY.model_copy(
        update={"description": "unsupported cafe\N{COMBINING ACUTE ACCENT}"}
    )
    composed_review = prepare_policy(composed)
    decomposed_review = prepare_policy(decomposed)

    assert (
        composed_review.policy_text_sha256
        == hashlib.sha256(composed.description.encode("utf-8")).hexdigest()
    )
    assert (
        decomposed_review.policy_text_sha256
        == hashlib.sha256(decomposed.description.encode("utf-8")).hexdigest()
    )
    assert composed_review.review_fingerprint != decomposed_review.review_fingerprint


def test_run_rejects_stale_review_and_does_not_score_clarification() -> None:
    review = prepare_policy(SAMPLE_POLICY)
    stale = SAMPLE_POLICY.model_copy(update={"agent_count": 3})
    try:
        run_metric(stale, review.review_fingerprint)
    except ValueError as exc:
        assert str(exc) == "review fingerprint does not match the complete policy input"
    else:
        raise AssertionError("stale review fingerprint was accepted")

    unsupported = SAMPLE_POLICY.model_copy(update={"description": "ordinary prose"})
    unsupported_review = prepare_policy(unsupported)
    result = run_metric(unsupported, unsupported_review.review_fingerprint)
    assert result.status == "needs_clarification"
    assert result.cases == ()
    assert (result.passed, result.failed, result.unscored, result.pass_rate) == (
        0,
        0,
        0,
        None,
    )
