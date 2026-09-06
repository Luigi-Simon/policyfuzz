"""Private provider shapes: semantic proposals may select source handles only."""

from typing import Annotated, Literal

from pydantic import Field, model_validator

from app.domain.models import (
    Effect,
    EffectDimensions,
    Identifier,
    NonEmptyText,
    OverrideRef,
    Percentage,
    Predicate,
    Sha256,
    StrictModel,
)


class ModelRuleDraft(StrictModel):
    """No source text, hash, offset, or session provenance is provider-authored."""

    rule_handle: Identifier
    citation_handle: Identifier
    description: NonEmptyText
    when: tuple[Predicate, ...]
    effects: Annotated[tuple[Effect, ...], Field(min_length=1)]
    overrides: tuple[OverrideRef, ...] = ()
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
    when_hint: tuple[Predicate, ...] | None = None
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


__all__ = ["ModelPolicyExtraction", "ModelRuleDraft", "ModelUnsupportedClause"]
