"""Typed predicates, with complete AND traces and no implicit hierarchy."""

import operator
from dataclasses import dataclass

from app.domain.models import Predicate, Rule, ScenarioFacts

_OPERATORS = {
    "eq": operator.eq,
    "neq": operator.ne,
    "lt": operator.lt,
    "lte": operator.le,
    "gt": operator.gt,
    "gte": operator.ge,
    "in": lambda actual, expected: actual in expected,
    "not_in": lambda actual, expected: actual not in expected,
    "contains": lambda actual, expected: expected in actual,
}


@dataclass(frozen=True)
class PredicateTrace:
    matched: bool


@dataclass(frozen=True)
class RuleTrace:
    rule_id: str
    matched: bool
    predicates: tuple[PredicateTrace, ...]


def evaluate_predicate(predicate: Predicate, facts: ScenarioFacts) -> PredicateTrace:
    predicate = Predicate.model_validate(predicate)
    facts = ScenarioFacts.model_validate(facts)
    actual = (
        facts.amount_minor + facts.prior_same_day_category_spend_minor
        if predicate.field == "daily_category_total_minor"
        else getattr(facts, predicate.field)
    )
    return PredicateTrace(_OPERATORS[predicate.operator](actual, predicate.value))


def evaluate_conditions(
    predicates: tuple[Predicate, ...], facts: ScenarioFacts
) -> tuple[PredicateTrace, ...]:
    return tuple(evaluate_predicate(predicate, facts) for predicate in predicates)


def rule_matches(rule: Rule, facts: ScenarioFacts) -> RuleTrace:
    predicates = evaluate_conditions(rule.when, facts)
    return RuleTrace(rule.rule_id, all(p.matched for p in predicates), predicates)
