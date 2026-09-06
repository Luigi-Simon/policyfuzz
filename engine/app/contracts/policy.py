from typing import Any, Literal

from pydantic import BaseModel, Field

from app.contracts.common import Citation, JsonDict, new_id, now_iso

Op = Literal[
    "eq",
    "neq",
    "in",
    "not_in",
    "gt",
    "gte",
    "lt",
    "lte",
    "exists",
    "matches",
    "between",
]

Modality = Literal["must", "must_not", "may", "should"]
Severity = Literal["critical", "high", "medium", "low"]
ValueType = Literal["string", "integer", "number", "boolean", "enum", "datetime"]


class AttributeSchema(BaseModel):
    """Typed field person 3 should fill when synthesizing a scenario fact."""

    name: str
    value_type: ValueType = "string"
    enum_values: list[str] | None = None
    minimum: float | None = None
    maximum: float | None = None
    description: str = ""


class ActorType(BaseModel):
    id: str
    label: str
    description: str = ""
    attributes: list[AttributeSchema] = Field(default_factory=list)


class ActionSpec(BaseModel):
    """An action a scenario may attempt (use_phone, confiscate, appeal, ...)."""

    name: str
    description: str = ""
    attributes: list[AttributeSchema] = Field(default_factory=list)


class Predicate(BaseModel):
    """Atomic condition, evaluable against scenario.facts.

    `field` uses dotted paths into the scenario fact bag, for example:
      actor.role, actor.grade, action.name, context.location, context.time
    """

    field: str
    op: Op = "eq"
    value: Any = None


class Obligation(BaseModel):
    modality: Modality
    action: str
    assignee: str = "actor"
    details: str = ""


class Rule(BaseModel):
    id: str
    title: str
    statement: str
    citations: list[Citation] = Field(default_factory=list)
    applies_to: list[str] = Field(default_factory=list)
    when: list[Predicate] = Field(default_factory=list)
    then: list[Obligation] = Field(default_factory=list)
    except_when: list[Predicate] = Field(default_factory=list)
    parameters: JsonDict = Field(default_factory=dict)
    severity: Severity = "medium"
    tags: list[str] = Field(default_factory=list)
    ambiguity: str | None = None


class CompiledIndex(BaseModel):
    """Derived lookup tables. Rebuilt on every compile — do not edit by hand."""

    rules_by_actor: dict[str, list[str]] = Field(default_factory=dict)
    parameters: JsonDict = Field(default_factory=dict)
    fact_fields: list[str] = Field(default_factory=list)
    open_question_rule_ids: list[str] = Field(default_factory=list)


class PolicyDocument(BaseModel):
    """Ingested source. Person 2 starts here."""

    document_id: str = Field(default_factory=lambda: new_id("doc"))
    filename: str
    media_type: str = "application/pdf"
    page_count: int = 0
    text: str = ""
    pages: list[str] = Field(default_factory=list)
    created_at: str = Field(default_factory=now_iso)


class ChangeLogEntry(BaseModel):
    revision: int
    instruction: str
    summary: str
    at: str = Field(default_factory=now_iso)


class PolicyIR(BaseModel):
    """Compiled policy. This is the handoff from person 2 to person 3."""

    schema_version: str = "1.0.0"
    policy_id: str = Field(default_factory=lambda: new_id("pol"))
    title: str
    jurisdiction: str | None = None
    source: PolicyDocument
    actor_types: list[ActorType] = Field(default_factory=list)
    actions: list[ActionSpec] = Field(default_factory=list)
    rules: list[Rule] = Field(default_factory=list)
    glossary: dict[str, str] = Field(default_factory=dict)
    open_questions: list[str] = Field(default_factory=list)
    conflicts: list[str] = Field(default_factory=list)
    index: CompiledIndex = Field(default_factory=CompiledIndex)
    revision: int = 1
    parent_revision: int | None = None
    change_log: list[ChangeLogEntry] = Field(default_factory=list)
    compiled_at: str = Field(default_factory=now_iso)

    def rule_map(self) -> dict[str, Rule]:
        return {rule.id: rule for rule in self.rules}
