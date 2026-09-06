"""Private provider shapes: semantic proposals may select source handles only."""

from typing import Annotated, Literal

from pydantic import Field, model_validator

from app.domain.models import (
    ApprovalRequirementValue,
    EffectDimension,
    EffectDimensions,
    EligibilityValue,
    Identifier,
    NonEmptyText,
    NonNegativeInt,
    OverrideRef,
    Percentage,
    Predicate,
    ReceiptRequirementValue,
    Sha256,
    StrictModel,
)


class ModelEligibilityEffect(StrictModel):
    dimension: Literal[EffectDimension.ELIGIBILITY]
    value: EligibilityValue


class ModelReceiptEffect(StrictModel):
    dimension: Literal[EffectDimension.RECEIPT_REQUIREMENT]
    value: ReceiptRequirementValue


class ModelApprovalEffect(StrictModel):
    dimension: Literal[EffectDimension.APPROVAL_REQUIREMENT]
    value: ApprovalRequirementValue


class ModelClaimCapEffect(StrictModel):
    dimension: Literal[EffectDimension.CLAIM_CAP_MINOR]
    value: NonNegativeInt


class ModelDailyCategoryCapEffect(StrictModel):
    dimension: Literal[EffectDimension.DAILY_CATEGORY_CAP_MINOR]
    value: NonNegativeInt


ModelEffect = Annotated[
    ModelEligibilityEffect
    | ModelReceiptEffect
    | ModelApprovalEffect
    | ModelClaimCapEffect
    | ModelDailyCategoryCapEffect,
    Field(discriminator="dimension"),
]


class ModelRuleDraft(StrictModel):
    """No source text, hash, offset, or session provenance is provider-authored."""

    rule_handle: Identifier
    citation_handle: Identifier
    description: NonEmptyText
    when: tuple[Predicate, ...]
    effects: Annotated[tuple[ModelEffect, ...], Field(min_length=1)]
    overrides: tuple[OverrideRef, ...] = Field(
        ...,
        description=(
            "Explicit dimension-specific edges to local rule_handle targets. "
            "Stated exceptions override the expressly marked default only; "
            "competing specific rules require explicit source precedence. "
            "Emit [] only when no source-supported override applies."
        ),
    )
    confidence_percent: Percentage | None = None


class ModelUnsupportedClause(StrictModel):
    clause_id: Identifier
    citation_handle: Identifier
    reason_code: Literal[
        "unsupported_vocabulary",
        "unsupported_logic",
        "ambiguous_language",
        "invalid_citation",
        "unsupported_aggregation",
        "unsupported_currency",
    ]
    affected_dimensions: Annotated[EffectDimensions, Field(min_length=1)]
    when_hint: tuple[Predicate, ...] | None = Field(
        ...,
        description=(
            "Explicit supported predicates for this clause's stated scope. "
            "Use null only when no stated scope is expressible with supported "
            "fields; do not use null when representable source scope is stated."
        ),
    )
    review_status: Literal["provisional"] = "provisional"


class ModelPolicyExtraction(StrictModel):
    """Private wire format, deliberately independent of public span contracts."""

    document_sha256: Sha256
    rules: tuple[ModelRuleDraft, ...]
    unsupported_clauses: tuple[ModelUnsupportedClause, ...] = ()

    @model_validator(mode="after")
    def unique_rule_handles(self) -> "ModelPolicyExtraction":
        handles = [rule.rule_handle for rule in self.rules]
        if len(handles) != len(set(handles)):
            raise ValueError("rule handles must be unique")
        return self


__all__ = [
    "ModelEffect",
    "ModelPolicyExtraction",
    "ModelRuleDraft",
    "ModelUnsupportedClause",
]
