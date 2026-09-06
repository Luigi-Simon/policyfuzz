"""Semantic equivalence signatures deliberately exclude extraction identity."""

from collections.abc import Mapping

from app.core.hashing import canonical_sha256
from app.domain.models import Rule


def base_rule_signature(rule: Rule) -> str:
    predicates = set()
    for p in rule.when:
        value = (
            tuple(sorted(set(p.value))) if p.operator in ("in", "not_in") else p.value
        )
        predicates.add(
            canonical_sha256({"field": p.field, "operator": p.operator, "value": value})
        )
    return canonical_sha256(
        {
            "when": tuple(sorted(predicates)),
            "effects": tuple(sorted((e.dimension, e.value) for e in rule.effects)),
        }
    )


def semantic_rule_signature(rule: Rule, rules_by_id: Mapping[str, Rule]) -> str:
    return canonical_sha256(
        {
            "base": base_rule_signature(rule),
            "overrides": tuple(
                sorted(
                    (o.dimension, base_rule_signature(rules_by_id[o.target_rule_id]))
                    for o in rule.overrides
                )
            ),
        }
    )
