from datetime import UTC, datetime

from app.core.artifacts import semantic_payload_projection
from app.core.hashing import canonical_sha256
from app.domain.models import (
    AnalyzeFindingsRequest,
    ApplyRevisionRequest,
    Effect,
    Predicate,
    ReplaceRuleOperation,
    RevisionProposal,
    RevisionRuleDraft,
)
from app.features.evaluation.engine import DeterministicEvaluationEngine, payload_hash
from app.features.evaluation.findings import DeterministicFindingAnalyzer
from app.features.evaluation.patches import DeterministicRevisionApplier
from app.features.evaluation.signatures import semantic_rule_signature


def test_five_gap_witnesses_group(
    request_factory, policy_factory, rule_factory, scenario_factory
):
    policy = policy_factory(
        [
            rule_factory(
                when=(Predicate(field="amount_minor", operator="lt", value=1000),)
            )
        ]
    )
    request = request_factory(policy, [scenario_factory(f"s{i}") for i in range(5)])
    report = DeterministicEvaluationEngine().evaluate(request)
    findings = DeterministicFindingAnalyzer().analyze(
        AnalyzeFindingsRequest(
            policy=policy,
            contract=request.contract,
            suite=request.suite,
            evaluation=report,
        )
    )
    gaps = [f for f in findings.findings if f.finding_type == "structural_gap"]
    assert len(gaps) == 1
    assert len(gaps[0].scenario_ids) == 5
    assert gaps[0].severity is None


def test_unasserted_allow_not_loophole(request_factory):
    request = request_factory()
    report = DeterministicEvaluationEngine().evaluate(request)
    findings = DeterministicFindingAnalyzer().analyze(
        AnalyzeFindingsRequest(
            policy=request.policy,
            contract=request.contract,
            suite=request.suite,
            evaluation=report,
        )
    )
    assert findings.findings == ()


def test_semantic_signature_ignores_ids(rule_factory):
    a, b = rule_factory("a"), rule_factory("b")
    assert semantic_rule_signature(a, {"a": a}) == semantic_rule_signature(b, {"b": b})


def patch_request(request_factory, policy_factory, rule_factory):
    policy = policy_factory(
        [
            rule_factory(
                when=(Predicate(field="amount_minor", operator="lt", value=5000),)
            )
        ]
    )
    request = request_factory(policy)
    findings = DeterministicFindingAnalyzer().analyze(
        AnalyzeFindingsRequest(
            policy=policy,
            contract=request.contract,
            suite=request.suite,
            evaluation=DeterministicEvaluationEngine().evaluate(request),
        )
    )
    gap = next(f for f in findings.findings if f.finding_type == "structural_gap")
    draft = RevisionRuleDraft(
        description="Include boundary",
        when=(Predicate(field="amount_minor", operator="lte", value=5000),),
        effects=(Effect(dimension="eligibility", value="allow"),),
    )
    proposal = RevisionProposal(
        proposal_id="p",
        document_sha256=policy.document_sha256,
        rule_set_sha256=canonical_sha256(semantic_payload_projection(policy)),
        policy_contract_sha256=payload_hash(request.contract),
        suite_sha256=payload_hash(request.suite),
        accepted_finding_ids=(gap.finding_id,),
        operations=(
            ReplaceRuleOperation(
                rule_id="r1",
                expected_revision=1,
                rule=draft,
                finding_ids=(gap.finding_id,),
            ),
        ),
        draft_policy_wording="Synthetic revised wording",
    )
    return ApplyRevisionRequest(
        policy=policy,
        contract=request.contract,
        suite=request.suite,
        proposal=proposal,
        confirmed_at=datetime(2026, 9, 4, tzinfo=UTC),
    )


def test_patch_atomic_revision_and_provenance(
    request_factory, policy_factory, rule_factory
):
    request = patch_request(request_factory, policy_factory, rule_factory)
    before = request.policy.model_dump()
    result = DeterministicRevisionApplier().apply_revision(request)
    assert result.applied
    assert result.revised_policy.rules[0].revision == 2
    assert result.revised_policy.rules[0].provenance.kind == "session_revision"
    assert request.policy.model_dump() == before


def test_stale_patch_fails_without_mutation(
    request_factory, policy_factory, rule_factory
):
    request = patch_request(request_factory, policy_factory, rule_factory)
    request = request.model_copy(
        update={
            "proposal": request.proposal.model_copy(
                update={"rule_set_sha256": "f" * 64}
            )
        }
    )
    result = DeterministicRevisionApplier().apply_revision(request)
    assert not result.applied
    assert result.revised_policy is None


def test_disguised_unrestricted_catchall_rejected(
    request_factory, policy_factory, rule_factory
):
    request = patch_request(request_factory, policy_factory, rule_factory)
    op = request.proposal.operations[0]
    draft = op.rule.model_copy(
        update={"when": (Predicate(field="amount_minor", operator="gte", value=0),)}
    )
    proposal = request.proposal.model_copy(
        update={"operations": (op.model_copy(update={"rule": draft}),)}
    )
    result = DeterministicRevisionApplier().apply_revision(
        request.model_copy(update={"proposal": proposal})
    )
    assert not result.applied


def test_invalid_target_is_rejected(request_factory, policy_factory, rule_factory):
    request = patch_request(request_factory, policy_factory, rule_factory)
    op = request.proposal.operations[0].model_copy(update={"finding_ids": ("made-up",)})
    proposal = request.proposal.model_copy(
        update={"accepted_finding_ids": ("made-up",), "operations": (op,)}
    )
    assert (
        not DeterministicRevisionApplier()
        .apply_revision(request.model_copy(update={"proposal": proposal}))
        .applied
    )


def test_override_revision_changes_only_source(
    request_factory, policy_factory, rule_factory
):
    from app.domain.models import AddOverrideOperation

    policy = policy_factory(
        [rule_factory("allow", value="allow"), rule_factory("deny", value="deny")]
    )
    request = request_factory(policy)
    findings = DeterministicFindingAnalyzer().analyze(
        AnalyzeFindingsRequest(
            policy=policy,
            contract=request.contract,
            suite=request.suite,
            evaluation=DeterministicEvaluationEngine().evaluate(request),
        )
    )
    target = next(f for f in findings.findings if f.finding_type == "conflict")
    proposal = RevisionProposal(
        proposal_id="override",
        document_sha256=policy.document_sha256,
        rule_set_sha256=request.suite.rule_set_sha256,
        policy_contract_sha256=payload_hash(request.contract),
        suite_sha256=payload_hash(request.suite),
        accepted_finding_ids=(target.finding_id,),
        operations=(
            AddOverrideOperation(
                rule_id="allow",
                dimension="eligibility",
                target_rule_id="deny",
                finding_ids=(target.finding_id,),
            ),
        ),
        draft_policy_wording="Synthetic override.",
    )
    applied = DeterministicRevisionApplier().apply_revision(
        ApplyRevisionRequest(
            policy=policy,
            contract=request.contract,
            suite=request.suite,
            proposal=proposal,
            confirmed_at=datetime(2026, 9, 4, tzinfo=UTC),
        )
    )
    assert applied.applied, applied.error
    rules = {r.rule_id: r for r in applied.revised_policy.rules}
    assert rules["allow"].revision == 2
    assert rules["allow"].provenance.kind == "session_revision"
    assert rules["deny"] == policy.rules[1]
    assert applied.changed_rule_ids == ("allow",)
