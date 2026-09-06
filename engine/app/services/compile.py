"""Recompile PolicyIR indexes and validate predicate fields."""

from __future__ import annotations

from app.contracts.common import now_iso
from app.contracts.policy import CompiledIndex, PolicyIR, Predicate

KNOWN_ROOTS = ("actor.", "action.", "context.", "population.")


class CompileError(ValueError):
    pass


def compile_ir(ir: PolicyIR) -> PolicyIR:
    _validate(ir)
    ir.index = _build_index(ir)
    ir.compiled_at = now_iso()
    return ir


def _validate(ir: PolicyIR) -> None:
    if not ir.actor_types:
        raise CompileError("PolicyIR has no actor_types")
    actor_ids = {actor.id for actor in ir.actor_types}
    fallback_actor = ir.actor_types[0].id
    if not ir.rules:
        raise CompileError("PolicyIR has no rules")
    for rule in ir.rules:
        rule.applies_to = [item for item in rule.applies_to if item in actor_ids] or [fallback_actor]
        for predicate in [*rule.when, *rule.except_when]:
            _normalize_predicate(predicate)


def _normalize_predicate(predicate: Predicate) -> None:
    field = (predicate.field or "context.unspecified").strip()
    if not any(field.startswith(root) for root in KNOWN_ROOTS):
        field = f"context.{field}"
    predicate.field = field


def _build_index(ir: PolicyIR) -> CompiledIndex:
    rules_by_actor: dict[str, list[str]] = {actor.id: [] for actor in ir.actor_types}
    parameters: dict[str, object] = {}
    fields: set[str] = set()
    open_question_rule_ids: list[str] = []

    for actor in ir.actor_types:
        for attr in actor.attributes:
            fields.add(f"actor.{attr.name}")
    for action in ir.actions:
        fields.add("action.name")
        for attr in action.attributes:
            fields.add(f"action.{attr.name}")

    for rule in ir.rules:
        for actor_id in rule.applies_to:
            rules_by_actor.setdefault(actor_id, []).append(rule.id)
        for key, value in rule.parameters.items():
            parameters[f"{rule.id}.{key}"] = value
        for predicate in [*rule.when, *rule.except_when]:
            fields.add(predicate.field)
        if rule.ambiguity:
            open_question_rule_ids.append(rule.id)

    return CompiledIndex(
        rules_by_actor=rules_by_actor,
        parameters=parameters,
        fact_fields=sorted(fields),
        open_question_rule_ids=open_question_rule_ids,
    )
