"""Pure deterministic construction of complete mechanical scenario facts."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from dataclasses import field as dataclass_field

from app.core.hashing import canonical_sha256
from app.domain.models import (
    PolicyContract,
    PolicyIR,
    Predicate,
    ScenarioCandidate,
    ScenarioFacts,
)
from app.features.fuzzing.constants import INTEGER_FIELD_MAXIMUMS

_ENUM_DOMAINS = {
    "employee_role": ("employee", "manager", "director", "executive"),
    "expense_category": ("meal", "hotel", "transport", "airfare", "incidental"),
    "destination_type": ("domestic", "international"),
}
_APPROVAL_ROLES = ("manager", "director", "finance")
_DEFAULT_FACTS = {
    "employee_role": "employee",
    "expense_category": "meal",
    "amount_minor": 5_000,
    "destination_type": "domestic",
    "booking_days_before": 14,
    "receipt_present": True,
    "approval_roles_present": frozenset(),
    "prior_same_day_category_spend_minor": 0,
}
_FACT_ORDER = (
    "employee_role",
    "expense_category",
    "amount_minor",
    "destination_type",
    "booking_days_before",
    "receipt_present",
    "approval_roles_present",
    "prior_same_day_category_spend_minor",
)


def numeric_triplet(threshold: int, *, minimum: int, maximum: int) -> tuple[int, ...]:
    """Return each exact in-domain neighbor without clamping duplicates."""

    if (
        type(threshold) is not int
        or type(minimum) is not int
        or type(maximum) is not int
    ):
        raise TypeError("numeric boundaries require integers")
    if minimum > maximum:
        raise ValueError("minimum cannot exceed maximum")
    return tuple(
        value
        for value in (threshold - 1, threshold, threshold + 1)
        if minimum <= value <= maximum
    )


def _predicate_value(predicate: Predicate, facts: dict[str, object]) -> object:
    if predicate.field == "daily_category_total_minor":
        return int(facts["amount_minor"]) + int(
            facts["prior_same_day_category_spend_minor"]
        )
    return facts[predicate.field]


def _matches(predicate: Predicate, facts: dict[str, object]) -> bool:
    actual = _predicate_value(predicate, facts)
    expected = predicate.value
    if predicate.operator == "eq":
        return actual == expected
    if predicate.operator == "neq":
        return actual != expected
    if predicate.operator == "in":
        return actual in expected
    if predicate.operator == "not_in":
        return actual not in expected
    if predicate.operator == "contains":
        return expected in actual
    if predicate.operator == "lt":
        return actual < expected
    if predicate.operator == "lte":
        return actual <= expected
    if predicate.operator == "gt":
        return actual > expected
    if predicate.operator == "gte":
        return actual >= expected
    return False


def _ordered_unique(values: Iterable[object]) -> tuple[object, ...]:
    result: list[object] = []
    for value in values:
        if value not in result:
            result.append(value)
    return tuple(result)


def _numeric_values(field: str, conditions: tuple[Predicate, ...]) -> tuple[int, ...]:
    maximum = INTEGER_FIELD_MAXIMUMS[field]
    values: list[int] = [int(_DEFAULT_FACTS[field]), 0, 1, maximum]
    for condition in conditions:
        if condition.field == field and type(condition.value) is int:
            values.extend(numeric_triplet(condition.value, minimum=0, maximum=maximum))
    return tuple(int(item) for item in _ordered_unique(values))


def _field_values(field: str, conditions: tuple[Predicate, ...]) -> tuple[object, ...]:
    if field in _ENUM_DOMAINS:
        default = _DEFAULT_FACTS[field]
        return _ordered_unique((default, *_ENUM_DOMAINS[field]))
    if field in INTEGER_FIELD_MAXIMUMS:
        return _numeric_values(field, conditions)
    if field == "receipt_present":
        return (True, False)
    if field == "approval_roles_present":
        return (
            frozenset(),
            *(frozenset({role}) for role in _APPROVAL_ROLES),
            frozenset(_APPROVAL_ROLES),
        )
    raise AssertionError(f"unsupported stored fact field: {field}")


@dataclass
class _IntegerDomain:
    lower: int
    upper: int
    excluded: set[int] = dataclass_field(default_factory=set)

    def allows(self, value: int) -> bool:
        return self.lower <= value <= self.upper and value not in self.excluded


def _integer_domain(
    field_name: str, conditions: tuple[Predicate, ...], *, maximum: int
) -> _IntegerDomain:
    domain = _IntegerDomain(lower=0, upper=maximum)
    for condition in conditions:
        if condition.field != field_name or type(condition.value) is not int:
            continue
        value = condition.value
        if condition.operator == "eq":
            domain.lower = max(domain.lower, value)
            domain.upper = min(domain.upper, value)
        elif condition.operator == "neq":
            domain.excluded.add(value)
        elif condition.operator == "lt":
            domain.upper = min(domain.upper, value - 1)
        elif condition.operator == "lte":
            domain.upper = min(domain.upper, value)
        elif condition.operator == "gt":
            domain.lower = max(domain.lower, value + 1)
        elif condition.operator == "gte":
            domain.lower = max(domain.lower, value)
    return domain


def _nearest_allowed(domain: _IntegerDomain, preferred: int) -> int | None:
    if domain.lower > domain.upper:
        return None
    start = min(max(preferred, domain.lower), domain.upper)
    for offset in range(len(domain.excluded) + 2):
        for value in (start + offset, start - offset):
            if domain.allows(value):
                return value
    return None


def _daily_pairs(conditions: tuple[Predicate, ...]) -> tuple[tuple[int, int], ...]:
    amount = _integer_domain("amount_minor", conditions, maximum=10_000_000)
    prior = _integer_domain(
        "prior_same_day_category_spend_minor", conditions, maximum=10_000_000
    )
    total = _integer_domain(
        "daily_category_total_minor", conditions, maximum=20_000_000
    )
    amount_lower = max(amount.lower, total.lower - prior.upper)
    amount_upper = min(amount.upper, total.upper - prior.lower)
    if amount_lower > amount_upper:
        return ()

    # Every inequality reduces to an interval. Only ``neq`` predicates can leave
    # holes, so probing each interval edge plus one point per excluded value is
    # complete without scanning the (potentially twenty-million-item) domain.
    probe_count = len(amount.excluded) + len(prior.excluded) + len(total.excluded) + 2
    amount_candidates = _ordered_unique(
        (
            min(max(5_000, amount_lower), amount_upper),
            *(amount_lower + offset for offset in range(probe_count)),
            *(amount_upper - offset for offset in range(probe_count)),
        )
    )
    for amount_value in amount_candidates:
        if not amount.allows(amount_value):
            continue
        prior_domain = _IntegerDomain(
            lower=max(prior.lower, total.lower - amount_value),
            upper=min(prior.upper, total.upper - amount_value),
            excluded=prior.excluded
            | {excluded_total - amount_value for excluded_total in total.excluded},
        )
        prior_value = _nearest_allowed(prior_domain, 0)
        if prior_value is not None:
            return ((amount_value, prior_value),)
    return ()


def satisfy_conditions(
    conditions: tuple[Predicate, ...], *, seed: int
) -> ScenarioFacts | None:
    """Find one complete typed fact vector satisfying an AND-only condition set."""

    del seed  # The fixed domain order makes identical semantic input reproducible.
    validated = tuple(Predicate.model_validate(item) for item in conditions)
    facts = dict(_DEFAULT_FACTS)
    for field in _FACT_ORDER:
        if field in {"amount_minor", "prior_same_day_category_spend_minor"}:
            continue
        relevant = tuple(item for item in validated if item.field == field)
        if not relevant:
            continue
        selected = next(
            (
                value
                for value in _field_values(field, validated)
                if all(_matches(item, facts | {field: value}) for item in relevant)
            ),
            None,
        )
        if selected is None:
            return None
        facts[field] = selected

    numeric_conditions = tuple(
        item
        for item in validated
        if item.field
        in {
            "amount_minor",
            "prior_same_day_category_spend_minor",
            "daily_category_total_minor",
        }
    )
    pair = next(
        (
            candidate
            for candidate in _daily_pairs(validated)
            if all(
                _matches(
                    item,
                    facts
                    | {
                        "amount_minor": candidate[0],
                        "prior_same_day_category_spend_minor": candidate[1],
                    },
                )
                for item in numeric_conditions
            )
        ),
        None,
    )
    if pair is None:
        return None
    facts["amount_minor"], facts["prior_same_day_category_spend_minor"] = pair
    if not all(_matches(item, facts) for item in validated):
        return None
    return ScenarioFacts(**facts)


def conditions_satisfied(
    conditions: tuple[Predicate, ...], facts: ScenarioFacts
) -> bool:
    """Evaluate supported AND-only conditions over a complete fact vector."""

    facts = ScenarioFacts.model_validate(facts)
    return all(
        _matches(Predicate.model_validate(item), facts.model_dump())
        for item in conditions
    )


def _candidate_id(payload: object) -> str:
    return f"candidate-{canonical_sha256(payload)}"


def _candidate(
    *,
    category: str,
    facts: ScenarioFacts,
    rule_ids: tuple[str, ...] = (),
    invariant_ids: tuple[str, ...] = (),
    assertions: tuple = (),
    protected: bool = False,
) -> ScenarioCandidate:
    signature = {
        "category": category,
        "facts": facts,
        "rule_ids": tuple(sorted(rule_ids)),
        "invariant_ids": tuple(sorted(invariant_ids)),
        "assertions": tuple(sorted(assertions, key=lambda item: item.assertion_id)),
        "protected": protected,
    }
    return ScenarioCandidate(
        candidate_id=_candidate_id(signature),
        category=category,
        origins=frozenset({"mechanical", "session"})
        if assertions
        else frozenset({"mechanical"}),
        facts=facts,
        target_rule_ids=tuple(sorted(rule_ids)),
        target_invariant_ids=tuple(sorted(invariant_ids)),
        assertions=assertions,
        protected=protected,
    )


def _boundary_facts(
    base: ScenarioFacts, predicate: Predicate, value: int
) -> ScenarioFacts:
    if predicate.field == "daily_category_total_minor":
        amount = min(value // 2, 10_000_000)
        prior = value - amount
        return base.model_copy(
            update={
                "amount_minor": amount,
                "prior_same_day_category_spend_minor": prior,
            }
        )
    return base.model_copy(update={predicate.field: value})


def _mechanical_candidates(
    policy: PolicyIR,
    contract: PolicyContract,
    *,
    rule_ids: frozenset[str],
    invariant_ids: frozenset[str],
    seed: int,
) -> tuple[ScenarioCandidate, ...]:
    candidates: list[ScenarioCandidate] = []
    for rule in policy.rules:
        if rule.rule_id not in rule_ids:
            continue
        witness = satisfy_conditions(rule.when, seed=seed)
        if witness is None:
            continue
        candidates.append(
            _candidate(category="normal", facts=witness, rule_ids=(rule.rule_id,))
        )
        for predicate in rule.when:
            if predicate.field not in INTEGER_FIELD_MAXIMUMS:
                continue
            assert type(predicate.value) is int
            for value in numeric_triplet(
                predicate.value,
                minimum=0,
                maximum=INTEGER_FIELD_MAXIMUMS[predicate.field],
            ):
                candidates.append(
                    _candidate(
                        category="boundary",
                        facts=_boundary_facts(witness, predicate, value),
                        rule_ids=(rule.rule_id,),
                    )
                )

    for invariant in contract.invariants:
        if invariant.invariant_id not in invariant_ids:
            continue
        witness = satisfy_conditions(invariant.when, seed=seed)
        if witness is None:
            continue
        candidates.append(
            _candidate(
                category="normal",
                facts=witness,
                invariant_ids=(invariant.invariant_id,),
                assertions=(invariant.assertion,),
                protected=True,
            )
        )
        for predicate in invariant.when:
            if predicate.field not in INTEGER_FIELD_MAXIMUMS:
                continue
            assert type(predicate.value) is int
            for value in numeric_triplet(
                predicate.value,
                minimum=0,
                maximum=INTEGER_FIELD_MAXIMUMS[predicate.field],
            ):
                boundary = _boundary_facts(witness, predicate, value)
                assertion_applies = conditions_satisfied(invariant.when, boundary)
                candidates.append(
                    _candidate(
                        category="boundary",
                        facts=boundary,
                        invariant_ids=(invariant.invariant_id,),
                        assertions=(invariant.assertion,) if assertion_applies else (),
                        protected=assertion_applies,
                    )
                )
    return tuple(candidates)


def build_initial_mechanical_candidates(
    policy: PolicyIR, contract: PolicyContract, *, seed: int
) -> tuple[ScenarioCandidate, ...]:
    """Build normal witnesses and all exact numeric neighbors."""

    return _mechanical_candidates(
        policy,
        contract,
        rule_ids=frozenset(rule.rule_id for rule in policy.rules),
        invariant_ids=frozenset(item.invariant_id for item in contract.invariants),
        seed=seed,
    )


def build_targeted_mechanical_candidates(
    policy: PolicyIR,
    contract: PolicyContract,
    *,
    rule_ids: frozenset[str],
    invariant_ids: frozenset[str],
    seed: int,
) -> tuple[ScenarioCandidate, ...]:
    """Build cases only for the measured targets still uncovered."""

    return _mechanical_candidates(
        policy,
        contract,
        rule_ids=rule_ids,
        invariant_ids=invariant_ids,
        seed=seed,
    )
