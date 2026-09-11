"""Canonical public models for the deterministic v2 Metric backend."""

from __future__ import annotations

import re
from enum import Enum
from typing import Annotated, Literal, TypeAlias

from pydantic import Field, field_validator, model_validator

from .contracts import ContractModel

_ID_PATTERN = r"^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$"
_HASH_PATTERN = r"^[0-9a-f]{64}$"
_HAN_SCRIPT = re.compile(
    r"[\u3400-\u4dbf\u4e00-\u9fff\uf900-\ufaff\U00020000-\U0003134f]"
)


def _english(value: str) -> str:
    if _HAN_SCRIPT.search(value):
        raise ValueError("public Metric text must use English display text")
    return value


class ReviewStatus(str, Enum):
    READY = "ready"
    NEEDS_CLARIFICATION = "needs_clarification"


class MetricRunStatus(str, Enum):
    COMPLETED = "completed"
    PARTIAL = "partial"
    NEEDS_CLARIFICATION = "needs_clarification"


class CaseCategory(str, Enum):
    NORMAL = "normal"
    BOUNDARY = "boundary"
    COMPOUND = "compound"
    CASCADING = "cascading"
    ADVERSARIAL = "adversarial"


class CaseVerdict(str, Enum):
    PASS = "pass"
    FAIL = "fail"
    UNSCORED = "unscored"


class ClaimStatus(str, Enum):
    SUBMITTED = "submitted"
    APPROVED = "approved"
    PAID = "paid"
    CANCELLED = "cancelled"


class PolicyClause(ContractModel):
    id: str = Field(pattern=_ID_PATTERN)
    text: str = Field(min_length=1, max_length=1_000)

    _text_is_english = field_validator("text")(_english)


class PolicyGoal(ContractModel):
    id: str = Field(pattern=_ID_PATTERN)
    text: str = Field(min_length=1, max_length=1_000)
    clause_ids: tuple[str, ...] = Field(min_length=1, max_length=8)

    _text_is_english = field_validator("text")(_english)

    @field_validator("clause_ids")
    @classmethod
    def clause_ids_are_unique_ascii(cls, values: tuple[str, ...]) -> tuple[str, ...]:
        if len(values) != len(set(values)):
            raise ValueError("goal clause IDs must be unique")
        if any(re.fullmatch(_ID_PATTERN, value) is None for value in values):
            raise ValueError("goal clause IDs must be ASCII identifiers")
        return values


class MetricRules(ContractModel):
    per_claim_limit_cents: int = Field(strict=True, ge=1, le=10_000_000)
    participant_allowance_cents: int = Field(strict=True, ge=1, le=100_000_000)
    approval_budget_accounting: Literal["paid_only", "paid_and_approved"]
    payment_budget_recheck: bool
    duplicate_scope: Literal["claim_id", "journey"]


class NumericCondition(ContractModel):
    """One source-bound comparison, never an inferred whole-policy decision."""

    id: str = Field(pattern=_ID_PATTERN)
    clause_id: str = Field(pattern=_ID_PATTERN)
    field: Literal[
        "age_years",
        "assessable_income_cents",
        "annual_income_cents",
        "monthly_income_cents",
        "annual_value_cents",
        "property_count",
        "rest_minutes",
        "notice_days",
        "weekly_work_minutes",
    ]
    operator: Literal["ge", "gt", "le", "lt", "eq"]
    threshold: int = Field(strict=True, ge=0, le=100_000_000)
    source_start: int = Field(strict=True, ge=0)
    source_end: int = Field(strict=True, ge=1)
    source_sha256: str = Field(pattern=_HASH_PATTERN)

    @model_validator(mode="after")
    def source_range_is_valid(self):
        if self.source_end <= self.source_start:
            raise ValueError("condition source range must be nonempty")
        return self


class PolicyConditions(ContractModel):
    kind: Literal["policy_conditions"] = "policy_conditions"
    conditions: tuple[NumericCondition, ...] = Field(min_length=1, max_length=12)


class EvaluateConditionAction(ContractModel):
    action: Literal["evaluate_condition"] = "evaluate_condition"
    condition_id: str = Field(pattern=_ID_PATTERN)
    value: int = Field(strict=True, ge=-1, le=100_000_001)


class ClaimRecord(ContractModel):
    claim_id: str = Field(pattern=_ID_PATTERN)
    participant_id: str = Field(pattern=_ID_PATTERN)
    journey_id: str = Field(pattern=_ID_PATTERN)
    amount_cents: int = Field(strict=True, ge=0, le=100_000_000)
    status: ClaimStatus


class ParticipantTotals(ContractModel):
    participant_id: str = Field(pattern=_ID_PATTERN)
    paid_cents: int = Field(strict=True, ge=0, le=100_000_000)
    reserved_cents: int = Field(strict=True, ge=0, le=100_000_000)


class MetricState(ContractModel):
    claims: tuple[ClaimRecord, ...] = Field(default=(), max_length=64)
    participants: tuple[ParticipantTotals, ...] = Field(default=(), max_length=32)

    @model_validator(mode="after")
    def identifiers_are_unique(self) -> MetricState:
        claim_ids = [claim.claim_id for claim in self.claims]
        participant_ids = [
            participant.participant_id for participant in self.participants
        ]
        if len(claim_ids) != len(set(claim_ids)):
            raise ValueError("claim IDs must be unique")
        if len(participant_ids) != len(set(participant_ids)):
            raise ValueError("participant IDs must be unique")
        return self


class SubmitAction(ContractModel):
    action: Literal["submit"] = "submit"
    claim_id: str = Field(pattern=_ID_PATTERN)
    participant_id: str = Field(pattern=_ID_PATTERN)
    journey_id: str = Field(pattern=_ID_PATTERN)
    amount_cents: int = Field(strict=True, ge=-100_000_000, le=100_000_000)


class ApproveAction(ContractModel):
    action: Literal["approve"] = "approve"
    claim_id: str = Field(pattern=_ID_PATTERN)


class PayAction(ContractModel):
    action: Literal["pay"] = "pay"
    claim_id: str = Field(pattern=_ID_PATTERN)


class CancelAction(ContractModel):
    action: Literal["cancel"] = "cancel"
    claim_id: str = Field(pattern=_ID_PATTERN)


class UnsupportedAction(ContractModel):
    action: str = Field(pattern=r"^[a-z][a-z0-9_]{0,31}$")
    parameters: tuple[str, ...] = Field(default=(), max_length=16)

    @model_validator(mode="after")
    def action_is_not_supported(self) -> UnsupportedAction:
        if self.action in {"submit", "approve", "pay", "cancel", "evaluate_condition"}:
            raise ValueError("supported action requires its typed fields")
        return self


MetricAction: TypeAlias = Annotated[  # noqa: UP040 - retain inline schema compatibility
    SubmitAction
    | ApproveAction
    | PayAction
    | CancelAction
    | EvaluateConditionAction
    | UnsupportedAction,
    Field(union_mode="left_to_right"),
]


class AssertionResult(ContractModel):
    requirement_id: str = Field(pattern=_ID_PATTERN)
    passed: bool
    expected: str = Field(min_length=1, max_length=1_000)
    actual: str = Field(min_length=1, max_length=1_000)
    step_refs: tuple[str, ...] = Field(min_length=1, max_length=32)

    _expected_is_english = field_validator("expected")(_english)
    _actual_is_english = field_validator("actual")(_english)

    @field_validator("step_refs")
    @classmethod
    def step_refs_are_unique_ascii(cls, values: tuple[str, ...]) -> tuple[str, ...]:
        if len(values) != len(set(values)):
            raise ValueError("assertion step references must be unique")
        if any(re.fullmatch(_ID_PATTERN, value) is None for value in values):
            raise ValueError("assertion step references must be ASCII identifiers")
        return values


class TraceStep(ContractModel):
    step_id: str = Field(pattern=_ID_PATTERN)
    action_index: int = Field(strict=True, ge=0, le=63)
    action: MetricAction
    accepted: bool
    detail: str = Field(min_length=1, max_length=1_000)
    before_state_sha256: str = Field(pattern=_HASH_PATTERN)
    after_state_sha256: str = Field(pattern=_HASH_PATTERN)
    participant_paid_cents_before: int = Field(strict=True, ge=0)
    participant_paid_cents_after: int = Field(strict=True, ge=0)
    participant_reserved_cents_before: int = Field(strict=True, ge=0)
    participant_reserved_cents_after: int = Field(strict=True, ge=0)

    _detail_is_english = field_validator("detail")(_english)


class ConditionTraceStep(ContractModel):
    step_id: str = Field(pattern=_ID_PATTERN)
    action_index: int = Field(strict=True, ge=0, le=63)
    action: EvaluateConditionAction
    matches: bool
    detail: str = Field(min_length=1, max_length=1_000)
    before_state_sha256: str = Field(pattern=_HASH_PATTERN)
    after_state_sha256: str = Field(pattern=_HASH_PATTERN)

    _detail_is_english = field_validator("detail")(_english)


class MetricCaseResult(ContractModel):
    case_id: str = Field(pattern=_ID_PATTERN)
    title: str = Field(min_length=1, max_length=200)
    category: CaseCategory
    plausibility: str = Field(min_length=1, max_length=1_000)
    initial_state: MetricState
    actions: tuple[MetricAction, ...] = Field(min_length=1, max_length=32)
    trace: tuple[TraceStep | ConditionTraceStep, ...] = Field(default=(), max_length=32)
    assertions: tuple[AssertionResult, ...] = Field(default=(), max_length=16)
    verdict: CaseVerdict
    unscored_reason: str | None = Field(default=None, max_length=1_000)
    minimal_actions: tuple[MetricAction, ...] | None = Field(
        default=None, max_length=32
    )

    _title_is_english = field_validator("title")(_english)
    _plausibility_is_english = field_validator("plausibility")(_english)

    @field_validator("unscored_reason")
    @classmethod
    def reason_is_english(cls, value: str | None) -> str | None:
        return None if value is None else _english(value)

    @model_validator(mode="after")
    def verdict_and_references_are_consistent(self) -> MetricCaseResult:
        step_ids = [step.step_id for step in self.trace]
        if len(step_ids) != len(set(step_ids)):
            raise ValueError("trace step IDs must be unique")
        step_id_set = set(step_ids)
        for assertion in self.assertions:
            if not set(assertion.step_refs) <= step_id_set:
                raise ValueError("assertion references unknown trace step")
        requirement_ids = [assertion.requirement_id for assertion in self.assertions]
        if len(requirement_ids) != len(set(requirement_ids)):
            raise ValueError("case assertion requirement IDs must be unique")

        if self.verdict is CaseVerdict.PASS:
            if not self.assertions or not all(item.passed for item in self.assertions):
                raise ValueError("pass requires at least one assertion and all true")
        elif self.verdict is CaseVerdict.FAIL:
            if not self.assertions or all(item.passed for item in self.assertions):
                raise ValueError("fail requires at least one false assertion")
        elif self.assertions:
            raise ValueError("unscored cases cannot contain scored assertions")

        if self.verdict is CaseVerdict.UNSCORED:
            if not self.unscored_reason:
                raise ValueError("unscored case requires a reason")
            if self.minimal_actions is not None:
                raise ValueError("unscored case cannot have minimal actions")
        elif self.unscored_reason is not None:
            raise ValueError("scored case cannot have an unscored reason")
        if self.minimal_actions is not None and self.verdict is not CaseVerdict.FAIL:
            raise ValueError("minimal actions are only valid for failed cases")
        return self


class MetricReview(ContractModel):
    policy_text_sha256: str = Field(pattern=_HASH_PATTERN)
    review_fingerprint: str = Field(pattern=_HASH_PATTERN)
    status: ReviewStatus
    clauses: tuple[PolicyClause, ...] = Field(default=(), max_length=16)
    goals: tuple[PolicyGoal, ...] = Field(default=(), max_length=16)
    rules: MetricRules | PolicyConditions | None
    assumptions: tuple[str, ...] = Field(default=(), max_length=16)
    limitations: tuple[str, ...] = Field(default=(), max_length=16)

    @field_validator("assumptions", "limitations")
    @classmethod
    def notes_are_english(cls, values: tuple[str, ...]) -> tuple[str, ...]:
        return tuple(_english(value) for value in values)

    @model_validator(mode="after")
    def interpretation_is_consistent(self) -> MetricReview:
        clause_ids = [clause.id for clause in self.clauses]
        goal_ids = [goal.id for goal in self.goals]
        if len(clause_ids) != len(set(clause_ids)):
            raise ValueError("review clause IDs must be unique")
        if len(goal_ids) != len(set(goal_ids)):
            raise ValueError("review goal IDs must be unique")
        clause_id_set = set(clause_ids)
        if any(not set(goal.clause_ids) <= clause_id_set for goal in self.goals):
            raise ValueError("goal references unknown policy clause")
        if isinstance(self.rules, PolicyConditions):
            ids = [c.id for c in self.rules.conditions]
            if len(ids) != len(set(ids)) or any(
                c.clause_id not in clause_id_set for c in self.rules.conditions
            ):
                raise ValueError(
                    "condition identifiers or clause references are invalid"
                )
        if self.status is ReviewStatus.READY:
            if self.rules is None or not self.clauses or not self.goals:
                raise ValueError("ready review requires rules, clauses, and goals")
        elif self.rules is not None:
            raise ValueError("clarification review cannot contain executable rules")
        return self


class MetricRunResult(ContractModel):
    schema_version: Literal["2.0"] = "2.0"
    run_id: str = Field(pattern=_ID_PATTERN)
    policy_version: Literal["1"] = "1"
    policy_text_sha256: str = Field(pattern=_HASH_PATTERN)
    review_fingerprint: str = Field(pattern=_HASH_PATTERN)
    generation_method: Literal[
        "rule_templates", "authored_fixture", "policy_conditions", "policy_scenarios"
    ] = "rule_templates"
    status: MetricRunStatus
    review: MetricReview
    suite_sha256: str = Field(pattern=_HASH_PATTERN)
    cases: tuple[MetricCaseResult, ...] = Field(default=(), max_length=32)
    passed: int = Field(strict=True, ge=0)
    failed: int = Field(strict=True, ge=0)
    unscored: int = Field(strict=True, ge=0)
    pass_rate: float | None
    limitations: tuple[str, ...] = Field(default=(), max_length=16)

    @field_validator("limitations")
    @classmethod
    def limitations_are_english(cls, values: tuple[str, ...]) -> tuple[str, ...]:
        return tuple(_english(value) for value in values)

    @model_validator(mode="after")
    def counts_identity_and_references_are_consistent(self) -> MetricRunResult:
        if self.policy_text_sha256 != self.review.policy_text_sha256:
            raise ValueError("run policy hash does not match review")
        if self.review_fingerprint != self.review.review_fingerprint:
            raise ValueError("run review fingerprint does not match review")
        case_ids = [case.case_id for case in self.cases]
        if len(case_ids) != len(set(case_ids)):
            raise ValueError("Metric case IDs must be unique")
        actual = {
            CaseVerdict.PASS: sum(
                case.verdict is CaseVerdict.PASS for case in self.cases
            ),
            CaseVerdict.FAIL: sum(
                case.verdict is CaseVerdict.FAIL for case in self.cases
            ),
            CaseVerdict.UNSCORED: sum(
                case.verdict is CaseVerdict.UNSCORED for case in self.cases
            ),
        }
        if (self.passed, self.failed, self.unscored) != (
            actual[CaseVerdict.PASS],
            actual[CaseVerdict.FAIL],
            actual[CaseVerdict.UNSCORED],
        ):
            raise ValueError("Metric result counts do not match case verdicts")
        denominator = self.passed + self.failed
        expected_rate = None if denominator == 0 else self.passed / denominator
        if self.pass_rate != expected_rate:
            raise ValueError("pass_rate does not match scored-case denominator")
        reviewed_goal_ids = {goal.id for goal in self.review.goals}
        for case in self.cases:
            for assertion in case.assertions:
                if assertion.requirement_id not in reviewed_goal_ids:
                    raise ValueError("assertion references unknown reviewed goal")
        if self.generation_method == "policy_conditions":
            if (
                not isinstance(self.review.rules, PolicyConditions)
                or self.status is not MetricRunStatus.PARTIAL
            ):
                raise ValueError("condition probes require explicit partial coverage")
            condition_ids = {c.id for c in self.review.rules.conditions}
            for case in self.cases:
                for action in case.actions:
                    if (
                        isinstance(action, EvaluateConditionAction)
                        and action.condition_id not in condition_ids
                    ):
                        raise ValueError("action references unknown condition")
        elif isinstance(self.review.rules, PolicyConditions):
            raise ValueError("condition evidence requires its generation method")
        if self.generation_method == "policy_scenarios":
            if (
                self.status is not MetricRunStatus.PARTIAL
                or self.review.status is not ReviewStatus.NEEDS_CLARIFICATION
                or self.review.rules is not None
                or self.review.clauses
                or self.review.goals
                or not self.cases
                or not self.limitations
                or any(
                    c.verdict is not CaseVerdict.UNSCORED
                    or c.trace
                    or any(
                        not isinstance(a, UnsupportedAction)
                        or a.action != "review_scenario"
                        for a in c.actions
                    )
                    for c in self.cases
                )
            ):
                raise ValueError(
                    "planned scenarios require unscored, unexecuted, explicitly limited evidence"
                )
        elif self.status in {MetricRunStatus.COMPLETED, MetricRunStatus.PARTIAL}:
            if self.review.status is not ReviewStatus.READY:
                raise ValueError("executed run requires ready review")
            if self.status is MetricRunStatus.PARTIAL and (
                not self.cases or not self.limitations
            ):
                raise ValueError("partial run requires cases and limitations")
        else:
            if self.review.status is not ReviewStatus.NEEDS_CLARIFICATION:
                raise ValueError("clarification run requires clarification review")
            if self.cases:
                raise ValueError("no cases may run before clarification")
        return self


__all__ = [
    "ApproveAction",
    "AssertionResult",
    "CancelAction",
    "CaseCategory",
    "CaseVerdict",
    "ClaimRecord",
    "ClaimStatus",
    "ConditionTraceStep",
    "EvaluateConditionAction",
    "MetricAction",
    "MetricCaseResult",
    "MetricReview",
    "MetricRules",
    "MetricRunResult",
    "MetricRunStatus",
    "MetricState",
    "NumericCondition",
    "ParticipantTotals",
    "PayAction",
    "PolicyClause",
    "PolicyConditions",
    "PolicyGoal",
    "ReviewStatus",
    "SubmitAction",
    "TraceStep",
    "UnsupportedAction",
]
