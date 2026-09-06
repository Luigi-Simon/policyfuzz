"""Bounded structured changes and frozen-input comparison report contracts."""

from typing import Annotated, Literal

from pydantic import Field, model_validator

from .common import (
    AssertionStatusValue,
    EffectDimensionValue,
    Identifier,
    InputHashes,
    NonEmptyText,
    NonNegativeInt,
    PublicError,
    Severity,
    Sha256,
    StrictModel,
    Timestamp,
)
from .evaluation import (
    EffectStateCounts,
    EvaluationReport,
    FindingReport,
    MetricsReport,
)
from .policy import Effect, OverrideRef, PolicyContract, PolicyIR, Predicate
from .scenario import ScenarioSuite


class FindingDecision(StrictModel):
    finding_id: Identifier
    decision: Literal["accept", "reject"]
    reviewer_severity: Severity | None = None


class RevisionRuleDraft(StrictModel):
    """Proposed rule content. Confirmation provenance is assigned only on application."""

    description: NonEmptyText
    when: Annotated[tuple[Predicate, ...], Field(min_length=1)]
    effects: Annotated[tuple[Effect, ...], Field(min_length=1)]
    overrides: tuple[OverrideRef, ...] = ()

    @model_validator(mode="after")
    def supported_rule(self) -> "RevisionRuleDraft":
        if any(item.field == "daily_category_total_minor" for item in self.when):
            raise ValueError("derived daily totals cannot be executable conditions")
        dimensions = [item.dimension for item in self.effects]
        if len(set(dimensions)) != len(dimensions):
            raise ValueError("a rule supplies at most one value per dimension")
        if any(item.dimension not in dimensions for item in self.overrides):
            raise ValueError("override dimension must be supplied by the revised rule")
        return self


class AddRuleOperation(StrictModel):
    kind: Literal["add_rule"] = "add_rule"
    rule_id: Identifier
    rule: RevisionRuleDraft
    finding_ids: Annotated[tuple[Identifier, ...], Field(min_length=1)]


class ReplaceRuleOperation(StrictModel):
    kind: Literal["replace_rule"] = "replace_rule"
    rule_id: Identifier
    expected_revision: NonNegativeInt
    rule: RevisionRuleDraft
    finding_ids: Annotated[tuple[Identifier, ...], Field(min_length=1)]


class AddOverrideOperation(StrictModel):
    kind: Literal["add_override"] = "add_override"
    rule_id: Identifier
    dimension: EffectDimensionValue
    target_rule_id: Identifier
    finding_ids: Annotated[tuple[Identifier, ...], Field(min_length=1)]

    @model_validator(mode="after")
    def no_self_override(self) -> "AddOverrideOperation":
        if self.rule_id == self.target_rule_id:
            raise ValueError("a rule cannot override itself")
        return self


RevisionOperation = Annotated[
    AddRuleOperation | ReplaceRuleOperation | AddOverrideOperation,
    Field(discriminator="kind"),
]


class RevisionProposal(StrictModel):
    proposal_id: Identifier
    document_sha256: Sha256
    rule_set_sha256: Sha256
    policy_contract_sha256: Sha256
    suite_sha256: Sha256
    accepted_finding_ids: Annotated[tuple[Identifier, ...], Field(min_length=1)]
    operations: Annotated[
        tuple[RevisionOperation, ...], Field(min_length=1, max_length=3)
    ]
    draft_policy_wording: NonEmptyText

    @model_validator(mode="after")
    def accepted_targets_only(self) -> "RevisionProposal":
        accepted = set(self.accepted_finding_ids)
        if len(accepted) != len(self.accepted_finding_ids):
            raise ValueError("accepted finding IDs must be unique")
        if any(
            not set(operation.finding_ids) <= accepted for operation in self.operations
        ):
            raise ValueError("revision operations may target only accepted findings")
        return self


class AssertionTransition(StrictModel):
    scenario_id: Identifier
    assertion_id: Identifier
    before: AssertionStatusValue
    after: AssertionStatusValue
    protected: bool
    targeted: bool


class AssertionTransitionCounts(StrictModel):
    pass_to_pass: NonNegativeInt = 0
    fail_to_pass: NonNegativeInt = 0
    pass_to_fail: NonNegativeInt = 0
    fail_to_fail: NonNegativeInt = 0
    inconclusive_or_error: NonNegativeInt = 0


class RegressionReport(StrictModel):
    report_id: Identifier
    baseline_inputs: InputHashes
    revised_inputs: InputHashes
    baseline_effect_states: EffectStateCounts
    revised_effect_states: EffectStateCounts
    assertion_transition_counts: AssertionTransitionCounts
    assertion_transitions: tuple[AssertionTransition, ...]

    @model_validator(mode="after")
    def frozen_comparison_inputs(self) -> "RegressionReport":
        before, after = self.baseline_inputs, self.revised_inputs
        if (
            before.suite_sha256 != after.suite_sha256
            or before.engine_sha256 != after.engine_sha256
        ):
            raise ValueError(
                "regression comparison requires identical suite and engine hashes"
            )
        if (
            before.contract_sha256 != after.contract_sha256
            or before.run_manifest_sha256 != after.run_manifest_sha256
        ):
            raise ValueError(
                "regression comparison requires frozen contract and run manifest"
            )
        identities = {
            (item.scenario_id, item.assertion_id) for item in self.assertion_transitions
        }
        if len(identities) != len(self.assertion_transitions):
            raise ValueError("each frozen assertion has exactly one transition row")
        return self


class PatchAcceptanceCounts(StrictModel):
    target_findings: NonNegativeInt = 0
    fixed_target_findings: NonNegativeInt = 0
    new_failures_outside_targets: NonNegativeInt = 0
    protected_regressions: NonNegativeInt = 0
    baseline_gap_conflict_inconclusive_or_error: NonNegativeInt = 0
    revised_gap_conflict_inconclusive_or_error: NonNegativeInt = 0
    unrelated_rule_changes: NonNegativeInt = 0
    holdout_regressions: NonNegativeInt = 0


class PatchAcceptanceReport(StrictModel):
    baseline_inputs: InputHashes
    revised_inputs: InputHashes
    suite_hash_matches: bool
    all_target_findings_fixed: bool
    zero_new_failures_outside_targets: bool
    zero_protected_regressions: bool
    no_increase_in_gap_conflict_inconclusive_or_error: bool
    unrelated_rules_unchanged: bool
    holdout_not_worse: bool
    patch_accepted: bool
    counts: PatchAcceptanceCounts = Field(default_factory=PatchAcceptanceCounts)

    @model_validator(mode="after")
    def acceptance_requires_every_check(self) -> "PatchAcceptanceReport":
        checks = (
            self.suite_hash_matches,
            self.all_target_findings_fixed,
            self.zero_new_failures_outside_targets,
            self.zero_protected_regressions,
            self.no_increase_in_gap_conflict_inconclusive_or_error,
            self.unrelated_rules_unchanged,
            self.holdout_not_worse,
        )
        if self.patch_accepted != all(checks):
            raise ValueError(
                "patch_accepted must equal the conjunction of all seven checks"
            )
        return self


class ProposeRevisionRequest(StrictModel):
    policy: PolicyIR
    contract: PolicyContract
    suite: ScenarioSuite
    findings: FindingReport
    decisions: Annotated[tuple[FindingDecision, ...], Field(min_length=1)]
    document_sha256: Sha256
    rule_set_sha256: Sha256
    policy_contract_sha256: Sha256
    suite_sha256: Sha256


class ApplyRevisionRequest(StrictModel):
    policy: PolicyIR
    contract: PolicyContract
    suite: ScenarioSuite
    proposal: RevisionProposal
    confirmed_at: Timestamp


class PatchApplicationResult(StrictModel):
    proposal_id: Identifier
    applied: bool
    revised_policy: PolicyIR | None = None
    changed_rule_ids: tuple[Identifier, ...] = ()
    error: PublicError | None = None

    @model_validator(mode="after")
    def application_outcome(self) -> "PatchApplicationResult":
        if self.applied:
            if (
                self.revised_policy is None
                or self.revised_policy.kind != "structured_revision"
                or self.error is not None
            ):
                raise ValueError(
                    "successful application requires a structured revision and no error"
                )
        elif (
            self.revised_policy is not None
            or self.changed_rule_ids
            or self.error is None
        ):
            raise ValueError(
                "failed application requires an error and no changed policy"
            )
        return self


class CompareRevisionRequest(StrictModel):
    baseline_policy: PolicyIR
    revised_policy: PolicyIR
    contract: PolicyContract
    suite: ScenarioSuite
    proposal: RevisionProposal
    baseline_evaluation: EvaluationReport
    revised_evaluation: EvaluationReport
    baseline_findings: FindingReport
    revised_findings: FindingReport


class ComparisonBundle(StrictModel):
    baseline_inputs: InputHashes
    revised_inputs: InputHashes
    regression: RegressionReport
    acceptance: PatchAcceptanceReport
    baseline_metrics: MetricsReport
    revised_metrics: MetricsReport
