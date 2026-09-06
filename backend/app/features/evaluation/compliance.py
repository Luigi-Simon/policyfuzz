"""Compliance is separate from eligibility and uses stored claim facts."""

from app.domain.models import ComplianceResult, EffectValue, ScenarioFacts

_APPROVAL_RANK = {"none": 0, "manager": 1, "director": 2, "finance": 3}


def derive_compliance(
    dimension: str, resolved_value: EffectValue, facts: ScenarioFacts
) -> ComplianceResult | None:
    facts = ScenarioFacts.model_validate(facts)
    if dimension == "eligibility":
        return None
    if dimension == "receipt_requirement":
        compliant = resolved_value == "not_required" or facts.receipt_present
    elif dimension == "approval_requirement":
        present = max(
            (_APPROVAL_RANK[r] for r in facts.approval_roles_present), default=0
        )
        compliant = present >= _APPROVAL_RANK[resolved_value]
    elif dimension == "claim_cap_minor":
        compliant = facts.amount_minor <= resolved_value
    elif dimension == "daily_category_cap_minor":
        compliant = (
            facts.amount_minor + facts.prior_same_day_category_spend_minor
            <= resolved_value
        )
    else:
        raise ValueError("unknown compliance dimension")
    return ComplianceResult(
        dimension=dimension, status="COMPLIANT" if compliant else "NONCOMPLIANT"
    )
