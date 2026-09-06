import json

import pytest

from app.core.artifacts import complete_payload_projection, semantic_payload_projection
from app.core.hashing import canonical_sha256
from app.domain.models import (
    AddRuleOperation,
    Finding,
    FindingDecision,
    FindingReport,
    ProposeRevisionRequest,
    ReplaceRuleOperation,
    RevisionProposal,
    RevisionRuleDraft,
    TraceRef,
)
from app.features.policy.revision import (
    RevisionValidationError,
    build_revision_prompt,
    parse_and_validate_revision_proposal,
    validate_revision_proposal,
)
from app.features.policy.model_output import ModelOutputValidationError
from tests.domain.factories import (
    HASH,
    make_inputs,
    make_policy,
    make_policy_contract,
    make_scenario_suite,
)


def _request(*, evidence_level: str = "mechanically_reproduced"):
    policy = make_policy()
    contract = make_policy_contract()
    rule_set_sha256 = canonical_sha256(semantic_payload_projection(policy))
    contract_sha256 = canonical_sha256(complete_payload_projection(contract))
    suite = make_scenario_suite(
        document_sha256=policy.document_sha256,
        policy_contract_sha256=contract_sha256,
        rule_set_sha256=rule_set_sha256,
    )
    suite_sha256 = canonical_sha256(complete_payload_projection(suite))
    finding = Finding(
        finding_id="finding-1",
        fingerprint_sha256=HASH,
        finding_type=(
            "potential_loophole" if evidence_level == "candidate" else "structural_gap"
        ),
        evidence_level=evidence_level,
        scenario_ids=("scenario-0",),
        rule_ids=("rule-meal",),
        dimension="claim_cap_minor",
        traces=(TraceRef(scenario_id="scenario-0", trace_sha256=HASH),),
    )
    request = ProposeRevisionRequest(
        policy=policy,
        contract=contract,
        suite=suite,
        findings=FindingReport(
            report_id="findings-1", inputs=make_inputs(), findings=(finding,)
        ),
        decisions=(FindingDecision(finding_id="finding-1", decision="accept"),),
        document_sha256=policy.document_sha256,
        rule_set_sha256=rule_set_sha256,
        policy_contract_sha256=contract_sha256,
        suite_sha256=suite_sha256,
    )
    return request


def _rule_draft() -> RevisionRuleDraft:
    from app.domain.models import Effect, Predicate

    return RevisionRuleDraft(
        description="Lower meal cap",
        when=(Predicate(field="expense_category", operator="eq", value="meal"),),
        effects=(Effect(dimension="claim_cap_minor", value=4000),),
    )


def _proposal(request: ProposeRevisionRequest) -> RevisionProposal:
    return RevisionProposal(
        proposal_id="model-supplied-id",
        document_sha256=request.document_sha256,
        rule_set_sha256=request.rule_set_sha256,
        policy_contract_sha256=request.policy_contract_sha256,
        suite_sha256=request.suite_sha256,
        accepted_finding_ids=("finding-1",),
        operations=(
            ReplaceRuleOperation(
                rule_id="rule-meal",
                expected_revision=0,
                rule=_rule_draft(),
                finding_ids=("finding-1",),
            ),
        ),
        draft_policy_wording="Unverified draft: meal claims have a lower cap.",
    )


def test_revision_validation_recomputes_id_and_marks_wording_unverified() -> None:
    request = _request()

    result = validate_revision_proposal(request, _proposal(request))

    assert result.proposal.proposal_id != "model-supplied-id"
    assert result.proposal.proposal_id.startswith("proposal-")
    assert result.draft_wording_status == "unverified"
    assert result.proposal.draft_policy_wording.startswith(
        "[AI-GENERATED, UNVERIFIED]"
    )


def test_revision_rejects_stale_anchor() -> None:
    request = _request()
    proposal = _proposal(request).model_copy(update={"suite_sha256": "b" * 64})

    with pytest.raises(RevisionValidationError, match="STALE_ARTIFACT_ANCHOR"):
        validate_revision_proposal(request, proposal)


def test_revision_rejects_unknown_or_stale_rule() -> None:
    request = _request()
    operation = _proposal(request).operations[0].model_copy(
        update={"rule_id": "missing-rule"}
    )
    proposal = _proposal(request).model_copy(update={"operations": (operation,)})

    with pytest.raises(RevisionValidationError, match="UNKNOWN_RULE_ID"):
        validate_revision_proposal(request, proposal)


def test_revision_rejects_candidate_findings() -> None:
    request = _request(evidence_level="candidate")

    with pytest.raises(RevisionValidationError, match="FINDING_NOT_ELIGIBLE"):
        validate_revision_proposal(request, _proposal(request))


def test_add_rule_ignores_model_generated_rule_id() -> None:
    request = _request()
    proposal = _proposal(request).model_copy(
        update={
            "operations": (
                AddRuleOperation(
                    rule_id="model-rule-id",
                    rule=_rule_draft(),
                    finding_ids=("finding-1",),
                ),
            )
        }
    )

    result = validate_revision_proposal(request, proposal)

    assert result.proposal.operations[0].rule_id.startswith("rule-")
    assert result.proposal.operations[0].rule_id != "model-rule-id"


def test_revision_prompt_contains_only_visible_eligible_evidence() -> None:
    request = _request()

    prompt = build_revision_prompt(request)

    assert "finding-1" in prompt.payload_json
    assert "unverified" in prompt.system_instructions.lower()


@pytest.mark.parametrize(
    "operations",
    [
        [],
        [{"kind": "delete_rule", "rule_id": "rule-meal", "finding_ids": ["finding-1"]}],
    ],
)
def test_raw_revision_rejects_empty_or_delete_operations(operations) -> None:
    request = _request()
    payload = _proposal(request).model_dump(mode="json")
    payload["operations"] = operations

    with pytest.raises(ModelOutputValidationError, match="SCHEMA_VALIDATION_FAILED"):
        parse_and_validate_revision_proposal(request, json.dumps(payload))


def test_raw_revision_rejects_more_than_three_operations() -> None:
    request = _request()
    payload = _proposal(request).model_dump(mode="json")
    payload["operations"] = payload["operations"] * 4

    with pytest.raises(ModelOutputValidationError, match="SCHEMA_VALIDATION_FAILED"):
        parse_and_validate_revision_proposal(request, json.dumps(payload))


def test_rejected_findings_are_not_revision_inputs() -> None:
    request = _request().model_copy(
        update={
            "decisions": (
                FindingDecision(finding_id="finding-1", decision="reject"),
            )
        }
    )

    with pytest.raises(RevisionValidationError, match="NO_ACCEPTED_FINDINGS"):
        build_revision_prompt(request)
