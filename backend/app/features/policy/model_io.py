"""Private provider-facing policy output shapes normalized into frozen contracts."""

from app.domain.models import (
    Identifier,
    PolicyExtraction,
    RuleDraft,
)


class ModelRuleDraft(RuleDraft):
    """A rule proposal with an optional provider-local reference handle."""

    rule_handle: Identifier | None = None


class ModelPolicyExtraction(PolicyExtraction):
    """Private extraction response retaining local rule handles during parsing."""

    rules: tuple[ModelRuleDraft, ...]


__all__ = ["ModelPolicyExtraction", "ModelRuleDraft"]
