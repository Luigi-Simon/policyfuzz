"""Validate a bounded proposal completely, then return a new policy atomically."""

from dataclasses import dataclass

from app.core.artifacts import semantic_payload_projection
from app.core.hashing import canonical_sha256
from app.domain.models import (
    AnalyzeFindingsRequest,
    ApplyRevisionRequest,
    EvaluatePolicyRequest,
    InputHashes,
    OverrideRef,
    PatchApplicationResult,
    PolicyIR,
    PublicError,
    Rule,
    SessionRevisionProvenance,
)
from app.features.evaluation.engine import DeterministicEvaluationEngine, payload_hash
from app.features.evaluation.errors import PatchValidationError
from app.features.evaluation.findings import DeterministicFindingAnalyzer
from app.features.evaluation.rule_validation import (
    conditions_unrestricted,
    validate_rule_set,
)
from app.features.evaluation.signatures import semantic_rule_signature


def baseline_findings(request):
    inputs = InputHashes(
        policy_sha256=payload_hash(request.policy),
        contract_sha256=payload_hash(request.contract),
        suite_sha256=payload_hash(request.suite),
        engine_sha256="0" * 64,
        run_manifest_sha256="0" * 64,
    )
    evaluation = DeterministicEvaluationEngine().evaluate(
        EvaluatePolicyRequest(
            policy=request.policy,
            contract=request.contract,
            suite=request.suite,
            inputs=inputs,
            engine_version=request.suite.engine_version,
        )
    )
    return (
        DeterministicFindingAnalyzer()
        .analyze(
            AnalyzeFindingsRequest(
                policy=request.policy,
                contract=request.contract,
                suite=request.suite,
                evaluation=evaluation,
            )
        )
        .findings
    )


def validate_proposal_anchors(request):
    proposal = request.proposal
    if not (
        proposal.document_sha256
        == request.policy.document_sha256
        == request.suite.document_sha256
        and proposal.rule_set_sha256
        == request.suite.rule_set_sha256
        == canonical_sha256(semantic_payload_projection(request.policy))
        and proposal.policy_contract_sha256
        == request.suite.policy_contract_sha256
        == payload_hash(request.contract)
        and proposal.suite_sha256
        == request.suite.content_sha256
        == payload_hash(request.suite)
    ):
        raise PatchValidationError("HASH_MISMATCH")


@dataclass(frozen=True)
class DeterministicRevisionApplier:
    def apply_revision(self, request: ApplyRevisionRequest) -> PatchApplicationResult:
        try:
            return self._apply(ApplyRevisionRequest.model_validate(request))
        except (ValueError, TypeError, KeyError) as exc:
            return PatchApplicationResult(
                proposal_id=request.proposal.proposal_id,
                applied=False,
                error=PublicError(
                    code="REVISION_INVALID",
                    message=f"Structured revision rejected: {str(exc)[:180]}",
                ),
            )

    def _apply(self, request):
        validate_proposal_anchors(request)
        findings = {f.finding_id: f for f in baseline_findings(request)}
        accepted = request.proposal.accepted_finding_ids
        if any(
            fid not in findings
            or findings[fid].evidence_level == "candidate"
            or any(
                s.partition != "visible"
                for s in request.suite.scenarios
                if s.scenario_id in findings[fid].scenario_ids
            )
            for fid in accepted
        ):
            raise PatchValidationError("targets must be reproduced reviewable findings")
        if set(accepted) != {
            fid for op in request.proposal.operations for fid in op.finding_ids
        }:
            raise PatchValidationError("all accepted findings require an operation")
        baseline = {r.rule_id: r for r in request.policy.rules}
        revised = dict(baseline)
        changed = set()
        for index, operation in enumerate(request.proposal.operations):
            if operation.rule_id in changed:
                raise PatchValidationError(
                    "a rule may be revised only once per proposal"
                )
            targets = [findings[fid] for fid in operation.finding_ids]
            allowed_dimensions = {f.dimension for f in targets}
            target_rules = {rid for f in targets for rid in f.rule_ids}
            citations = {
                baseline[rid].provenance.citation_id
                for rid in target_rules
                if rid in baseline and baseline[rid].provenance.kind == "text_citation"
            }
            old = baseline.get(operation.rule_id)
            if old and old.provenance.kind == "text_citation":
                citations.add(old.provenance.citation_id)
            if not citations:
                # An omitted invariant dimension still has motivating baseline policy citations.
                citations = {
                    r.provenance.citation_id
                    for r in baseline.values()
                    if r.provenance.kind == "text_citation"
                }
            provenance = SessionRevisionProvenance(
                proposal_id=request.proposal.proposal_id,
                operation_index=index,
                confirmed_at=request.confirmed_at,
                baseline_citation_ids=tuple(sorted(citations)),
            )
            if operation.kind == "add_override":
                if old is None or operation.target_rule_id not in baseline:
                    raise PatchValidationError("override endpoint missing")
                if operation.dimension not in allowed_dimensions or not all(
                    f.finding_type == "conflict" for f in targets
                ):
                    raise PatchValidationError(
                        "override requires the targeted conflict dimension"
                    )
                if (
                    operation.rule_id not in target_rules
                    or operation.target_rule_id not in target_rules
                ):
                    raise PatchValidationError(
                        "override endpoints must belong to target conflict"
                    )
                edge = OverrideRef(
                    dimension=operation.dimension,
                    target_rule_id=operation.target_rule_id,
                )
                if edge in old.overrides:
                    raise PatchValidationError("no-op override")
                replacement = old.model_copy(
                    update={
                        "overrides": old.overrides + (edge,),
                        "revision": old.revision + 1,
                        "provenance": provenance,
                    }
                )
            else:
                if operation.kind == "add_rule" and old is not None:
                    raise PatchValidationError("rule ID collision")
                if operation.kind == "replace_rule":
                    if old is None or old.revision != operation.expected_revision:
                        raise PatchValidationError("stale or missing rule")
                    if target_rules and old.rule_id not in target_rules:
                        raise PatchValidationError("unrelated rule replacement")
                draft = operation.rule
                if conditions_unrestricted(draft.when):
                    raise PatchValidationError("unrestricted catch-all revision")
                replacement = Rule(
                    rule_id=operation.rule_id,
                    revision=old.revision + 1 if old else 1,
                    description=draft.description,
                    when=draft.when,
                    effects=draft.effects,
                    overrides=draft.overrides,
                    provenance=provenance,
                )
                if old:
                    old_unrelated = {
                        e.dimension: e.value
                        for e in old.effects
                        if e.dimension not in allowed_dimensions
                    }
                    new_unrelated = {
                        e.dimension: e.value
                        for e in replacement.effects
                        if e.dimension not in allowed_dimensions
                    }
                    if old_unrelated != new_unrelated or (
                        old_unrelated and old.when != replacement.when
                    ):
                        raise PatchValidationError("unrelated effect change")
                    old_unrelated_overrides = {
                        edge
                        for edge in old.overrides
                        if edge.dimension not in allowed_dimensions
                    }
                    new_unrelated_overrides = {
                        edge
                        for edge in replacement.overrides
                        if edge.dimension not in allowed_dimensions
                    }
                    if old_unrelated_overrides != new_unrelated_overrides:
                        raise PatchValidationError("unrelated override change")
                    if not {e.dimension for e in old.effects} <= {
                        e.dimension for e in replacement.effects
                    }:
                        raise PatchValidationError("effect deletion")
                    if (
                        {e.dimension for e in replacement.effects}
                        - {e.dimension for e in old.effects}
                        - allowed_dimensions
                    ):
                        raise PatchValidationError("unrelated dimension")
                elif (
                    not {e.dimension for e in replacement.effects} <= allowed_dimensions
                ):
                    raise PatchValidationError("unrelated added dimension")
            changed_edges = set(replacement.overrides) ^ set(
                old.overrides if old else ()
            )
            for edge in changed_edges:
                if not any(
                    finding.finding_type == "conflict"
                    and finding.dimension == edge.dimension
                    and operation.rule_id in finding.rule_ids
                    and edge.target_rule_id in finding.rule_ids
                    for finding in targets
                ):
                    raise PatchValidationError(
                        "override change must stay within the accepted conflict endpoints"
                    )
            revised[operation.rule_id] = replacement
            changed.add(operation.rule_id)
        policy = PolicyIR(
            policy_id=request.policy.policy_id,
            document_sha256=request.policy.document_sha256,
            kind="structured_revision",
            review_status="session_confirmed",
            rules=tuple(revised[k] for k in sorted(revised)),
            unsupported_clauses=request.policy.unsupported_clauses,
        )
        validate_rule_set(policy)
        for rid in changed:
            if rid in baseline and semantic_rule_signature(
                baseline[rid], baseline
            ) == semantic_rule_signature(revised[rid], revised):
                raise PatchValidationError("no-op semantic revision")
        return PatchApplicationResult(
            proposal_id=request.proposal.proposal_id,
            applied=True,
            revised_policy=policy,
            changed_rule_ids=tuple(sorted(changed)),
        )
