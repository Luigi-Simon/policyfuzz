"""Run storage, commands and the deliberately restricted public RunView."""

from typing import Annotated, Literal

from pydantic import Field, model_validator

from .common import (
    ArtifactRef,
    ArtifactType,
    EffectDimensions,
    EffectDimensionValue,
    Identifier,
    NonEmptyText,
    NonNegativeInt,
    Percentage,
    PublicError,
    RunMode,
    Severity,
    Sha256,
    SourceSpan,
    StrictModel,
    Timestamp,
)
from .evaluation import (
    AssertionCounts,
    BenchmarkManifest,
    BenchmarkScore,
    ComplianceResult,
    DimensionResult,
    EffectStateCounts,
    EvaluationReport,
    FindingReport,
    FindingReviewStatus,
    FindingType,
    MetricsReport,
    PredicateResult,
)
from .llm import GenerationConfig
from .policy import (
    AssertionContent,
    Effect,
    OverrideRef,
    PolicyContract,
    PolicyDocument,
    PolicyIR,
    Predicate,
    TextRuleProvenance,
    UnsupportedClause,
)
from .revision import (
    ComparisonBundle,
    FindingDecision,
    PatchAcceptanceReport,
    RegressionReport,
    RevisionOperation,
    RevisionProposal,
)
from .scenario import CoverageSnapshot, ScenarioSuite

RunStage = Literal[
    "queued",
    "ingesting",
    "extracting",
    "awaiting_contract",
    "generating_initial_tests",
    "provisional_execution",
    "targeting_coverage",
    "freezing_suite",
    "baseline_execution",
    "analyzing",
    "awaiting_finding_review",
    "drafting_revision",
    "awaiting_revision_confirmation",
    "applying_revision",
    "retesting",
    "complete",
    "completed_no_findings",
    "completed_no_revision",
    "contract_rejected",
    "revision_rejected",
    "coverage_limit_exceeded",
    "failed",
]
TerminalStatus = Literal[
    "complete",
    "completed_no_findings",
    "completed_no_revision",
    "contract_rejected",
    "revision_rejected",
    "coverage_limit_exceeded",
    "failed",
]
RunAction = Literal[
    "confirm_contract",
    "reject_contract",
    "select_findings",
    "confirm_revision",
    "reject_revision",
    "delete_run",
]


class PromptHash(StrictModel):
    prompt_name: Identifier
    prompt_sha256: Sha256


class RunManifest(StrictModel):
    manifest_id: Identifier
    run_id: Identifier
    engine_version: NonEmptyText
    engine_sha256: Sha256
    prompt_hashes: tuple[PromptHash, ...]
    provider: Identifier
    model_identifier: Identifier
    generation_config: GenerationConfig
    random_seed: NonNegativeInt
    started_at: Timestamp
    mode: RunMode


ArtifactPayload = (
    PolicyDocument
    | PolicyIR
    | PolicyContract
    | ScenarioSuite
    | EvaluationReport
    | FindingReport
    | RevisionProposal
    | RegressionReport
    | PatchAcceptanceReport
    | ComparisonBundle
    | MetricsReport
    | BenchmarkManifest
    | BenchmarkScore
    | CoverageSnapshot
    | RunManifest
)
_PAYLOAD_TYPES = {
    "policy_document": PolicyDocument,
    "policy_ir": PolicyIR,
    "policy_contract": PolicyContract,
    "scenario_suite": ScenarioSuite,
    "evaluation_report": EvaluationReport,
    "finding_report": FindingReport,
    "revision_proposal": RevisionProposal,
    "regression_report": RegressionReport,
    "patch_acceptance_report": PatchAcceptanceReport,
    "comparison_bundle": ComparisonBundle,
    "metrics_report": MetricsReport,
    "benchmark_manifest": BenchmarkManifest,
    "benchmark_score": BenchmarkScore,
    "coverage_snapshot": CoverageSnapshot,
    "run_manifest": RunManifest,
}


class ArtifactEnvelope(StrictModel):
    artifact_type: ArtifactType
    artifact_sha256: Sha256
    semantic_sha256: Sha256
    parent_hashes: tuple[Sha256, ...]
    run_manifest_id: Identifier
    payload: ArtifactPayload

    @model_validator(mode="after")
    def payload_matches_artifact_type(self) -> "ArtifactEnvelope":
        if not isinstance(self.payload, _PAYLOAD_TYPES[self.artifact_type]):
            raise ValueError("payload must match artifact_type")  # noqa: TRY004 - Pydantic validation error
        return self


class RunEvent(StrictModel):
    timestamp: Timestamp
    stage: RunStage
    action_summary: NonEmptyText
    artifact: ArtifactRef | None = None
    error_id: Identifier | None = None


class ArtifactSummary(StrictModel):
    artifact: ArtifactRef
    title: NonEmptyText
    item_count: NonNegativeInt | None = None


class RuleSummary(StrictModel):
    """Review of a server-held baseline rule with source citations."""

    rule_id: Identifier
    revision: NonNegativeInt
    description: NonEmptyText
    when: tuple[Predicate, ...]
    effects: Annotated[tuple[Effect, ...], Field(min_length=1)]
    overrides: tuple[OverrideRef, ...] = ()
    citations: Annotated[tuple[TextRuleProvenance, ...], Field(min_length=1)]
    confidence_percent: Percentage | None = None


class InvariantSummary(StrictModel):
    """Session intent for review/editing; no gold or mechanical oracle metadata."""

    invariant_id: Identifier
    description: NonEmptyText
    when: tuple[Predicate, ...]
    assertion: AssertionContent
    severity: Severity


class FindingSummary(StrictModel):
    finding_id: Identifier
    finding_type: FindingType
    dimension: EffectDimensionValue
    summary: NonEmptyText
    severity: Severity | None = None
    review_status: FindingReviewStatus
    witness_count: NonNegativeInt


class CoverageCounters(StrictModel):
    total_rules: NonNegativeInt = 0
    covered_rules: NonNegativeInt = 0
    total_invariants: NonNegativeInt = 0
    covered_invariants: NonNegativeInt = 0
    total_predicate_branches: NonNegativeInt = 0
    covered_predicate_branches: NonNegativeInt = 0
    scenario_count: Annotated[int, Field(ge=0, le=15)] = 0


class PublicMetrics(StrictModel):
    scenario_count: NonNegativeInt
    effect_states: EffectStateCounts
    assertions: AssertionCounts
    unique_finding_count: NonNegativeInt
    assertion_pass_percent: Percentage | None = None


class PublicComparisonMetrics(StrictModel):
    baseline: PublicMetrics
    revised: PublicMetrics
    patch_accepted: bool
    protected_regressions: NonNegativeInt
    new_failures_outside_targets: NonNegativeInt


class ContractConfirmation(StrictModel):
    kind: Literal["contract"] = "contract"
    baseline_policy_id: Identifier
    baseline_policy_sha256: Sha256 = Field(
        description="Artifact SHA256 of the exact server-held baseline PolicyIR."
    )
    document_sha256: Sha256
    rules: Annotated[tuple[RuleSummary, ...], Field(max_length=12)]
    invariants: Annotated[
        tuple[InvariantSummary, ...], Field(min_length=3, max_length=5)
    ]
    required_dimensions: Annotated[EffectDimensions, Field(min_length=1)]


class FindingsConfirmation(StrictModel):
    kind: Literal["findings"] = "findings"
    finding_ids: tuple[Identifier, ...]


class RevisionOperationSummary(StrictModel):
    """Authoritative typed operation with the affected baseline rule for comparison."""

    operation: RevisionOperation
    before: RuleSummary | None = None

    @model_validator(mode="after")
    def matching_before_rule(self) -> "RevisionOperationSummary":
        if self.operation.kind == "add_rule":
            if self.before is not None:
                raise ValueError("an added rule has no baseline rule")
        elif self.before is None or self.before.rule_id != self.operation.rule_id:
            raise ValueError("a modified rule requires its matching baseline summary")
        elif (
            self.operation.kind == "replace_rule"
            and self.before.revision != self.operation.expected_revision
        ):
            raise ValueError("replacement must match the displayed baseline revision")
        return self


class RevisionConfirmation(StrictModel):
    kind: Literal["revision"] = "revision"
    proposal_id: Identifier
    operations: Annotated[
        tuple[RevisionOperationSummary, ...], Field(min_length=1, max_length=3)
    ]
    draft_policy_wording: NonEmptyText


PendingConfirmation = Annotated[
    ContractConfirmation | FindingsConfirmation | RevisionConfirmation,
    Field(discriminator="kind"),
]


class UnsupportedClauseEvidence(UnsupportedClause):
    """Visible-policy evidence only; private clauses contribute to holdout counts."""

    partition: Literal["visible"] = "visible"
    disposition: Literal["pending_review", "retained_inconclusive", "excluded"]


class RejectionEvidence(StrictModel):
    """Visible rejection; source_spans is empty when no policy source exists."""

    partition: Literal["visible"] = "visible"
    item_kind: Literal["rule", "scenario"]
    item_id: Identifier
    source_spans: tuple[SourceSpan, ...]
    reason_code: Literal[
        "invalid_citation",
        "unsupported_vocabulary",
        "unsupported_logic",
        "invalid_rule",
        "dangling_override",
        "override_cycle",
        "invalid_facts",
        "invalid_assertion",
        "duplicate",
        "budget_exceeded",
        "incompatible_assertions",
    ]
    disposition: Literal["excluded", "merged_duplicate", "rule_set_rejected"]


class VisibleTraceSummary(StrictModel):
    """Visible execution evidence, never facts, assertion answers, or holdout rows."""

    partition: Literal["visible"] = "visible"
    scenario_id: Identifier
    phase: Literal["baseline", "revised"]
    trace_sha256: Sha256
    fired_rule_ids: tuple[Identifier, ...]
    predicate_results: tuple[PredicateResult, ...]
    resolved_effects: tuple[DimensionResult, ...]
    compliance_values: tuple[ComplianceResult, ...]
    source_citations: tuple[SourceSpan, ...]


class HoldoutEvidenceSummary(StrictModel):
    """The only holdout evidence shape: aggregate counts with no case identifiers.

    Projectors must route all private clauses, rejections and traces here, never
    into the visible evidence collections or free-text summaries/events.
    """

    partition: Literal["holdout"] = "holdout"
    scenario_count: Annotated[int, Field(ge=0, le=15)] = 0
    unsupported_clause_count: NonNegativeInt = 0
    rejected_rule_count: NonNegativeInt = 0
    rejected_scenario_count: NonNegativeInt = 0
    baseline_effect_states: EffectStateCounts = Field(default_factory=EffectStateCounts)
    revised_effect_states: EffectStateCounts | None = None


class RunView(StrictModel):
    run_id: Identifier
    stage: RunStage
    allowed_actions: tuple[RunAction, ...] = ()
    mode: RunMode
    events: tuple[RunEvent, ...] = ()
    artifacts: tuple[ArtifactSummary, ...] = ()
    pending_confirmation: PendingConfirmation | None = None
    coverage: CoverageCounters = Field(default_factory=CoverageCounters)
    findings: tuple[FindingSummary, ...] = ()
    unsupported_clauses: tuple[UnsupportedClauseEvidence, ...] = ()
    rejections: tuple[RejectionEvidence, ...] = ()
    traces: tuple[VisibleTraceSummary, ...] = ()
    holdout_evidence: HoldoutEvidenceSummary | None = None
    baseline_metrics: PublicMetrics | None = None
    comparison_metrics: PublicComparisonMetrics | None = None
    terminal_status: TerminalStatus | None = None
    error: PublicError | None = None
    decision_at: Timestamp | None = None


class RunRecord(StrictModel):
    run_id: Identifier
    stage: RunStage
    manifest: RunManifest
    created_at: Timestamp
    expires_at: Timestamp
    artifacts: tuple[ArtifactEnvelope, ...] = ()
    events: tuple[RunEvent, ...] = ()
    finding_decisions: tuple[FindingDecision, ...] = ()
    decision_at: Timestamp | None = None
    error: PublicError | None = None

    @model_validator(mode="after")
    def bounded_lifetime(self) -> "RunRecord":
        seconds = (self.expires_at - self.created_at).total_seconds()
        if not 0 < seconds <= 3600:
            raise ValueError("run lifetime must be positive and at most 60 minutes")
        if self.manifest.run_id != self.run_id:
            raise ValueError("manifest must belong to this run")
        return self


class CreateRunRequest(StrictModel):
    source_type: Literal["pasted_text", "bundled_sample"]
    title: NonEmptyText
    text: Annotated[str, Field(min_length=1, max_length=50_000)] | None = None
    sample_id: Identifier | None = None
    non_confidential_confirmed: bool = False

    @model_validator(mode="after")
    def source_and_consent(self) -> "CreateRunRequest":
        if self.source_type == "pasted_text":
            if (
                self.text is None
                or not self.text.strip()
                or self.sample_id is not None
                or not self.non_confidential_confirmed
            ):
                raise ValueError(
                    "pasted text requires nonempty text and non-confidential confirmation; maximum 50000 characters"
                )
        elif self.sample_id is None or self.text is not None:
            raise ValueError("bundled sample requires a sample ID and no pasted text")
        return self


class CreateRunResponse(StrictModel):
    run_id: Identifier


class ConfirmContractRequest(StrictModel):
    """Confirm a server-held baseline by identity/hash and submit reviewed intent.

    The coordinator checks both anchors against the stored provisional baseline;
    the browser cannot replace the compiled rules or unsupported-clause mappings.
    """

    decision: Literal["confirm", "reject"]
    baseline_policy_id: Identifier | None = None
    baseline_policy_sha256: Sha256 | None = Field(
        default=None,
        description="Artifact SHA256 of the exact server-held baseline PolicyIR.",
    )
    invariants: Annotated[tuple[InvariantSummary, ...], Field(max_length=5)] = ()
    required_dimensions: EffectDimensions = frozenset()

    @model_validator(mode="after")
    def confirmation_shape(self) -> "ConfirmContractRequest":
        if self.decision == "confirm":
            if (
                self.baseline_policy_id is None
                or self.baseline_policy_sha256 is None
                or not 3 <= len(self.invariants) <= 5
                or not self.required_dimensions
            ):
                raise ValueError(
                    "confirmation requires baseline ID/hash, three to five invariants, and required dimensions"
                )
            if len({item.invariant_id for item in self.invariants}) != len(
                self.invariants
            ):
                raise ValueError("invariant IDs must be unique")
            if len({item.assertion.assertion_id for item in self.invariants}) != len(
                self.invariants
            ):
                raise ValueError("invariant assertion IDs must be unique")
        elif (
            self.baseline_policy_id is not None
            or self.baseline_policy_sha256 is not None
            or self.invariants
            or self.required_dimensions
        ):
            raise ValueError("rejection cannot include a confirmed contract")
        return self


class SelectFindingsRequest(StrictModel):
    decisions: Annotated[tuple[FindingDecision, ...], Field(min_length=1)]

    @model_validator(mode="after")
    def unique_decisions(self) -> "SelectFindingsRequest":
        if len({item.finding_id for item in self.decisions}) != len(self.decisions):
            raise ValueError("each finding receives only one decision")
        return self


class ConfirmRevisionRequest(StrictModel):
    proposal_id: Identifier
    decision: Literal["confirm", "reject"]


class RunActionResponse(StrictModel):
    run_id: Identifier
    stage: RunStage
    allowed_actions: tuple[RunAction, ...]


class DeleteRunResponse(StrictModel):
    run_id: Identifier
    deleted: Literal[True] = True


class HealthResponse(StrictModel):
    status: Literal["ok", "degraded"]
    provider_configured: bool
    engine_version: NonEmptyText
