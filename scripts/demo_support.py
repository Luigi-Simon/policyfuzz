"""Recorded synthetic provider responses around the actual application stages.

This is a reproducible development demonstration, not a blind benchmark or a
live-provider quality measurement. Confirmation decisions are authored fixtures.
"""

from __future__ import annotations

import json
import sys
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT / "backend") not in sys.path:
    sys.path.insert(0, str(ROOT / "backend"))

from app.container import build_container
from app.core.artifacts import complete_payload_projection, semantic_payload_projection
from app.core.config import Settings
from app.core.fakes import ScriptedLLMClient
from app.core.hashing import canonical_sha256
from app.domain.models import (
    AddRuleOperation,
    ConfirmContractRequest,
    ConfirmRevisionRequest,
    CreateRunRequest,
    Effect,
    FindingDecision,
    LLMRequest,
    LLMResponse,
    OverrideRef,
    PolicyContract,
    Predicate,
    ReplaceRuleOperation,
    RevisionProposal,
    RevisionRuleDraft,
    RunRecord,
    SelectFindingsRequest,
)
from app.workflow.coordinator import RunCoordinator
from app.workflow.validation import validate_cached_record


class DemoClock:
    def wall_now(self):
        return datetime(2026, 9, 6, tzinfo=UTC)

    def monotonic(self):
        return 0.0


class DemoResponses:
    """Finite per-operation output script; no model request is written to disk."""

    def __init__(self):
        fixtures = ROOT / "team/person-2-policy/fixtures"
        self.outputs = {
            "policy_extraction": json.loads(
                (fixtures / "development-provider-extraction.json").read_text()
            ),
            "invariant_suggestion": json.loads(
                (fixtures / "development-invariant-suggestions.json").read_text()
            ),
            "scenario_generation": {"scenarios": []},
            "targeted_scenario_generation": {"scenarios": []},
        }
        self.client = ScriptedLLMClient()
        self.recorded = []
        self.used = set()

    async def complete_json(self, request: LLMRequest) -> LLMResponse:
        if (
            request.operation not in self.outputs
            or request.operation in self.used
            or request.repair_attempt
        ):
            raise ValueError("The recorded provider script does not match this stage.")
        self.used.add(request.operation)
        response = LLMResponse(output=self.outputs[request.operation])
        self.client.queue(response)
        result = await self.client.complete_json(request)
        self.recorded.append(
            {"operation": request.operation, "response": result.model_dump(mode="json")}
        )
        return result


def digest(value):
    return canonical_sha256(complete_payload_projection(value))


def latest(record, kind):
    return next(
        a.payload for a in reversed(record.artifacts) if a.artifact_type == kind
    )


def _draft(rule, **changes):
    fields = {
        name: getattr(rule, name)
        for name in ("description", "when", "effects", "overrides")
    }
    fields.update(changes)
    return RevisionRuleDraft(**fields)


def demo_proposal(record):
    policy = latest(record, "policy_ir")
    contract = latest(record, "policy_contract")
    suite = latest(record, "scenario_suite")
    findings = latest(record, "finding_report")
    scored = [
        f
        for f in findings.findings
        if f.evidence_level != "candidate"
        and f.finding_type in {"structural_gap", "conflict", "intent_breach"}
    ]
    if len(scored) != 3 or {f.finding_type for f in scored} != {
        "structural_gap",
        "conflict",
        "intent_breach",
    }:
        raise ValueError(
            "The development run must reproduce exactly the three authored defects."
        )
    by_type = {f.finding_type: f.finding_id for f in scored}
    receipt = next(
        r
        for r in policy.rules
        if any(
            e.dimension == "receipt_requirement" and e.value == "required"
            for e in r.effects
        )
    )
    hotel = next(
        r
        for r in policy.rules
        if any(
            p.field == "destination_type" and p.value == "international" for p in r.when
        )
    )
    hotel_exception = next(
        r
        for r in policy.rules
        if any(p.field == "expense_category" and p.value == "hotel" for p in r.when)
        and any(
            e.dimension == "approval_requirement" and e.value == "none"
            for e in r.effects
        )
    )
    receipt_conditions = tuple(
        p.model_copy(update={"operator": "gte"})
        if p.field == "amount_minor" and p.operator == "gt"
        else p
        for p in receipt.when
    )
    return RevisionProposal(
        proposal_id="scripted-development-revision",
        document_sha256=policy.document_sha256,
        rule_set_sha256=canonical_sha256(semantic_payload_projection(policy)),
        policy_contract_sha256=digest(contract),
        suite_sha256=digest(suite),
        accepted_finding_ids=tuple(sorted(f.finding_id for f in scored)),
        operations=(
            ReplaceRuleOperation(
                rule_id=receipt.rule_id,
                expected_revision=receipt.revision,
                rule=_draft(receipt, when=receipt_conditions),
                finding_ids=(by_type["structural_gap"],),
            ),
            ReplaceRuleOperation(
                rule_id=hotel.rule_id,
                expected_revision=hotel.revision,
                rule=_draft(
                    hotel,
                    overrides=(
                        *hotel.overrides,
                        OverrideRef(
                            dimension="approval_requirement",
                            target_rule_id=hotel_exception.rule_id,
                        ),
                    ),
                ),
                finding_ids=(by_type["conflict"],),
            ),
            AddRuleOperation(
                rule_id="scripted-daily-meal-cap",
                rule=RevisionRuleDraft(
                    description="Daily meal cap",
                    when=(
                        Predicate(
                            field="expense_category", operator="eq", value="meal"
                        ),
                    ),
                    effects=(
                        Effect(dimension="daily_category_cap_minor", value=10000),
                    ),
                ),
                finding_ids=(by_type["intent_breach"],),
            ),
        ),
        draft_policy_wording="SYNTHETIC HACKATHON SAMPLE — UNVERIFIED WORDING. Receipts are required at or above SGD 50. International hotel manager approval overrides the hotel exception. Meals have a daily SGD 100 cap.",
    )


def _require_stage(view, expected):
    if view.stage != expected:
        code = view.error.code if view.error else "NO_PUBLIC_ERROR"
        raise ValueError(
            f"Development flow stopped at {view.stage}: {code}; expected {expected}."
        )


async def run_demo():
    script = DemoResponses()
    settings = Settings(app_mode="live", llm_model="scripted-development-v1")
    container = build_container(settings, llm=script, clock=DemoClock())
    original = container.coordinator
    dependencies = {
        name: getattr(original, name)
        for name in (
            "store",
            "clock",
            "policy_compiler",
            "scenario_planner",
            "evaluation_engine",
            "finding_analyzer",
            "revision_planner",
            "revision_applier",
            "regression_analyzer",
            "ingest",
            "metrics",
            "manifest_factory",
            "draft_severity",
        )
    }
    coordinator = RunCoordinator(
        **dependencies,
        mode="cached",
        recording_demo=True,
        run_id_factory=lambda: "development-recording-v1",
    )
    container.coordinator = coordinator
    try:
        created = await coordinator.create_run(
            CreateRunRequest(
                source_type="bundled_sample",
                title="SYNTHETIC HACKATHON SAMPLE — NOT COMPANY POLICY",
                sample_id="development-policy",
            )
        )
        run_id = created.run_id
        await container.execute(run_id, lambda: coordinator.start(run_id))
        view = await coordinator.get_run(run_id)
        _require_stage(view, "awaiting_contract")
        pending = view.pending_confirmation
        intent = PolicyContract.model_validate_json(
            (
                ROOT / "samples/benchmarks/development/confirmed-contract.json"
            ).read_bytes()
        )
        severities = {i.invariant_id: i.severity for i in intent.invariants}
        command = ConfirmContractRequest(
            decision="confirm",
            baseline_policy_id=pending.baseline_policy_id,
            baseline_policy_sha256=pending.baseline_policy_sha256,
            invariants=tuple(
                i.model_copy(update={"severity": severities[i.invariant_id]})
                for i in pending.invariants
            ),
            required_dimensions=intent.required_dimensions,
        )
        await container.execute(
            run_id, lambda: coordinator.confirm_contract(run_id, command)
        )
        view = await coordinator.get_run(run_id)
        _require_stage(view, "awaiting_finding_review")
        record = await coordinator.store.get(run_id)
        proposal = demo_proposal(record)
        script.outputs["revision_proposal"] = proposal.model_dump(mode="json")
        findings = {f.finding_id: f for f in latest(record, "finding_report").findings}
        decisions = tuple(
            FindingDecision(
                finding_id=i,
                decision="accept",
                reviewer_severity="high" if findings[i].severity is None else None,
            )
            for i in view.pending_confirmation.finding_ids
        )
        await container.execute(
            run_id,
            lambda: coordinator.select_findings(
                run_id, SelectFindingsRequest(decisions=decisions)
            ),
        )
        view = await coordinator.get_run(run_id)
        _require_stage(view, "awaiting_revision_confirmation")
        command = ConfirmRevisionRequest(
            proposal_id=view.pending_confirmation.proposal_id, decision="confirm"
        )
        await container.execute(
            run_id, lambda: coordinator.confirm_revision(run_id, command)
        )
        view = await coordinator.get_run(run_id)
        _require_stage(view, "complete")
        stored = await coordinator.store.get(run_id)
        record = RunRecord.model_validate_json(
            stored.model_dump_json(
                exclude={"version", "source_request", "pending_confirmation"}
            )
        )
        validate_cached_record(record)
        comparison = latest(record, "comparison_bundle")
        if not comparison.acceptance.patch_accepted:
            raise ValueError(
                "The demonstration patch did not pass all seven acceptance gates."
            )
        return record, script.recorded
    finally:
        await container.aclose()
