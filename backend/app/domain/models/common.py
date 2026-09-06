"""Shared immutable values. These models do not execute or hash policy data."""

from datetime import datetime
from enum import StrEnum
from typing import Annotated, Literal

from pydantic import (
    AwareDatetime,
    BaseModel,
    BeforeValidator,
    ConfigDict,
    Field,
    ValidationInfo,
    model_validator,
)


class StrictModel(BaseModel):
    model_config = ConfigDict(
        extra="forbid", frozen=True, strict=True, revalidate_instances="always"
    )
    schema_version: Literal["1.0"] = "1.0"


Identifier = Annotated[str, Field(min_length=1, max_length=200)]
NonEmptyText = Annotated[str, Field(min_length=1)]
Sha256 = Annotated[str, Field(pattern=r"^[0-9a-f]{64}$")]
NonNegativeInt = Annotated[int, Field(ge=0)]
MoneyMinor = Annotated[int, Field(ge=0, le=10_000_000)]
Percentage = Annotated[int, Field(ge=0, le=100)]


def _timestamp(value: object) -> object:
    if isinstance(value, str):
        return datetime.fromisoformat(value)
    return value


Timestamp = Annotated[AwareDatetime, BeforeValidator(_timestamp)]


def _freeze_set(value: object, info: ValidationInfo) -> object:
    if (
        isinstance(value, set) or (info.mode == "json" and isinstance(value, list))
    ) and all(isinstance(item, str) for item in value):
        return frozenset(value)
    return value


EmployeeRole = Literal["employee", "manager", "director", "executive"]
ExpenseCategory = Literal["meal", "hotel", "transport", "airfare", "incidental"]
DestinationType = Literal["domestic", "international"]
ApprovalRole = Literal["manager", "director", "finance"]
ApprovalRoles = Annotated[frozenset[ApprovalRole], BeforeValidator(_freeze_set)]
FactField = Literal[
    "employee_role",
    "expense_category",
    "amount_minor",
    "destination_type",
    "booking_days_before",
    "receipt_present",
    "approval_roles_present",
    "prior_same_day_category_spend_minor",
]
PredicateField = FactField | Literal["daily_category_total_minor"]
PredicateOperator = Literal[
    "eq", "neq", "in", "not_in", "lt", "lte", "gt", "gte", "contains"
]
EffectDimensionValue = Literal[
    "eligibility",
    "receipt_requirement",
    "approval_requirement",
    "claim_cap_minor",
    "daily_category_cap_minor",
]
EffectDimensions = Annotated[
    frozenset[EffectDimensionValue], BeforeValidator(_freeze_set)
]
EligibilityValue = Literal["allow", "deny"]
ReceiptRequirementValue = Literal["required", "not_required"]
ApprovalRequirementValue = Literal["none", "manager", "director", "finance"]
Severity = Literal["low", "medium", "high", "critical"]
RunMode = Literal["live", "cached"]


class EffectDimension(StrEnum):
    ELIGIBILITY = "eligibility"
    RECEIPT_REQUIREMENT = "receipt_requirement"
    APPROVAL_REQUIREMENT = "approval_requirement"
    CLAIM_CAP_MINOR = "claim_cap_minor"
    DAILY_CATEGORY_CAP_MINOR = "daily_category_cap_minor"


class EffectStatus(StrEnum):
    VALUE = "VALUE"
    GAP = "GAP"
    NOT_APPLICABLE = "NOT_APPLICABLE"
    CONFLICT = "CONFLICT"
    INCONCLUSIVE = "INCONCLUSIVE"
    ERROR = "ERROR"


class AssertionStatus(StrEnum):
    PASS = "PASS"
    FAIL = "FAIL"
    INCONCLUSIVE = "INCONCLUSIVE"
    ERROR = "ERROR"


class ComplianceStatus(StrEnum):
    COMPLIANT = "COMPLIANT"
    NONCOMPLIANT = "NONCOMPLIANT"
    NOT_APPLICABLE = "NOT_APPLICABLE"
    INCONCLUSIVE = "INCONCLUSIVE"
    ERROR = "ERROR"


EffectStatusValue = Literal[
    "VALUE", "GAP", "NOT_APPLICABLE", "CONFLICT", "INCONCLUSIVE", "ERROR"
]
AssertionStatusValue = Literal["PASS", "FAIL", "INCONCLUSIVE", "ERROR"]
ComplianceStatusValue = Literal[
    "COMPLIANT", "NONCOMPLIANT", "NOT_APPLICABLE", "INCONCLUSIVE", "ERROR"
]
ArtifactType = Literal[
    "policy_document",
    "policy_ir",
    "policy_contract",
    "scenario_suite",
    "evaluation_report",
    "finding_report",
    "revision_proposal",
    "regression_report",
    "patch_acceptance_report",
    "comparison_bundle",
    "metrics_report",
    "benchmark_manifest",
    "benchmark_score",
    "coverage_snapshot",
    "run_manifest",
]


class SourceSpan(StrictModel):
    page: Annotated[int, Field(ge=1)]
    start: NonNegativeInt
    end: NonNegativeInt
    quote: NonEmptyText
    quote_sha256: Sha256
    section: NonEmptyText | None = None

    @model_validator(mode="after")
    def ordered_range(self) -> "SourceSpan":
        if self.end <= self.start:
            raise ValueError("source span must have end > start")
        return self


class ArtifactRef(StrictModel):
    artifact_type: ArtifactType
    artifact_sha256: Sha256
    semantic_sha256: Sha256


class InputHashes(StrictModel):
    policy_sha256: Sha256
    contract_sha256: Sha256
    suite_sha256: Sha256
    engine_sha256: Sha256
    run_manifest_sha256: Sha256


class PublicError(StrictModel):
    code: Literal[
        "INVALID_INPUT",
        "INVALID_STATE",
        "INVALID_POLICY",
        "INVALID_CITATION",
        "MALFORMED_MODEL_OUTPUT",
        "PROVIDER_UNAVAILABLE",
        "COVERAGE_LIMIT_EXCEEDED",
        "HASH_MISMATCH",
        "REVISION_INVALID",
        "PROSE_COMPILE_MISMATCH",
        "RUN_NOT_FOUND",
        "INTERNAL_ERROR",
    ]
    message: NonEmptyText
    error_id: Identifier | None = None
    retryable: bool = False
