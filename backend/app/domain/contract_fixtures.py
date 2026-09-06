"""SYNTHETIC HACKATHON SAMPLE: a contract illustration, not engine/model output.

All evidence is authored synthetic display data. Structured identities use the
sole canonical hash helper; source and quote digests hash exact raw UTF-8 bytes.
The small labeled anchors below identify this fixture's illustrative inputs and
are not claims that stored evaluation or benchmark artifacts exist.
"""

import argparse
import sys
from hashlib import sha256
from pathlib import Path

from app.core.hashing import canonical_sha256
from app.domain.export_schemas import check_file, stable_json, write_file
from app.domain.models import (
    ArtifactRef,
    ArtifactSummary,
    AssertionCounts,
    AssertionTransitionCounts,
    ComplianceResult,
    CoverageCounters,
    DimensionResult,
    EffectStateCounts,
    FindingSummary,
    HoldoutEvidenceSummary,
    InputHashes,
    PatchAcceptanceCounts,
    PatchAcceptanceReport,
    Predicate,
    PredicateResult,
    PublicComparisonMetrics,
    PublicMetrics,
    RejectionEvidence,
    RunEvent,
    RunView,
    SourceSpan,
    UnsupportedClauseEvidence,
    VisibleTraceSummary,
)

LABEL = "SYNTHETIC HACKATHON SAMPLE"
FIXED_TIMESTAMP = "2026-09-04T12:00:00Z"
SYNTHETIC_SOURCE = (
    "SYNTHETIC HACKATHON SAMPLE\n"
    "1. Meals are eligible. Receipts are required. Meal claims are capped at SGD 50.\n"
    "2. A manager must approve hotel claims.\n"
    "3. Exceptional meal claims may receive a reasonable discretionary allowance.\n"
)
SOURCE_SHA256 = sha256(SYNTHETIC_SOURCE.encode("utf-8")).hexdigest()
SYNTHETIC_SUITE_ANCHOR = {
    "label": LABEL,
    "kind": "illustrative_frozen_suite",
    "seed": 42,
    "visible_scenario_count": 5,
    "holdout_scenario_count": 1,
    "assertion_count": 5,
    "source_sha256": SOURCE_SHA256,
}
SYNTHETIC_ENGINE_ANCHOR = {
    "label": LABEL,
    "kind": "illustrative_engine",
    "engine_version": "1.0",
    "execution": "No engine or model was run to author this fixture.",
}
_CONTRACT_ANCHOR = {
    "label": LABEL,
    "kind": "illustrative_confirmed_contract",
    "invariant_count": 3,
    "source_sha256": SOURCE_SHA256,
}
_MANIFEST_ANCHOR = {
    "label": LABEL,
    "run_id": "synthetic-completed-run",
    "mode": "cached",
    "started_at": FIXED_TIMESTAMP,
    "seed": 42,
}


def fixture_input_hashes(phase: str) -> InputHashes:
    """Full digests of fixed synthetic anchors, with only policy varying by phase."""
    if phase not in {"baseline", "revised"}:
        raise ValueError("phase must be baseline or revised")
    return InputHashes(
        policy_sha256=canonical_sha256(
            {
                "label": LABEL,
                "source_sha256": SOURCE_SHA256,
                "kind": "illustrative_policy",
                "phase": phase,
                "meal_cap_minor": 5000 if phase == "baseline" else 4500,
            }
        ),
        contract_sha256=canonical_sha256(_CONTRACT_ANCHOR),
        suite_sha256=canonical_sha256(SYNTHETIC_SUITE_ANCHOR),
        engine_sha256=canonical_sha256(SYNTHETIC_ENGINE_ANCHOR),
        run_manifest_sha256=canonical_sha256(_MANIFEST_ANCHOR),
    )


def _span(quote: str, section: str) -> SourceSpan:
    start = SYNTHETIC_SOURCE.index(quote)
    return SourceSpan(
        page=1,
        start=start,
        end=start + len(quote),
        quote=quote,
        quote_sha256=sha256(quote.encode("utf-8")).hexdigest(),
        section=section,
    )


def _traces(phase: str) -> tuple[VisibleTraceSummary, ...]:
    dimensions = (
        "eligibility",
        "receipt_requirement",
        "approval_requirement",
        "claim_cap_minor",
        "daily_category_cap_minor",
    )
    rows = (
        ("VALUE", "VALUE", "VALUE", "VALUE", "VALUE"),
        ("VALUE", "VALUE", "VALUE", "GAP", "NOT_APPLICABLE"),
        ("CONFLICT", "VALUE", "VALUE", "INCONCLUSIVE", "ERROR"),
        ("VALUE", "VALUE", "VALUE", "GAP", "NOT_APPLICABLE"),
        ("CONFLICT", "VALUE", "VALUE", "INCONCLUSIVE", "ERROR"),
    )
    traces = []
    for index, states in enumerate(rows, start=1):
        values = ("allow", "required", "manager", 5000, 10000)
        if phase == "revised":
            values = (
                "deny" if index == 2 else "allow",
                "required",
                "manager",
                4500,
                10000,
            )
        results = tuple(
            DimensionResult(
                dimension=dimension,
                status=status,
                value=value if status == "VALUE" else None,
                conflicting_values=("allow", "deny") if status == "CONFLICT" else (),
                applicable_rule_ids=("synthetic-rule-meal", "synthetic-rule-exception")
                if status == "CONFLICT"
                else (("synthetic-rule-meal",) if status == "VALUE" else ()),
                unsupported_clause_ids=("synthetic-discretionary-clause",)
                if status == "INCONCLUSIVE"
                else (),
            )
            for dimension, status, value in zip(dimensions, states, values, strict=True)
        )
        payload = {
            "schema_version": "1.0",
            "partition": "visible",
            "scenario_id": f"synthetic-visible-{index}",
            "phase": phase,
            "fired_rule_ids": ("synthetic-rule-meal", "synthetic-rule-exception")
            if "CONFLICT" in states
            else ("synthetic-rule-meal",),
            "predicate_results": (
                PredicateResult(
                    rule_id="synthetic-rule-meal",
                    predicate_index=0,
                    matched=True,
                ),
                PredicateResult(
                    rule_id="synthetic-rule-exception",
                    predicate_index=0,
                    matched="CONFLICT" in states,
                ),
            ),
            "resolved_effects": results,
            "compliance_values": (
                ComplianceResult(
                    dimension="receipt_requirement",
                    status="COMPLIANT",
                ),
            ),
            "source_citations": (
                _span(
                    "Meals are eligible. Receipts are required. Meal claims are capped at SGD 50.",
                    "1",
                ),
            ),
        }
        traces.append(
            VisibleTraceSummary(**payload, trace_sha256=canonical_sha256(payload))
        )
    return tuple(traces)


def build_completed_run_view() -> RunView:
    """Build the complete display contract using conspicuously synthetic evidence."""
    baseline_inputs = fixture_input_hashes("baseline")
    revised_inputs = fixture_input_hashes("revised")
    states = EffectStateCounts(
        VALUE=20,
        GAP=2,
        NOT_APPLICABLE=2,
        CONFLICT=2,
        INCONCLUSIVE=2,
        ERROR=2,
    )
    baseline = PublicMetrics(
        scenario_count=6,
        effect_states=states,
        assertions=AssertionCounts(passed=2, failed=2, inconclusive=1),
        unique_finding_count=3,
        assertion_pass_percent=40,
    )
    revised = PublicMetrics(
        scenario_count=6,
        effect_states=states,
        assertions=AssertionCounts(passed=2, failed=2, error=1),
        unique_finding_count=3,
        assertion_pass_percent=40,
    )
    acceptance = PatchAcceptanceReport(
        baseline_inputs=baseline_inputs,
        revised_inputs=revised_inputs,
        suite_hash_matches=True,
        all_target_findings_fixed=True,
        zero_new_failures_outside_targets=False,
        zero_protected_regressions=False,
        no_increase_in_gap_conflict_inconclusive_or_error=True,
        unrelated_rules_unchanged=True,
        holdout_not_worse=True,
        patch_accepted=False,
        counts=PatchAcceptanceCounts(
            target_findings=1,
            fixed_target_findings=1,
            new_failures_outside_targets=1,
            protected_regressions=1,
            baseline_gap_conflict_inconclusive_or_error=8,
            revised_gap_conflict_inconclusive_or_error=8,
            unrelated_rule_changes=0,
            holdout_regressions=0,
        ),
    )
    comparison = PublicComparisonMetrics(
        baseline=baseline,
        revised=revised,
        acceptance=acceptance,
        assertion_transition_counts=AssertionTransitionCounts(
            pass_to_pass=1,
            fail_to_pass=1,
            pass_to_fail=1,
            fail_to_fail=1,
            inconclusive_or_error=1,
        ),
        patch_accepted=False,
        protected_regressions=1,
        new_failures_outside_targets=1,
    )
    artifact = ArtifactRef(
        artifact_type="patch_acceptance_report",
        artifact_sha256=canonical_sha256(acceptance),
        semantic_sha256=canonical_sha256(acceptance),
    )
    unsupported_span = _span(
        "Exceptional meal claims may receive a reasonable discretionary allowance.",
        "3",
    )
    return RunView(
        run_id="synthetic-completed-run",
        stage="complete",
        mode="cached",
        allowed_actions=("delete_run",),
        terminal_status="complete",
        decision_at=FIXED_TIMESTAMP,
        events=(
            RunEvent(
                timestamp=FIXED_TIMESTAMP,
                stage="complete",
                artifact=artifact,
                action_summary=f"{LABEL}: authored contract illustration; no engine or model run. Patch acceptance is false.",
            ),
        ),
        artifacts=(
            ArtifactSummary(
                artifact=artifact,
                title=f"{LABEL}: aggregate patch acceptance",
                item_count=7,
            ),
        ),
        coverage=CoverageCounters(
            total_rules=2,
            covered_rules=2,
            total_invariants=3,
            covered_invariants=3,
            total_predicate_branches=4,
            covered_predicate_branches=3,
            scenario_count=6,
        ),
        findings=(
            FindingSummary(
                finding_id="synthetic-finding-cap",
                finding_type="intent_breach",
                dimension="claim_cap_minor",
                summary=f"{LABEL}: meal-cap intent example.",
                severity="high",
                review_status="accepted",
                witness_count=1,
            ),
            FindingSummary(
                finding_id="synthetic-finding-conflict",
                finding_type="conflict",
                dimension="eligibility",
                summary=f"{LABEL}: conflicting eligibility example.",
                review_status="rejected",
                witness_count=2,
            ),
            FindingSummary(
                finding_id="synthetic-finding-unsupported",
                finding_type="unsupported_clause",
                dimension="claim_cap_minor",
                summary=f"{LABEL}: discretionary clause remains inconclusive.",
                review_status="rejected",
                witness_count=2,
            ),
        ),
        unsupported_clauses=(
            UnsupportedClauseEvidence(
                clause_id="synthetic-discretionary-clause",
                span=unsupported_span,
                reason_code="unsupported_logic",
                affected_dimensions=frozenset({"claim_cap_minor"}),
                when_hint=(
                    Predicate(field="expense_category", operator="eq", value="meal"),
                ),
                disposition="retained_inconclusive",
            ),
        ),
        rejections=(
            RejectionEvidence(
                item_kind="rule",
                item_id="synthetic-rejected-rule",
                source_spans=(unsupported_span,),
                reason_code="unsupported_logic",
                disposition="excluded",
            ),
            RejectionEvidence(
                item_kind="scenario",
                item_id="synthetic-rejected-scenario",
                source_spans=(),
                reason_code="invalid_facts",
                disposition="excluded",
            ),
        ),
        traces=(*_traces("baseline"), *_traces("revised")),
        holdout_evidence=HoldoutEvidenceSummary(
            scenario_count=1,
            unsupported_clause_count=0,
            rejected_rule_count=0,
            rejected_scenario_count=1,
            baseline_effect_states=EffectStateCounts(VALUE=5),
            revised_effect_states=EffectStateCounts(VALUE=5),
        ),
        baseline_metrics=baseline,
        comparison_metrics=comparison,
    )


def completed_fixture_json() -> str:
    """Stable JSON for the fixed completed fixture (its set field is singleton)."""
    return stable_json(build_completed_run_view().model_dump(mode="json"))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--output", type=Path)
    mode.add_argument("--check", type=Path)
    args = parser.parse_args(argv)
    content = completed_fixture_json()
    if args.check:
        if not check_file(args.check, content):
            print(f"Fixture drift: {args.check}", file=sys.stderr)
            return 1
    else:
        write_file(args.output, content)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
