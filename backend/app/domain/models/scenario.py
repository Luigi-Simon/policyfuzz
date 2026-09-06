"""Complete facts, exploratory candidates, frozen suites and coverage evidence."""

from typing import Annotated, Literal

from pydantic import BeforeValidator, Field, model_validator

from .common import (
    ApprovalRoles,
    DestinationType,
    EmployeeRole,
    ExpenseCategory,
    Identifier,
    MoneyMinor,
    NonEmptyText,
    NonNegativeInt,
    Sha256,
    StrictModel,
    _freeze_set,
)
from .policy import Assertion, PolicyContract, PolicyIR

ScenarioOrigin = Literal["gold", "session", "mechanical", "llm_exploratory"]
ScenarioOrigins = Annotated[
    frozenset[ScenarioOrigin], BeforeValidator(_freeze_set), Field(min_length=1)
]
ScenarioCategory = Literal["normal", "boundary", "adversarial"]
ScenarioPartition = Literal["visible", "holdout"]


class ScenarioFacts(StrictModel):
    employee_role: EmployeeRole
    expense_category: ExpenseCategory
    amount_minor: MoneyMinor
    destination_type: DestinationType
    booking_days_before: Annotated[int, Field(ge=0, le=365)]
    receipt_present: bool
    approval_roles_present: ApprovalRoles
    prior_same_day_category_spend_minor: MoneyMinor


class ScenarioCandidate(StrictModel):
    candidate_id: Identifier
    category: ScenarioCategory
    origins: ScenarioOrigins
    facts: ScenarioFacts
    target_rule_ids: tuple[Identifier, ...] = ()
    target_invariant_ids: tuple[Identifier, ...] = ()
    assertions: tuple[Assertion, ...] = ()
    protected: bool = False
    partition: ScenarioPartition = "visible"

    @model_validator(mode="after")
    def independent_assertions(self) -> "ScenarioCandidate":
        origin_mapping = {
            "gold": "gold",
            "session_confirmed": "session",
            "mechanical": "mechanical",
        }
        if any(
            origin_mapping[item.origin] not in self.origins for item in self.assertions
        ):
            raise ValueError(
                "scored assertions require independently sourced scenario origins"
            )
        if len({item.assertion_id for item in self.assertions}) != len(self.assertions):
            raise ValueError("assertion IDs must be unique within a scenario")
        return self


class ScenarioBatch(StrictModel):
    candidates: tuple[ScenarioCandidate, ...]


class Scenario(StrictModel):
    scenario_id: Identifier
    category: ScenarioCategory
    origins: ScenarioOrigins
    facts: ScenarioFacts
    target_rule_ids: tuple[Identifier, ...] = ()
    target_invariant_ids: tuple[Identifier, ...] = ()
    assertions: tuple[Assertion, ...] = ()
    protected: bool = False
    partition: ScenarioPartition = "visible"

    @model_validator(mode="after")
    def independent_assertions(self) -> "Scenario":
        origin_mapping = {
            "gold": "gold",
            "session_confirmed": "session",
            "mechanical": "mechanical",
        }
        if any(
            origin_mapping[item.origin] not in self.origins for item in self.assertions
        ):
            raise ValueError(
                "scored assertions require independently sourced scenario origins"
            )
        if len({item.assertion_id for item in self.assertions}) != len(self.assertions):
            raise ValueError("assertion IDs must be unique within a scenario")
        return self


class ScenarioRejection(StrictModel):
    candidate_id: Identifier
    reason_code: Literal[
        "invalid_facts",
        "invalid_assertion",
        "duplicate",
        "budget_exceeded",
        "incompatible_assertions",
    ]
    duplicate_of: Identifier | None = None


class SuiteStatistics(StrictModel):
    generated_count: NonNegativeInt = 0
    rejected_count: NonNegativeInt = 0
    duplicate_count: NonNegativeInt = 0
    rejections: tuple[ScenarioRejection, ...] = ()


class ScenarioSuite(StrictModel):
    suite_id: Identifier
    content_sha256: Sha256
    seed: NonNegativeInt
    document_sha256: Sha256
    policy_contract_sha256: Sha256
    rule_set_sha256: Sha256
    engine_version: NonEmptyText
    scenarios: Annotated[tuple[Scenario, ...], Field(min_length=1, max_length=15)]
    statistics: SuiteStatistics = Field(default_factory=SuiteStatistics)

    @model_validator(mode="after")
    def unique_scenarios(self) -> "ScenarioSuite":
        if len({item.scenario_id for item in self.scenarios}) != len(self.scenarios):
            raise ValueError("scenario IDs must be unique")
        return self


class CoverageEvidence(StrictModel):
    target_kind: Literal["rule", "invariant", "predicate_branch"]
    target_id: Identifier
    scenario_ids: tuple[Identifier, ...]
    predicate_index: NonNegativeInt | None = None
    predicate_outcome: bool | None = None

    @model_validator(mode="after")
    def branch_coordinates(self) -> "CoverageEvidence":
        branch = self.target_kind == "predicate_branch"
        if branch != (
            self.predicate_index is not None and self.predicate_outcome is not None
        ):
            raise ValueError("predicate branch evidence requires index and outcome")
        if not branch and (
            self.predicate_index is not None or self.predicate_outcome is not None
        ):
            raise ValueError(
                "rule and invariant evidence do not use branch coordinates"
            )
        return self


class CoverageSnapshot(StrictModel):
    total_rules: NonNegativeInt = 0
    covered_rules: NonNegativeInt = 0
    total_invariants: NonNegativeInt = 0
    covered_invariants: NonNegativeInt = 0
    total_predicate_branches: NonNegativeInt = 0
    covered_predicate_branches: NonNegativeInt = 0
    evidence: tuple[CoverageEvidence, ...] = ()
    missing_rule_ids: tuple[Identifier, ...] = ()
    missing_invariant_ids: tuple[Identifier, ...] = ()
    targeted_cycles: Annotated[int, Field(ge=0, le=1)] = 0
    status: Literal["pending", "satisfied", "COVERAGE_LIMIT_EXCEEDED"] = "pending"

    @model_validator(mode="after")
    def bounded_counts(self) -> "CoverageSnapshot":
        if (
            self.covered_rules > self.total_rules
            or self.covered_invariants > self.total_invariants
            or self.covered_predicate_branches > self.total_predicate_branches
        ):
            raise ValueError("covered count cannot exceed total")
        if self.status == "satisfied" and (
            self.covered_rules != self.total_rules
            or self.covered_invariants != self.total_invariants
            or self.missing_rule_ids
            or self.missing_invariant_ids
        ):
            raise ValueError("minimum rule and invariant coverage is required")
        return self


class GenerateInitialScenariosRequest(StrictModel):
    policy: PolicyIR
    contract: PolicyContract
    seed: NonNegativeInt
    scenario_budget: Annotated[int, Field(ge=1, le=15)] = 15


class GenerateTargetedScenariosRequest(GenerateInitialScenariosRequest):
    existing_candidates: tuple[ScenarioCandidate, ...]
    coverage: CoverageSnapshot
    targeted_cycle: Annotated[int, Field(ge=1, le=1)] = 1


class AssembleSuiteRequest(StrictModel):
    suite_id: Identifier
    document_sha256: Sha256
    policy_contract_sha256: Sha256
    rule_set_sha256: Sha256
    engine_version: NonEmptyText
    seed: NonNegativeInt
    candidates: tuple[ScenarioCandidate, ...]
