"""Deterministic candidate validation, merging, selection and stable IDs."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from pydantic import ValidationError

from app.core.hashing import canonical_sha256
from app.domain.models import (
    PolicyContract,
    PolicyIR,
    Scenario,
    ScenarioBatch,
    ScenarioCandidate,
    ScenarioFacts,
    ScenarioRejection,
)
from app.features.fuzzing.synthesis import conditions_satisfied

_CATEGORY_PRIORITY = {"normal": 0, "adversarial": 1, "boundary": 2}


@dataclass(frozen=True, slots=True)
class CanonicalizationResult:
    """Feature-local detail retained until frozen suite statistics are built."""

    batch: ScenarioBatch
    rejections: tuple[ScenarioRejection, ...]
    generated_count: int
    duplicate_count: int


def fact_sha256(facts: ScenarioFacts) -> str:
    return canonical_sha256(ScenarioFacts.model_validate(facts))


def _assertion_projection(candidate: ScenarioCandidate) -> tuple[object, ...]:
    return tuple(
        sorted(
            candidate.assertions,
            key=lambda item: (item.assertion_id, canonical_sha256(item)),
        )
    )


def scenario_semantic_sha256(candidate: ScenarioCandidate) -> str:
    """Hash scenario identity fields; exclude category, origins and input IDs."""

    candidate = ScenarioCandidate.model_validate(candidate)
    return canonical_sha256(
        {
            "facts": candidate.facts,
            "target_rule_ids": tuple(sorted(set(candidate.target_rule_ids))),
            "target_invariant_ids": tuple(sorted(set(candidate.target_invariant_ids))),
            "assertions": _assertion_projection(candidate),
            "protected": candidate.protected,
            "partition": candidate.partition,
        }
    )


def _stable_candidate(candidate: ScenarioCandidate) -> ScenarioCandidate:
    normalized = candidate.model_copy(
        update={
            "candidate_id": "candidate-" + scenario_semantic_sha256(candidate),
            "target_rule_ids": tuple(sorted(set(candidate.target_rule_ids))),
            "target_invariant_ids": tuple(sorted(set(candidate.target_invariant_ids))),
            "assertions": _assertion_projection(candidate),
        }
    )
    return ScenarioCandidate.model_validate(normalized)


def materialize_scenario(candidate: ScenarioCandidate) -> Scenario:
    """Convert a validated candidate into its order-independent stable scenario."""

    candidate = _stable_candidate(ScenarioCandidate.model_validate(candidate))
    return Scenario(
        scenario_id="scenario-" + scenario_semantic_sha256(candidate),
        **candidate.model_dump(exclude={"candidate_id"}),
    )


def _rejection(
    candidate_id: str,
    reason_code: Literal[
        "invalid_facts",
        "invalid_assertion",
        "duplicate",
        "budget_exceeded",
        "incompatible_assertions",
    ],
    *,
    duplicate_of: str | None = None,
) -> ScenarioRejection:
    return ScenarioRejection(
        candidate_id=candidate_id,
        reason_code=reason_code,
        duplicate_of=duplicate_of,
    )


def _conflicting_assertions(left: ScenarioCandidate, right: ScenarioCandidate) -> bool:
    by_id = {item.assertion_id: item for item in left.assertions}
    by_coordinate = {
        (item.target_kind, item.dimension): item for item in left.assertions
    }
    for assertion in right.assertions:
        same_id = by_id.get(assertion.assertion_id)
        if same_id is not None and same_id != assertion:
            return True
        coordinate = (assertion.target_kind, assertion.dimension)
        existing = by_coordinate.get(coordinate)
        if existing is not None and (
            existing.operator != assertion.operator
            or existing.expected_value != assertion.expected_value
        ):
            return True
    return False


def _merge(left: ScenarioCandidate, right: ScenarioCandidate) -> ScenarioCandidate:
    assertions = {item.assertion_id: item for item in left.assertions}
    assertions.update({item.assertion_id: item for item in right.assertions})
    merged = ScenarioCandidate(
        candidate_id=left.candidate_id,
        category=max(
            (left.category, right.category), key=_CATEGORY_PRIORITY.__getitem__
        ),
        origins=left.origins | right.origins,
        facts=left.facts,
        target_rule_ids=tuple(
            sorted(set(left.target_rule_ids) | set(right.target_rule_ids))
        ),
        target_invariant_ids=tuple(
            sorted(set(left.target_invariant_ids) | set(right.target_invariant_ids))
        ),
        assertions=tuple(
            sorted(assertions.values(), key=lambda item: item.assertion_id)
        ),
        protected=left.protected or right.protected,
        partition=left.partition,
    )
    return _stable_candidate(merged)


def _validate_candidates(
    candidates: tuple[ScenarioCandidate, ...],
    *,
    policy: PolicyIR,
    contract: PolicyContract,
    used_fact_sha256s: frozenset[str],
) -> tuple[list[ScenarioCandidate], list[ScenarioRejection]]:
    rule_ids = {item.rule_id for item in policy.rules}
    invariant_ids = {item.invariant_id for item in contract.invariants}
    accepted: list[ScenarioCandidate] = []
    rejected: list[ScenarioRejection] = []
    for index, proposed in enumerate(candidates):
        candidate_id = getattr(proposed, "candidate_id", f"invalid-candidate-{index}")
        try:
            candidate = ScenarioCandidate.model_validate(proposed)
        except (ValidationError, TypeError, ValueError, AttributeError):
            rejected.append(_rejection(candidate_id, "invalid_facts"))
            continue
        if (
            not set(candidate.target_rule_ids) <= rule_ids
            or not set(candidate.target_invariant_ids) <= invariant_ids
        ):
            rejected.append(_rejection(candidate.candidate_id, "invalid_facts"))
            continue
        if candidate.protected and not candidate.assertions:
            rejected.append(_rejection(candidate.candidate_id, "invalid_assertion"))
            continue
        confirmed_invariants = {item.invariant_id: item for item in contract.invariants}
        if any(
            item.origin == "session_confirmed"
            and (
                (source := confirmed_invariants.get(item.source_invariant_id)) is None
                or source.assertion != item
                or source.invariant_id not in candidate.target_invariant_ids
                or not conditions_satisfied(source.when, candidate.facts)
            )
            for item in candidate.assertions
        ):
            rejected.append(_rejection(candidate.candidate_id, "invalid_assertion"))
            continue
        if fact_sha256(candidate.facts) in used_fact_sha256s:
            rejected.append(_rejection(candidate.candidate_id, "duplicate"))
            continue
        accepted.append(candidate)
    return accepted, rejected


def _deduplicate(
    candidates: list[ScenarioCandidate],
) -> tuple[list[ScenarioCandidate], list[ScenarioRejection], int]:
    groups: dict[tuple[str, str], list[ScenarioCandidate]] = {}
    for candidate in candidates:
        groups.setdefault(
            (fact_sha256(candidate.facts), candidate.partition), []
        ).append(candidate)
    merged_candidates: list[ScenarioCandidate] = []
    rejected: list[ScenarioRejection] = []
    duplicates = 0
    for key in sorted(groups):
        group = sorted(
            groups[key],
            key=lambda item: (scenario_semantic_sha256(item), item.candidate_id),
        )
        merged = _stable_candidate(group[0])
        group_rejections: list[tuple[str, str]] = []
        for candidate in group[1:]:
            if _conflicting_assertions(merged, candidate):
                group_rejections.append(
                    (candidate.candidate_id, "incompatible_assertions")
                )
                continue
            duplicates += 1
            merged = _merge(merged, candidate)
            group_rejections.append((candidate.candidate_id, "duplicate"))
        merged_candidates.append(merged)
        rejected.extend(
            _rejection(candidate_id, reason, duplicate_of=merged.candidate_id)
            for candidate_id, reason in group_rejections
        )
    return merged_candidates, rejected, duplicates


def _select(
    candidates: list[ScenarioCandidate],
    *,
    capacity: int,
    requested_rule_ids: frozenset[str],
    requested_invariant_ids: frozenset[str],
) -> tuple[list[ScenarioCandidate], list[ScenarioRejection]]:
    selected: list[ScenarioCandidate] = []
    remaining = list(candidates)
    covered_rules: set[str] = set()
    covered_invariants: set[str] = set()
    categories: set[str] = set()
    while remaining and len(selected) < capacity:

        def ranking(item: ScenarioCandidate) -> tuple[object, ...]:
            gain = len(
                (set(item.target_rule_ids) & requested_rule_ids) - covered_rules
            ) + len(
                (set(item.target_invariant_ids) & requested_invariant_ids)
                - covered_invariants
            )
            return (
                -int(item.protected),
                -int(item.category not in categories),
                -gain,
                -int("mechanical" in item.origins),
                scenario_semantic_sha256(item),
            )

        chosen = min(remaining, key=ranking)
        remaining.remove(chosen)
        selected.append(chosen)
        categories.add(chosen.category)
        covered_rules.update(set(chosen.target_rule_ids) & requested_rule_ids)
        covered_invariants.update(
            set(chosen.target_invariant_ids) & requested_invariant_ids
        )
    rejected = [
        _rejection(item.candidate_id, "budget_exceeded")
        for item in sorted(remaining, key=scenario_semantic_sha256)
    ]
    return sorted(selected, key=scenario_semantic_sha256), rejected


def canonicalize_with_rejections(
    *,
    kind: Literal["initial", "targeted"],
    candidates: tuple[ScenarioCandidate, ...],
    prior_rejections: tuple[ScenarioRejection, ...],
    policy: PolicyIR,
    contract: PolicyContract,
    capacity: int,
    requested_rule_ids: frozenset[str],
    requested_invariant_ids: frozenset[str],
    used_fact_sha256s: frozenset[str] = frozenset(),
) -> CanonicalizationResult:
    """Return the frozen batch plus all observable validation dispositions."""

    del kind  # Both phases share validation; their budgets are caller supplied.
    if type(capacity) is not int or not 0 <= capacity <= 15:
        raise ValueError("capacity must be between zero and fifteen")
    prior = tuple(ScenarioRejection.model_validate(item) for item in prior_rejections)
    valid, validation_rejections = _validate_candidates(
        candidates,
        policy=PolicyIR.model_validate(policy),
        contract=PolicyContract.model_validate(contract),
        used_fact_sha256s=used_fact_sha256s,
    )
    merged, duplicate_rejections, duplicate_count = _deduplicate(valid)
    selected, capacity_rejections = _select(
        merged,
        capacity=capacity,
        requested_rule_ids=requested_rule_ids,
        requested_invariant_ids=requested_invariant_ids,
    )
    return CanonicalizationResult(
        batch=ScenarioBatch(candidates=tuple(selected)),
        rejections=prior
        + tuple(validation_rejections)
        + tuple(duplicate_rejections)
        + tuple(capacity_rejections),
        generated_count=len(candidates),
        duplicate_count=duplicate_count,
    )


def canonicalize_batch(
    *,
    kind: Literal["initial", "targeted"],
    candidates: tuple[ScenarioCandidate, ...],
    prior_rejections: tuple[ScenarioRejection, ...],
    policy: PolicyIR,
    contract: PolicyContract,
    capacity: int,
    requested_rule_ids: frozenset[str],
    requested_invariant_ids: frozenset[str],
    used_fact_sha256s: frozenset[str] = frozenset(),
) -> ScenarioBatch:
    """Public frozen-contract projection of detailed canonicalization."""

    return canonicalize_with_rejections(
        kind=kind,
        candidates=candidates,
        prior_rejections=prior_rejections,
        policy=policy,
        contract=contract,
        capacity=capacity,
        requested_rule_ids=requested_rule_ids,
        requested_invariant_ids=requested_invariant_ids,
        used_fact_sha256s=used_fact_sha256s,
    ).batch
