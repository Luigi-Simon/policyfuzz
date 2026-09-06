"""Reject impossible rules and invalid dimension-specific precedence graphs."""

from app.domain.models import PolicyIR, Predicate
from app.features.evaluation.errors import RuleSetValidationError
from app.features.evaluation.predicates import _OPERATORS

_DOMAINS = {
    "employee_role": {"employee", "manager", "director", "executive"},
    "expense_category": {"meal", "hotel", "transport", "airfare", "incidental"},
    "destination_type": {"domestic", "international"},
    "receipt_present": {True, False},
}
_MAXIMA = {
    "amount_minor": 10_000_000,
    "booking_days_before": 365,
    "prior_same_day_category_spend_minor": 10_000_000,
    "daily_category_total_minor": 20_000_000,
}


def conditions_satisfiable(predicates: tuple[Predicate, ...]) -> bool:
    for field in {p.field for p in predicates}:
        items = [p for p in predicates if p.field == field]
        if field == "approval_roles_present":
            continue
        if field in _MAXIMA:
            maximum = _MAXIMA[field]
            candidates = {0, maximum}
            for p in items:
                candidates.update(
                    v for v in (p.value - 1, p.value, p.value + 1) if 0 <= v <= maximum
                )
        else:
            candidates = _DOMAINS[field]
        if not any(
            all(_OPERATORS[p.operator](v, p.value) for p in items) for v in candidates
        ):
            return False
    return True


def validate_rule_set(policy: PolicyIR) -> None:
    try:
        PolicyIR.model_validate(policy)
    except ValueError as exc:
        raise RuleSetValidationError(f"INVALID_RULE_SET: {exc}") from exc
    rules = {r.rule_id: r for r in policy.rules}
    for rule in policy.rules:
        if not conditions_satisfiable(rule.when):
            raise RuleSetValidationError(f"UNSATISFIABLE: {rule.rule_id}")
        for dimension in {e.dimension for e in rule.effects}:
            active, done = set(), set()

            def visit(rule_id, active=active, done=done, dimension=dimension):
                if rule_id in active:
                    raise RuleSetValidationError("OVERRIDE_CYCLE")
                if rule_id in done:
                    return
                active.add(rule_id)
                for edge in rules[rule_id].overrides:
                    if edge.dimension == dimension:
                        visit(edge.target_rule_id)
                active.remove(rule_id)
                done.add(rule_id)

            visit(rule.rule_id)


def conditions_unrestricted(predicates: tuple[Predicate, ...]) -> bool:
    """Every predicate tautological means the conjunction accepts the full domain."""
    for p in predicates:
        if p.field == "approval_roles_present":
            return False
        candidates = _DOMAINS.get(p.field)
        if candidates is None:
            maximum = _MAXIMA[p.field]
            candidates = {0, maximum, p.value}
            candidates.update(
                v for v in (p.value - 1, p.value + 1) if 0 <= v <= maximum
            )
        if not all(_OPERATORS[p.operator](v, p.value) for v in candidates):
            return False
    return True
