"""Honest coverage accounting from evaluator-produced evidence only."""

from __future__ import annotations

from app.domain.models import (
    CoverageEvidence,
    CoverageSnapshot,
    PolicyContract,
    PolicyIR,
)


def _evidence_key(item: CoverageEvidence) -> tuple[object, ...]:
    return (
        item.target_kind,
        item.target_id,
        -1 if item.predicate_index is None else item.predicate_index,
        -1 if item.predicate_outcome is None else int(item.predicate_outcome),
    )


def analyze_coverage(
    policy: PolicyIR,
    contract: PolicyContract,
    evidence: CoverageEvidence | tuple[CoverageEvidence, ...],
) -> CoverageSnapshot:
    """Normalize measured evidence and derive required-target coverage."""

    policy = PolicyIR.model_validate(policy)
    contract = PolicyContract.model_validate(contract)
    supplied = (evidence,) if isinstance(evidence, CoverageEvidence) else evidence
    rule_lengths = {rule.rule_id: len(rule.when) for rule in policy.rules}
    invariant_ids = {item.invariant_id for item in contract.invariants}
    aggregated: dict[tuple[object, ...], set[str]] = {}
    canonical: dict[tuple[object, ...], CoverageEvidence] = {}
    for proposed in supplied:
        item = CoverageEvidence.model_validate(proposed)
        if not item.scenario_ids:
            continue
        valid = (
            (item.target_kind == "rule" and item.target_id in rule_lengths)
            or (item.target_kind == "invariant" and item.target_id in invariant_ids)
            or (
                item.target_kind == "predicate_branch"
                and item.target_id in rule_lengths
                and item.predicate_index is not None
                and item.predicate_index < rule_lengths[item.target_id]
            )
        )
        if not valid:
            continue
        key = _evidence_key(item)
        canonical[key] = item
        aggregated.setdefault(key, set()).update(item.scenario_ids)

    normalized = tuple(
        canonical[key].model_copy(
            update={"scenario_ids": tuple(sorted(aggregated[key]))}
        )
        for key in sorted(aggregated)
    )
    covered_rules = {
        item.target_id for item in normalized if item.target_kind == "rule"
    }
    covered_invariants = {
        item.target_id for item in normalized if item.target_kind == "invariant"
    }
    covered_branches = {
        _evidence_key(item)
        for item in normalized
        if item.target_kind == "predicate_branch"
    }
    missing_rules = tuple(sorted(set(rule_lengths) - covered_rules))
    missing_invariants = tuple(sorted(invariant_ids - covered_invariants))
    return CoverageSnapshot(
        total_rules=len(rule_lengths),
        covered_rules=len(covered_rules),
        total_invariants=len(invariant_ids),
        covered_invariants=len(covered_invariants),
        total_predicate_branches=2 * sum(rule_lengths.values()),
        covered_predicate_branches=len(covered_branches),
        evidence=normalized,
        missing_rule_ids=missing_rules,
        missing_invariant_ids=missing_invariants,
        status="satisfied"
        if not missing_rules and not missing_invariants
        else "pending",
    )


def required_coverage_complete(coverage: CoverageSnapshot) -> bool:
    coverage = CoverageSnapshot.model_validate(coverage)
    return (
        coverage.covered_rules == coverage.total_rules
        and coverage.covered_invariants == coverage.total_invariants
        and not coverage.missing_rule_ids
        and not coverage.missing_invariant_ids
    )


def adaptation_lift(initial: CoverageSnapshot, final: CoverageSnapshot) -> int:
    """Count net newly covered required rule and invariant targets."""

    initial = CoverageSnapshot.model_validate(initial)
    final = CoverageSnapshot.model_validate(final)
    return (final.covered_rules + final.covered_invariants) - (
        initial.covered_rules + initial.covered_invariants
    )
