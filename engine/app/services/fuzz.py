"""IR-driven fuzz designer: PolicyIR + seed → ≤50 Scenario agents."""

from __future__ import annotations

import hashlib
import random
import re
from typing import Any

from app.contracts.policy import ActorType, AttributeSchema, PolicyIR, Predicate, Rule
from app.contracts.run import AudienceSegment, SeedSpec
from app.contracts.scenario import Scenario, ScenarioKind, ScenarioSuite
from app.plugins.scenario_designer import ScenarioDesigner

DEFAULT_MAX_AGENTS = 50

# Locale-neutral name pool (not tied to any single country).
FIRST = [
    "Alex", "Sam", "Jordan", "Taylor", "Morgan", "Casey", "Riley", "Avery",
    "Quinn", "Jamie", "Cameron", "Drew", "Skyler", "Reese", "Harper",
    "Kai", "Noa", "Milan", "Elena", "Omar", "Sofia", "Kenji", "Amara", "Priya",
]
LAST = [
    "Rivera", "Chen", "Patel", "Nguyen", "Kim", "Garcia", "Hassan", "Silva",
    "Park", "Ali", "Brooks", "Singh", "Costa", "Berg", "Okoye", "Diaz",
]


class FuzzDesigner(ScenarioDesigner):
    """Turn compiled rules into named test agents for the grader and the swarm."""

    def __init__(self, max_agents: int = DEFAULT_MAX_AGENTS):
        self.max_agents = max(1, min(max_agents, DEFAULT_MAX_AGENTS))

    def generate(self, ir: PolicyIR, seed: SeedSpec) -> ScenarioSuite:
        requested = seed.population_size or self.max_agents
        n = max(1, min(int(requested), self.max_agents))
        rng = random.Random(_seed_int(seed.text or ir.policy_id))
        plan = _coverage_plan(ir, n)
        segments = _resolve_segments(seed, ir)
        scenarios = [
            _build_scenario(index, ir, seed, kind, rule, segments, rng)
            for index, (kind, rule) in enumerate(plan)
        ]
        return ScenarioSuite(
            policy_id=ir.policy_id,
            policy_revision=ir.revision,
            seed=seed.text or _segments_summary(segments),
            population_size=n,
            scenarios=scenarios,
        )


def _seed_int(text: str) -> int:
    return int.from_bytes(hashlib.sha256(text.encode("utf-8")).digest(), "big")


def _resolve_segments(seed: SeedSpec, ir: PolicyIR) -> list[AudienceSegment]:
    if seed.segments:
        return [item for item in seed.segments if item.id.strip()]
    groups = seed.groups or [actor.id for actor in ir.actor_types] or ["resident"]
    return [
        AudienceSegment(id=group, label=group.replace("_", " "), weight=1.0)
        for group in groups
    ]


def _segments_summary(segments: list[AudienceSegment]) -> str:
    if not segments:
        return ""
    parts = []
    for item in segments:
        label = item.label or item.id
        attrs = ", ".join(f"{k}={v}" for k, v in list(item.attributes.items())[:4])
        parts.append(f"{label} (weight {item.weight})" + (f": {attrs}" if attrs else ""))
    return "Audience segments: " + "; ".join(parts)


def _pick_segment(segments: list[AudienceSegment], index: int, rng: random.Random) -> AudienceSegment:
    if not segments:
        return AudienceSegment(id="resident", label="Resident", weight=1.0)
    weights = [max(float(item.weight), 0.01) for item in segments]
    if rng.random() < 0.75:
        return rng.choices(segments, weights=weights, k=1)[0]
    return segments[index % len(segments)]


def _coverage_plan(ir: PolicyIR, n: int) -> list[tuple[ScenarioKind, Rule]]:
    rules = ir.rules or []
    if not rules:
        placeholder = Rule(id="R001", title="empty", statement="no rules")
        return [("normal", placeholder) for _ in range(n)]
    open_ids = set(ir.index.open_question_rule_ids)
    plan: list[tuple[ScenarioKind, Rule]] = []
    # Cover distinct rules before assigning another probe to an earlier rule.
    # Rotate kinds across both rules and rounds to retain diversity at small caps.
    round_index = 0
    while len(plan) < n:
        for rule_index, rule in enumerate(rules):
            kinds: tuple[ScenarioKind, ...] = ("normal", "boundary", "adversarial")
            if rule.ambiguity or rule.id in open_ids:
                kinds += ("targeted",)
            plan.append((kinds[(rule_index + round_index) % len(kinds)], rule))
            if len(plan) == n:
                break
        round_index += 1
    return plan


def _build_scenario(
    index: int,
    ir: PolicyIR,
    seed: SeedSpec,
    kind: ScenarioKind,
    rule: Rule,
    segments: list[AudienceSegment],
    rng: random.Random,
) -> Scenario:
    actor = _pick_actor(ir, rule)
    action_name = _action_for(ir, rule, kind)
    segment = _pick_segment(segments, index, rng)
    group = segment.id
    facts = _base_facts(ir, actor, action_name, group, rng)
    facts["actor.name"] = f"{rng.choice(FIRST)} {rng.choice(LAST)}"
    facts["actor.group"] = group
    facts["actor.segment"] = segment.label or segment.id
    for key, value in segment.attributes.items():
        field = key if "." in key else f"actor.{key}"
        facts[field] = value
    if seed.locale:
        facts["context.locale"] = seed.locale
    _apply_predicates(facts, rule.when)
    if kind == "boundary":
        _nudge_boundary(facts, rule)
    elif kind == "adversarial":
        _make_adversarial(facts, ir, rule)
    elif kind == "targeted":
        _make_targeted(facts, ir, rule)
    else:
        if _modality(rule) == "must_not":
            facts["action.name"] = _safe_action(ir, rule)
    targeted = [rule.id] if rule.id else []
    if kind == "targeted" and ir.open_questions:
        facts["context.open_question"] = ir.open_questions[index % len(ir.open_questions)]
    return Scenario(
        kind=kind,
        title=f"{kind} · {rule.id} · {facts['actor.name']}",
        narrative=_narrative(facts, kind, rule),
        facts=facts,
        targeted_rule_ids=targeted,
        # Probe kind describes how facts were generated, not a policy-owner oracle.
        expected_outcome=None,
        notes=rule.ambiguity or "",
    )


def _pick_actor(ir: PolicyIR, rule: Rule) -> ActorType:
    wanted = (rule.applies_to or [None])[0]
    for actor in ir.actor_types:
        if actor.id == wanted:
            return actor
    return ir.actor_types[0] if ir.actor_types else ActorType(id="resident", label="Resident")


def _action_for(ir: PolicyIR, rule: Rule, kind: ScenarioKind) -> str:
    named = [item.action for item in rule.then if item.action]
    if kind == "adversarial" and _modality(rule) == "must_not" and named:
        return named[0]
    if kind != "adversarial" and _modality(rule) == "must_not":
        return _safe_action(ir, rule)
    if named:
        return named[0]
    if ir.actions:
        return ir.actions[0].name
    return "comply"


def _safe_action(ir: PolicyIR, rule: Rule) -> str:
    forbidden = {item.action for item in rule.then}
    for action in ir.actions:
        if action.name not in forbidden:
            return action.name
    return "comply"


def _modality(rule: Rule) -> str:
    return rule.then[0].modality if rule.then else "must"


def _base_facts(
    ir: PolicyIR,
    actor: ActorType,
    action_name: str,
    group: str,
    rng: random.Random,
) -> dict[str, Any]:
    facts: dict[str, Any] = {
        "actor.role": actor.id,
        "actor.group": group,
        "action.name": action_name,
        "context.location": group.replace("_", " "),
    }
    for attr in actor.attributes:
        if attr.name in {"role", "name"}:
            continue
        facts[f"actor.{attr.name}"] = _sample_attr(attr, rng)
    for action in ir.actions:
        if action.name != action_name:
            continue
        for attr in action.attributes:
            facts[f"action.{attr.name}"] = _sample_attr(attr, rng)
    for field in ir.index.fact_fields:
        facts.setdefault(field, _default_for_field(field, rng))
    return facts


def _sample_attr(attr: AttributeSchema, rng: random.Random) -> Any:
    if attr.enum_values:
        return rng.choice(attr.enum_values)
    if attr.value_type == "boolean":
        return False
    if attr.value_type in {"integer", "number"}:
        low = int(attr.minimum) if attr.minimum is not None else 21
        high = int(attr.maximum) if attr.maximum is not None else max(low + 20, 64)
        if high <= low:
            high = low + 1
        return rng.randint(low, high)
    return attr.description or attr.name


def _default_for_field(field: str, rng: random.Random) -> Any:
    if field.endswith(".age"):
        return rng.randint(18, 70)
    if field.endswith(".name"):
        return "unnamed"
    if "amount" in field:
        return 0
    if field.startswith("action."):
        return "comply" if field.endswith(".name") else ""
    return ""


def _apply_predicates(facts: dict[str, Any], predicates: list[Predicate]) -> None:
    for predicate in predicates:
        facts[predicate.field] = _matching_value(predicate)


def _matching_value(predicate: Predicate, *, invert: bool = False) -> Any:
    op = predicate.op
    value = predicate.value
    if op == "eq":
        return _other(value) if invert else value
    if op == "neq":
        return value if invert else _other(value)
    if op in {"gt", "gte"}:
        number = _as_number(value, 0)
        return number - 1 if invert else (number + 1 if op == "gt" else number)
    if op in {"lt", "lte"}:
        number = _as_number(value, 0)
        return number + 1 if invert else (number - 1 if op == "lt" else number)
    if op == "in":
        options = list(value) if isinstance(value, (list, tuple)) else [value]
        if invert:
            return f"not_{options[0]}" if options else "other"
        return options[0] if options else value
    if op == "not_in":
        options = list(value) if isinstance(value, (list, tuple)) else [value]
        if invert:
            return options[0] if options else value
        return f"not_{options[0]}" if options else "other"
    if op == "exists":
        return None if invert else True
    if op == "between" and isinstance(value, (list, tuple)) and len(value) == 2:
        low, high = _as_number(value[0], 0), _as_number(value[1], 1)
        return low - 1 if invert else (low + high) / 2
    return value


def _other(value: Any) -> Any:
    if isinstance(value, bool):
        return not value
    if isinstance(value, (int, float)):
        return value + 1
    return f"not_{value}"


def _as_number(value: Any, default: float) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _nudge_boundary(facts: dict[str, Any], rule: Rule) -> None:
    for predicate in [*rule.when, *rule.except_when]:
        if predicate.op in {"gt", "gte", "lt", "lte", "between"}:
            facts[predicate.field] = _matching_value(predicate)
            return
    for key, value in rule.parameters.items():
        if isinstance(value, (int, float)):
            field = _parameter_field(key)
            facts[field] = value
            return
    for key, value in list(facts.items()):
        if isinstance(value, (int, float)) and not isinstance(value, bool):
            facts[key] = value
            return


def _parameter_field(key: str) -> str:
    name = key.lower()
    if "age" in name:
        return "actor.age"
    if "warning" in name:
        return "context.warnings"
    if "day" in name or "hour" in name:
        return "context.days"
    if "amount" in name or "dollar" in name:
        return "action.amount"
    return f"context.{re.sub(r'[^a-z0-9]+', '_', name)}"


def _make_adversarial(facts: dict[str, Any], ir: PolicyIR, rule: Rule) -> None:
    _apply_predicates(facts, rule.when)
    if _modality(rule) == "must_not" and rule.then:
        facts["action.name"] = rule.then[0].action
        return
    if rule.except_when:
        _apply_predicates(facts, rule.except_when)
        return
    if rule.when:
        facts[rule.when[0].field] = _matching_value(rule.when[0], invert=True)
        return
    facts["action.name"] = _safe_action(ir, rule) if _modality(rule) == "must" else facts.get("action.name")


def _make_targeted(facts: dict[str, Any], ir: PolicyIR, rule: Rule) -> None:
    _apply_predicates(facts, rule.when)
    if rule.except_when:
        _apply_predicates(facts, rule.except_when)
    facts["context.ambiguity"] = rule.ambiguity or (ir.open_questions[0] if ir.open_questions else "unclear")


def _narrative(facts: dict[str, Any], kind: ScenarioKind, rule: Rule) -> str:
    name = facts.get("actor.name", "A resident")
    role = facts.get("actor.segment") or facts.get("actor.role", "resident")
    action = facts.get("action.name", "act")
    return (
        f"{name} is a {role} running a {kind} probe of {rule.id} "
        f"({rule.title or rule.statement[:80]}). Intended action: {action}."
    )
