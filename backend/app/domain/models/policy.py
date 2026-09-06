"""Authoritative policy vocabulary, provenance, and independently confirmed intent."""

from typing import Annotated, Literal

from pydantic import Field, model_validator

from .common import (
    ApprovalRequirementValue,
    EffectDimensions,
    EffectDimensionValue,
    EligibilityValue,
    Identifier,
    NonEmptyText,
    NonNegativeInt,
    Percentage,
    PredicateField,
    PredicateOperator,
    ReceiptRequirementValue,
    Severity,
    Sha256,
    SourceSpan,
    StrictModel,
    Timestamp,
)

_ENUM_DOMAINS = {
    "employee_role": frozenset({"employee", "manager", "director", "executive"}),
    "expense_category": frozenset(
        {"meal", "hotel", "transport", "airfare", "incidental"}
    ),
    "destination_type": frozenset({"domestic", "international"}),
}
_INTEGER_MAX = {
    "amount_minor": 10_000_000,
    "booking_days_before": 365,
    "prior_same_day_category_spend_minor": 10_000_000,
    "daily_category_total_minor": 20_000_000,
}
_COMPARISONS = frozenset({"eq", "neq", "lt", "lte", "gt", "gte"})
OPERATORS_BY_FIELD = {
    **{field: frozenset({"eq", "neq", "in", "not_in"}) for field in _ENUM_DOMAINS},
    **{field: _COMPARISONS for field in _INTEGER_MAX},
    "receipt_present": frozenset({"eq", "neq"}),
    "approval_roles_present": frozenset({"contains"}),
}


class Predicate(StrictModel):
    field: PredicateField
    operator: PredicateOperator
    value: str | int | bool | tuple[str, ...]

    @model_validator(mode="after")
    def typed_predicate(self) -> "Predicate":
        if self.operator not in OPERATORS_BY_FIELD[self.field]:
            raise ValueError("operator is invalid for this field")
        value = self.value
        if self.field in _INTEGER_MAX:
            if type(value) is not int or not 0 <= value <= _INTEGER_MAX[self.field]:
                raise ValueError("integer predicate value is out of domain")
        elif self.field == "receipt_present":
            if type(value) is not bool:
                raise ValueError("receipt predicate requires a Boolean")
        elif self.field == "approval_roles_present":
            if value not in ("manager", "director", "finance"):
                raise ValueError(
                    "approval predicate requires a supported approval role"
                )
        else:
            domain = _ENUM_DOMAINS[self.field]
            if self.operator in ("in", "not_in"):
                if (
                    not isinstance(value, tuple)
                    or not value
                    or any(item not in domain for item in value)
                ):
                    raise ValueError(
                        "membership requires a nonempty tuple from the field domain"
                    )
            elif not isinstance(value, str) or value not in domain:
                raise ValueError("value is outside the field domain")
        return self


EffectValue = (
    EligibilityValue
    | ReceiptRequirementValue
    | ApprovalRequirementValue
    | NonNegativeInt
)
_EFFECT_VALUES = {
    "eligibility": ("allow", "deny"),
    "receipt_requirement": ("required", "not_required"),
    "approval_requirement": ("none", "manager", "director", "finance"),
}


def validate_effect_value(dimension: str, value: object) -> None:
    if dimension in _EFFECT_VALUES:
        if not isinstance(value, str) or value not in _EFFECT_VALUES[dimension]:
            raise ValueError("value is incompatible with effect dimension")
    elif type(value) is not int or value < 0:
        raise ValueError("cap effect requires a nonnegative integer")


class Effect(StrictModel):
    dimension: EffectDimensionValue
    value: EffectValue

    @model_validator(mode="after")
    def typed_effect(self) -> "Effect":
        validate_effect_value(self.dimension, self.value)
        return self


class TextRuleProvenance(StrictModel):
    kind: Literal["text_citation"] = "text_citation"
    citation_id: Identifier
    span: SourceSpan


class SessionRevisionProvenance(StrictModel):
    kind: Literal["session_revision"] = "session_revision"
    proposal_id: Identifier
    operation_index: Annotated[int, Field(ge=0, le=2)]
    confirmed_at: Timestamp
    baseline_citation_ids: Annotated[tuple[Identifier, ...], Field(min_length=1)]


RuleProvenance = Annotated[
    TextRuleProvenance | SessionRevisionProvenance, Field(discriminator="kind")
]


class OverrideRef(StrictModel):
    dimension: EffectDimensionValue
    target_rule_id: Identifier


class RuleDraft(StrictModel):
    description: NonEmptyText
    when: tuple[Predicate, ...]
    effects: Annotated[tuple[Effect, ...], Field(min_length=1)]
    overrides: tuple[OverrideRef, ...] = ()
    provenance: RuleProvenance
    confidence_percent: Percentage | None = None

    @model_validator(mode="after")
    def executable_conditions(self) -> "RuleDraft":
        if any(
            predicate.field == "daily_category_total_minor" for predicate in self.when
        ):
            raise ValueError("daily_category_total_minor is invariant-only")
        dimensions = [effect.dimension for effect in self.effects]
        if len(set(dimensions)) != len(dimensions):
            raise ValueError("a rule supplies at most one value per dimension")
        if any(edge.dimension not in dimensions for edge in self.overrides):
            raise ValueError(
                "an override must target a dimension supplied by this rule"
            )
        if len(set(self.overrides)) != len(self.overrides):
            raise ValueError("duplicate override")
        return self


class Rule(RuleDraft):
    rule_id: Identifier
    revision: NonNegativeInt = 0


class UnsupportedClause(StrictModel):
    clause_id: Identifier
    span: SourceSpan
    reason_code: Literal[
        "unsupported_vocabulary",
        "unsupported_logic",
        "ambiguous_language",
        "invalid_citation",
        "unsupported_aggregation",
        "unsupported_currency",
    ]
    affected_dimensions: Annotated[EffectDimensions, Field(min_length=1)]
    when_hint: tuple[Predicate, ...] | None = None
    review_status: Literal["provisional", "session_confirmed"] = "provisional"

    @model_validator(mode="after")
    def supported_hint(self) -> "UnsupportedClause":
        if self.when_hint and any(
            item.field == "daily_category_total_minor" for item in self.when_hint
        ):
            raise ValueError("unsupported-clause hints use stored facts only")
        return self


class PolicyPage(StrictModel):
    page: Annotated[int, Field(ge=1)]
    text: str
    start: NonNegativeInt
    end: NonNegativeInt

    @model_validator(mode="after")
    def ordered_range(self) -> "PolicyPage":
        if self.end < self.start:
            raise ValueError("page end must not precede start")
        return self


class PolicyDocument(StrictModel):
    document_id: Identifier
    title: NonEmptyText
    source_type: Literal["pasted_text", "bundled_sample"]
    pages: Annotated[tuple[PolicyPage, ...], Field(min_length=1)]
    document_sha256: Sha256

    @model_validator(mode="after")
    def unique_pages(self) -> "PolicyDocument":
        if len({page.page for page in self.pages}) != len(self.pages):
            raise ValueError("page numbers must be unique")
        return self


class PolicyIR(StrictModel):
    policy_id: Identifier
    document_sha256: Sha256
    kind: Literal["compiled_baseline", "structured_revision"] = "compiled_baseline"
    review_status: Literal["provisional", "session_confirmed"]
    base_currency: Literal["SGD"] = "SGD"
    rules: Annotated[tuple[Rule, ...], Field(max_length=12)]
    unsupported_clauses: tuple[UnsupportedClause, ...] = ()

    @model_validator(mode="after")
    def valid_rule_set(self) -> "PolicyIR":
        rules = {rule.rule_id: rule for rule in self.rules}
        if len(rules) != len(self.rules):
            raise ValueError("rule IDs must be unique")
        if self.kind == "compiled_baseline" and any(
            not isinstance(rule.provenance, TextRuleProvenance) for rule in self.rules
        ):
            raise ValueError("compiled baseline requires text citations")
        graph: dict[str, set[str]] = {rule_id: set() for rule_id in rules}
        for rule in self.rules:
            for edge in rule.overrides:
                target = rules.get(edge.target_rule_id)
                if target is None or edge.dimension not in {
                    effect.dimension for effect in target.effects
                }:
                    raise ValueError("override target and effect dimension must exist")
                graph[rule.rule_id].add(edge.target_rule_id)
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


class AssertionContent(StrictModel):
    """Typed assertion content, without oracle origins or private label references."""

    assertion_id: Identifier
    target_kind: Literal["effect_value", "compliance_value"]
    dimension: EffectDimensionValue
    operator: Literal["eq", "neq", "lte", "gte"]
    expected_value: EffectValue | Literal["COMPLIANT", "NONCOMPLIANT"]

    @model_validator(mode="after")
    def typed_assertion(self) -> "AssertionContent":
        if self.target_kind == "compliance_value":
            if (
                self.dimension == "eligibility"
                or self.expected_value not in ("COMPLIANT", "NONCOMPLIANT")
                or self.operator not in ("eq", "neq")
            ):
                raise ValueError(
                    "compliance assertion requires a requirement dimension and compliance value"
                )
        else:
            validate_effect_value(self.dimension, self.expected_value)
            if self.dimension in _EFFECT_VALUES and self.operator not in ("eq", "neq"):
                raise ValueError(
                    "categorical effect assertions support only eq and neq"
                )
        return self


class Assertion(AssertionContent):
    origin: Literal["gold", "session_confirmed", "mechanical"]
    source_invariant_id: Identifier | None = None
    gold_label_id: Identifier | None = None
    mechanical_relation_id: Identifier | None = None

    @model_validator(mode="after")
    def independent_assertion(self) -> "Assertion":
        references = {
            "gold": self.gold_label_id,
            "session_confirmed": self.source_invariant_id,
            "mechanical": self.mechanical_relation_id,
        }
        if (
            references[self.origin] is None
            or sum(value is not None for value in references.values()) != 1
        ):
            raise ValueError(
                "assertion requires exactly its independent origin reference"
            )
        return self


class InvariantDraft(StrictModel):
    invariant_id: Identifier
    description: NonEmptyText
    when: tuple[Predicate, ...]
    assertion: Assertion
    severity: Severity

    @model_validator(mode="after")
    def assertion_matches_invariant(self) -> "InvariantDraft":
        if (
            self.assertion.origin != "session_confirmed"
            or self.assertion.source_invariant_id != self.invariant_id
        ):
            raise ValueError(
                "invariant assertion must reference this session invariant"
            )
        return self


class Invariant(InvariantDraft):
    origin: Literal["session_confirmed"] = "session_confirmed"


class PolicyContract(StrictModel):
    contract_id: Identifier
    required_dimensions: Annotated[EffectDimensions, Field(min_length=1)]
    invariants: Annotated[tuple[Invariant, ...], Field(min_length=3, max_length=5)]

    @model_validator(mode="after")
    def unique_invariants(self) -> "PolicyContract":
        if len({item.invariant_id for item in self.invariants}) != len(self.invariants):
            raise ValueError("invariant IDs must be unique")
        if len({item.assertion.assertion_id for item in self.invariants}) != len(
            self.invariants
        ):
            raise ValueError("invariant assertion IDs must be unique")
        return self


class PolicyExtraction(StrictModel):
    document_sha256: Sha256
    rules: tuple[RuleDraft, ...]
    unsupported_clauses: tuple[UnsupportedClause, ...] = ()


class CompilePolicyRequest(StrictModel):
    document: PolicyDocument
    extraction: PolicyExtraction


class PolicyCompilation(StrictModel):
    policy: PolicyIR
    excluded_rule_count: NonNegativeInt = 0
