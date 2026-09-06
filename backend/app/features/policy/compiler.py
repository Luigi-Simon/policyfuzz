"""Deterministic assembly of validated extraction into a provisional policy."""

from app.core.hashing import canonical_sha256
from app.domain.models import CompilePolicyRequest, PolicyCompilation, PolicyIR
from app.features.policy.extraction import (
    assign_baseline_rule_ids,
    validate_policy_extraction,
)


def compile_baseline_policy(request: CompilePolicyRequest) -> PolicyCompilation:
    """Build a provisional baseline without invoking or trusting a model."""

    validated = validate_policy_extraction(request.document, request.extraction)
    rules = assign_baseline_rule_ids(
        request.document,
        validated.extraction.rules,
    )
    identity = canonical_sha256(
        {
            "document_sha256": request.document.document_sha256,
            "rule_ids": tuple(rule.rule_id for rule in rules),
            "unsupported_clauses": validated.extraction.unsupported_clauses,
        }
    )
    policy = PolicyIR(
        policy_id=f"policy-{identity}",
        document_sha256=request.document.document_sha256,
        kind="compiled_baseline",
        review_status="provisional",
        base_currency="SGD",
        rules=rules,
        unsupported_clauses=validated.extraction.unsupported_clauses,
    )
    return PolicyCompilation(
        policy=policy,
        excluded_rule_count=validated.excluded_rule_count,
    )
