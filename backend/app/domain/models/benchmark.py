"""Private benchmark schema definitions, never generated or executed oracles."""

from typing import Annotated

from pydantic import Field, model_validator

from .common import Identifier, NonNegativeInt, Sha256, SourceSpan, StrictModel
from .policy import PolicyDocument
from .revision import RevisionRuleDraft


class BenchmarkSourceLabel(StrictModel):
    label_id: Identifier
    source_span: SourceSpan
    rule_ids: tuple[Identifier, ...]
    unsupported_clause_id: Identifier | None = None

    @model_validator(mode="after")
    def supported_label(self) -> "BenchmarkSourceLabel":
        if not self.rule_ids and self.unsupported_clause_id is None:
            raise ValueError("a label requires a rule or unsupported clause")
        if len(set(self.rule_ids)) != len(self.rule_ids):
            raise ValueError("label rule IDs must be unique")
        return self


class BenchmarkSourceLabels(StrictModel):
    document: PolicyDocument
    labels: tuple[BenchmarkSourceLabel, ...]

    @model_validator(mode="after")
    def unique_labels(self) -> "BenchmarkSourceLabels":
        if len({item.label_id for item in self.labels}) != len(self.labels):
            raise ValueError("label IDs must be unique")
        return self


class BenchmarkExpectedRule(StrictModel):
    rule_id: Identifier
    revision: NonNegativeInt
    rule: RevisionRuleDraft


class BenchmarkCorrectedSemantics(StrictModel):
    document_sha256: Sha256
    baseline_policy_sha256: Sha256
    rules: Annotated[
        tuple[BenchmarkExpectedRule, ...], Field(min_length=1, max_length=12)
    ]

    @model_validator(mode="after")
    def valid_expected_rules(self) -> "BenchmarkCorrectedSemantics":
        rules = {item.rule_id: item.rule for item in self.rules}
        if len(rules) != len(self.rules):
            raise ValueError("expected rule IDs must be unique")
        graph: dict[str, set[str]] = {rule_id: set() for rule_id in rules}
        for rule_id, rule in rules.items():
            for edge in rule.overrides:
                target = rules.get(edge.target_rule_id)
                if target is None or edge.dimension not in {
                    effect.dimension for effect in target.effects
                }:
                    raise ValueError("override target and dimension must exist")
                graph[rule_id].add(edge.target_rule_id)
        visiting: set[str] = set()
        visited: set[str] = set()

        def visit(rule_id: str) -> None:
            if rule_id in visiting:
                raise ValueError("override cycles are invalid")
            if rule_id in visited:
                return
            visiting.add(rule_id)
            for target in graph[rule_id]:
                visit(target)
            visiting.remove(rule_id)
            visited.add(rule_id)

        for rule_id in graph:
            visit(rule_id)
        return self
