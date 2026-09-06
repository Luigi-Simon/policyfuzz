"""Deterministic evaluation evidence and benchmark/metric report shapes."""

from typing import Annotated, Literal

from pydantic import Field, model_validator

from .common import (
    AssertionStatusValue,
    ComplianceStatusValue,
    EffectDimensions,
    EffectDimensionValue,
    EffectStatusValue,
    Identifier,
    InputHashes,
    NonEmptyText,
    NonNegativeInt,
    Percentage,
    PublicError,
    Severity,
    Sha256,
    SourceSpan,
    StrictModel,
    Timestamp,
)
from .policy import (
    EffectValue,
    PolicyContract,
    PolicyIR,
    RuleProvenance,
    validate_effect_value,
)
from .scenario import CoverageSnapshot, Scenario, ScenarioSuite


class PredicateResult(StrictModel):
    rule_id: Identifier
    predicate_index: NonNegativeInt
    matched: bool


class DimensionResult(StrictModel):
    dimension: EffectDimensionValue
    status: EffectStatusValue
    value: EffectValue | None = None
    conflicting_values: tuple[EffectValue, ...] = ()
    applicable_rule_ids: tuple[Identifier, ...] = ()
    overridden_rule_ids: tuple[Identifier, ...] = ()
    unsupported_clause_ids: tuple[Identifier, ...] = ()

    @model_validator(mode="after")
    def typed_resolution(self) -> "DimensionResult":
        if (self.status == "VALUE") != (self.value is not None):
            raise ValueError("only VALUE results carry a resolved value")
        if self.value is not None:
            validate_effect_value(self.dimension, self.value)
        for value in self.conflicting_values:
            validate_effect_value(self.dimension, value)
        if self.status == "CONFLICT":
            if len(set(self.conflicting_values)) < 2:
                raise ValueError("conflict requires at least two distinct values")
        elif self.conflicting_values:
            raise ValueError("only CONFLICT results carry conflicting values")
        return self


class ComplianceResult(StrictModel):
    dimension: Literal[
        "receipt_requirement",
        "approval_requirement",
        "claim_cap_minor",
        "daily_category_cap_minor",
    ]
    status: ComplianceStatusValue


class AssertionResult(StrictModel):
    assertion_id: Identifier
    status: AssertionStatusValue
    actual_value: EffectValue | Literal["COMPLIANT", "NONCOMPLIANT"] | None = None


class EvaluationTrace(StrictModel):
    scenario_id: Identifier
    fired_rule_ids: tuple[Identifier, ...]
    predicate_results: tuple[PredicateResult, ...]
    resolved_effects: tuple[DimensionResult, ...]
    compliance_values: tuple[ComplianceResult, ...]
    source_citations: tuple[RuleProvenance, ...]
    trace_sha256: Sha256


class ScenarioEvaluation(StrictModel):
    scenario_id: Identifier
    trace: EvaluationTrace
    assertion_results: tuple[AssertionResult, ...] = ()
    verdict: Literal["PASS", "FAIL", "UNSCORED", "INCONCLUSIVE", "ERROR"]
    error: PublicError | None = None

    @model_validator(mode="after")
    def scored_verdict_requires_assertion(self) -> "ScenarioEvaluation":
        if self.trace.scenario_id != self.scenario_id:
            raise ValueError("trace must belong to this scenario")
        if self.verdict in ("PASS", "FAIL") and not self.assertion_results:
            raise ValueError("PASS or FAIL requires an independent assertion result")
        if self.verdict == "PASS" and any(
            item.status != "PASS" for item in self.assertion_results
        ):
            raise ValueError("PASS cannot contain unsuccessful assertions")
        if self.verdict == "FAIL" and not any(
            item.status == "FAIL" for item in self.assertion_results
        ):
            raise ValueError("FAIL requires a failed assertion")
        return self


class EvaluationReport(StrictModel):
    report_id: Identifier
    inputs: InputHashes
    engine_version: NonEmptyText
    results: tuple[ScenarioEvaluation, ...]
    coverage: CoverageSnapshot

    @model_validator(mode="after")
    def unique_results(self) -> "EvaluationReport":
        if len({item.scenario_id for item in self.results}) != len(self.results):
            raise ValueError("scenario evaluation IDs must be unique")
        return self


FindingType = Literal[
    "structural_gap",
    "conflict",
    "intent_breach",
    "regression",
    "unsupported_clause",
    "potential_loophole",
]
EvidenceLevel = Literal["mechanically_reproduced", "session_confirmed", "candidate"]
FindingReviewStatus = Literal["pending", "accepted", "rejected"]


class TraceRef(StrictModel):
    scenario_id: Identifier
    trace_sha256: Sha256


class Finding(StrictModel):
    finding_id: Identifier
    fingerprint_sha256: Sha256
    finding_type: FindingType
    evidence_level: EvidenceLevel
    scenario_ids: Annotated[tuple[Identifier, ...], Field(min_length=1)]
    rule_ids: tuple[Identifier, ...] = ()
    invariant_id: Identifier | None = None
    assertion_id: Identifier | None = None
    dimension: EffectDimensionValue
    traces: Annotated[tuple[TraceRef, ...], Field(min_length=1)]
    citations: tuple[SourceSpan, ...] = ()
    review_status: FindingReviewStatus = "pending"
    severity: Severity | None = None
    severity_origin: Literal["session_invariant", "session_reviewer"] | None = None

    @model_validator(mode="after")
    def supported_evidence(self) -> "Finding":
        if (self.severity is None) != (self.severity_origin is None):
            raise ValueError("severity requires an independent severity origin")
        if self.severity_origin == "session_invariant" and self.invariant_id is None:
            raise ValueError("invariant severity requires an invariant reference")
        if (
            self.finding_type == "potential_loophole"
            and self.evidence_level != "candidate"
        ):
            raise ValueError("potential loopholes remain review candidates")
        if self.evidence_level == "candidate" and self.severity is not None:
            raise ValueError("candidate findings cannot carry authoritative severity")
        if self.finding_type == "intent_breach" and self.invariant_id is None:
            raise ValueError("intent breach requires an invariant")
        if self.finding_type == "regression" and self.assertion_id is None:
            raise ValueError("regression requires an assertion")
        if set(self.scenario_ids) != {trace.scenario_id for trace in self.traces}:
            raise ValueError("each witness requires a trace reference")
        return self


class FindingReport(StrictModel):
    report_id: Identifier
    inputs: InputHashes
    findings: tuple[Finding, ...]


class EvaluatePolicyRequest(StrictModel):
    policy: PolicyIR
    contract: PolicyContract
    suite: ScenarioSuite
    inputs: InputHashes
    engine_version: NonEmptyText


class AnalyzeFindingsRequest(StrictModel):
    policy: PolicyIR
    contract: PolicyContract
    suite: ScenarioSuite
    evaluation: EvaluationReport


class EffectStateCounts(StrictModel):
    VALUE: NonNegativeInt = 0
    GAP: NonNegativeInt = 0
    NOT_APPLICABLE: NonNegativeInt = 0
    CONFLICT: NonNegativeInt = 0
    INCONCLUSIVE: NonNegativeInt = 0
    ERROR: NonNegativeInt = 0


class AssertionCounts(StrictModel):
    passed: NonNegativeInt = 0
    failed: NonNegativeInt = 0
    inconclusive: NonNegativeInt = 0
    error: NonNegativeInt = 0


class MetricsReport(StrictModel):
    inputs: InputHashes
    scenario_count: NonNegativeInt
    effect_states: EffectStateCounts
    assertions: AssertionCounts
    unique_finding_count: NonNegativeInt
    coverage: CoverageSnapshot
    assertion_pass_percent: Percentage | None = None


class MetricsRequest(StrictModel):
    evaluation: EvaluationReport
    findings: FindingReport


class BenchmarkDefect(StrictModel):
    defect_id: Identifier
    finding_type: FindingType
    dimension: EffectDimensionValue
    target_ids: tuple[Identifier, ...]
    severity: Severity
    source_spans: tuple[SourceSpan, ...] = ()
    semantic_signature_sha256: Sha256 | None = None
    permitted_witness_ids: tuple[Identifier, ...] = ()
    expected_finding_fingerprint_sha256: Sha256 | None = None
    partition: Literal["visible", "holdout"] = "visible"
    unsupported_clause: bool = False


class BenchmarkManifest(StrictModel):
    """Private scoring input; must never be nested inside a RunView."""

    benchmark_id: Identifier
    document_sha256: Sha256
    policy_contract_sha256: Sha256
    engine_version: NonEmptyText
    sealed_at: Timestamp
    seal_sha256: Sha256
    defects: tuple[BenchmarkDefect, ...]
    gold_scenarios: tuple[Scenario, ...]
    required_dimensions: EffectDimensions

    @model_validator(mode="after")
    def gold_only(self) -> "BenchmarkManifest":
        if any(
            "gold" not in scenario.origins
            or any(assertion.origin != "gold" for assertion in scenario.assertions)
            for scenario in self.gold_scenarios
        ):
            raise ValueError("benchmark gold scenarios require gold origins and labels")
        if len({item.defect_id for item in self.defects}) != len(self.defects):
            raise ValueError("benchmark defect IDs must be unique")
        return self


class BenchmarkScore(StrictModel):
    benchmark_id: Identifier
    inputs: InputHashes
    true_positives: NonNegativeInt
    false_positives: NonNegativeInt
    false_negatives: NonNegativeInt
    precision_percent: Percentage | None = None
    recall_percent: Percentage | None = None
    f1_percent: Percentage | None = None


class ScoreBenchmarkRequest(StrictModel):
    manifest: BenchmarkManifest
    findings: FindingReport
    evaluation: EvaluationReport
