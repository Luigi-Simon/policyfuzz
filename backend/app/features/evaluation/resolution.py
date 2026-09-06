"""Dimension-scoped precedence removes all named matching effects simultaneously."""

from app.domain.models import DimensionResult, PolicyContract, PolicyIR, Scenario
from app.features.evaluation.predicates import RuleTrace, evaluate_conditions


def scenario_required_dimensions(
    scenario: Scenario, contract: PolicyContract, matched_invariant_ids: frozenset[str]
) -> frozenset[str]:
    return (
        contract.required_dimensions
        | {a.dimension for a in scenario.assertions}
        | {
            i.assertion.dimension
            for i in contract.invariants
            if i.invariant_id in matched_invariant_ids
        }
    )


def resolve_dimension(
    policy: PolicyIR,
    scenario: Scenario,
    dimension: str,
    required_dimensions: frozenset[str],
    rule_traces: tuple[RuleTrace, ...],
) -> DimensionResult:
    unsupported = tuple(
        sorted(
            c.clause_id
            for c in policy.unsupported_clauses
            if dimension in c.affected_dimensions
            and (
                (c.when_hint is None and dimension in required_dimensions)
                or (
                    c.when_hint is not None
                    and all(
                        p.matched
                        for p in evaluate_conditions(c.when_hint, scenario.facts)
                    )
                )
            )
        )
    )
    if unsupported:
        return DimensionResult(
            dimension=dimension,
            status="INCONCLUSIVE",
            unsupported_clause_ids=unsupported,
        )
    matching = {r.rule_id for r in rule_traces if r.matched}
    rules = {
        r.rule_id: r
        for r in policy.rules
        if r.rule_id in matching and any(e.dimension == dimension for e in r.effects)
    }
    removed = {
        edge.target_rule_id
        for rule in rules.values()
        for edge in rule.overrides
        if edge.dimension == dimension and edge.target_rule_id in rules
    }
    values = {
        e.value
        for rid, r in rules.items()
        if rid not in removed
        for e in r.effects
        if e.dimension == dimension
    }
    common = {
        "dimension": dimension,
        "applicable_rule_ids": tuple(sorted(rules)),
        "overridden_rule_ids": tuple(sorted(removed)),
    }
    if not values:
        return DimensionResult(
            **common,
            status="GAP" if dimension in required_dimensions else "NOT_APPLICABLE",
        )
    if len(values) > 1:
        return DimensionResult(
            **common, status="CONFLICT", conflicting_values=tuple(sorted(values))
        )
    return DimensionResult(**common, status="VALUE", value=next(iter(values)))
