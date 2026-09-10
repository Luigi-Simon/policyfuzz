"""Stable public entry points for policy review and deterministic Metric runs."""

from __future__ import annotations

from app.core.hashing import canonical_sha256
from app.v2.metric_contracts import MetricReview, MetricRunResult
from app.v2.run_models import RunPolicyInput

from .parser import prepare


def prepare_policy(policy: RunPolicyInput) -> MetricReview:
    return prepare(policy)


def run_metric(
    policy: RunPolicyInput,
    review_fingerprint: str,
) -> MetricRunResult:
    review = prepare(policy)
    if review.review_fingerprint != review_fingerprint:
        raise ValueError("review fingerprint does not match the complete policy input")
    if review.status == "needs_clarification":
        return MetricRunResult(
            run_id=f"metric-{canonical_sha256({'review': review_fingerprint})[:16]}",
            policy_text_sha256=review.policy_text_sha256,
            review_fingerprint=review.review_fingerprint,
            status="needs_clarification",
            review=review,
            suite_sha256=canonical_sha256(()),
            cases=(),
            passed=0,
            failed=0,
            unscored=0,
            pass_rate=None,
            limitations=("No scored cases were produced before clarification.",),
        )

    from .runner import execute_metric_suite

    return execute_metric_suite(review)


__all__ = ["prepare_policy", "run_metric"]
