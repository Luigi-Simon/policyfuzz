import json

import pytest

from app.core.artifacts import complete_payload_projection, semantic_payload_projection
from app.core.fakes import ScriptedLLMClient
from app.core.hashing import canonical_sha256
from app.domain.models import (
    AddRuleOperation,
    Assertion,
    Effect,
    Finding,
    FindingDecision,
    FindingReport,
    LLMResponse,
    OverrideRef,
    Predicate,
    ProposeRevisionRequest,
    ReplaceRuleOperation,
    RevisionProposal,
    RevisionRuleDraft,
    TraceRef,
)
from app.features.policy.model_output import ModelOutputValidationError
from app.features.policy.revision import (
    LLMRevisionPlanner,
    RevisionValidationError,
    build_revision_prompt,
    parse_and_validate_revision_proposal,
    validate_revision_proposal,
)
from tests.domain.factories import (
    HASH,
    make_inputs,
    make_policy,
    make_policy_contract,
    make_rule,
    make_scenario,
    make_scenario_suite,
)


def _request(*, evidence_level: str = "mechanically_reproduced", policy=None):
    policy = policy or make_policy()
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
    assert result.proposal.draft_policy_wording.startswith("[AI-GENERATED, UNVERIFIED]")


def test_revision_rejects_stale_anchor() -> None:
    request = _request()
    proposal = _proposal(request).model_copy(update={"suite_sha256": "b" * 64})

    with pytest.raises(RevisionValidationError, match="STALE_ARTIFACT_ANCHOR"):
        validate_revision_proposal(request, proposal)


def _semantic_replacement_request():
    target = make_rule(
        when=(
            Predicate(
                field="employee_role", operator="in", value=("employee", "manager")
            ),
            Predicate(field="amount_minor", operator="gt", value=100),
        ),
        effects=(
            Effect(dimension="claim_cap_minor", value=5000),
            Effect(dimension="approval_requirement", value="manager"),
        ),
        overrides=(
            OverrideRef(dimension="claim_cap_minor", target_rule_id="base-cap"),
            OverrideRef(
                dimension="approval_requirement", target_rule_id="base-approval"
            ),
        ),
    )
    return _request(
        policy=make_policy(
            rules=(
                target,
                make_rule(rule_id="base-cap"),
                make_rule(
                    rule_id="base-approval",
                    effects=(Effect(dimension="approval_requirement", value="none"),),
                ),
            )
        )
    )


def _replacement_proposal(request, **changes):
    target = request.policy.rules[0]
    values = {
        "description": "PRIVATE_DESCRIPTION_ONLY_CHANGE",
        "when": target.when,
        "effects": target.effects,
        "overrides": target.overrides,
    }
    draft = RevisionRuleDraft(**(values | changes))
    proposal = _proposal(request)
    return proposal.model_copy(
        update={
            "operations": (proposal.operations[0].model_copy(update={"rule": draft}),),
        }
    )


@pytest.mark.parametrize("reordered", [False, True])
def test_revision_rejects_description_only_or_reordered_semantic_noop(reordered):
    request = _semantic_replacement_request()
    changes = {}
    if reordered:
        target = request.policy.rules[0]
        changes = {
            "when": (
                target.when[1],
                target.when[0].model_copy(
                    update={"value": ("manager", "employee", "manager")}
                ),
                target.when[1],
            ),
            "effects": tuple(reversed(target.effects)),
            "overrides": tuple(reversed(target.overrides)),
        }
    with pytest.raises(
        RevisionValidationError, match="NO_OP_RULE_REPLACEMENT"
    ) as caught:
        validate_revision_proposal(request, _replacement_proposal(request, **changes))
    assert "PRIVATE_DESCRIPTION_ONLY_CHANGE" not in str(caught.value)


@pytest.mark.parametrize("field", ["when", "effects", "overrides"])
def test_revision_accepts_actual_change_to_any_structured_rule_component(field):
    request = _semantic_replacement_request()
    target = request.policy.rules[0]
    changes = {
        "when": (target.when[0], target.when[1].model_copy(update={"value": 101})),
        "effects": (
            target.effects[0].model_copy(update={"value": 4000}),
            target.effects[1],
        ),
        "overrides": target.overrides[:1],
    }
    proposal = _replacement_proposal(request, **{field: changes[field]})
    result = validate_revision_proposal(request, proposal)
    assert getattr(result.proposal.operations[0].rule, field) == changes[field]


@pytest.mark.parametrize("schema_repair", [False, True])
async def test_semantic_noop_rejection_never_adds_a_model_repair(schema_repair):
    request = _semantic_replacement_request()
    response = LLMResponse(
        output=_replacement_proposal(request).model_dump(mode="json")
    )
    responses = (
        (LLMResponse(output={"invalid": "schema"}), response)
        if schema_repair
        else (response,)
    )
    llm = ScriptedLLMClient(responses)

    with pytest.raises(RevisionValidationError, match="NO_OP_RULE_REPLACEMENT"):
        await LLMRevisionPlanner(llm).propose(request)

    assert len(llm.requests) == (2 if schema_repair else 1)


def test_revision_rejects_unknown_or_stale_rule() -> None:
    request = _request()
    operation = (
        _proposal(request).operations[0].model_copy(update={"rule_id": "missing-rule"})
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


def test_revision_requires_every_accepted_finding_to_have_an_operation() -> None:
    request = _request()
    second_finding = request.findings.findings[0].model_copy(
        update={"finding_id": "finding-2"}
    )
    request = request.model_copy(
        update={
            "findings": request.findings.model_copy(
                update={"findings": (*request.findings.findings, second_finding)}
            ),
            "decisions": (
                *request.decisions,
                FindingDecision(finding_id="finding-2", decision="accept"),
            ),
        }
    )
    proposal = _proposal(request).model_copy(
        update={"accepted_finding_ids": ("finding-1", "finding-2")}
    )

    with pytest.raises(RevisionValidationError, match="UNTARGETED_ACCEPTED_FINDING"):
        validate_revision_proposal(request, proposal)


def test_revision_rejects_multiple_changes_to_the_same_rule() -> None:
    request = _request()
    operation = _proposal(request).operations[0]
    proposal = _proposal(request).model_copy(
        update={"operations": (operation, operation)}
    )

    with pytest.raises(RevisionValidationError, match="RULE_REVISED_MULTIPLE_TIMES"):
        validate_revision_proposal(request, proposal)


def test_revision_rejects_duplicate_deterministic_added_rule_ids() -> None:
    request = _request()
    operation = AddRuleOperation(
        rule_id="model-rule-id",
        rule=_rule_draft(),
        finding_ids=("finding-1",),
    )
    proposal = _proposal(request).model_copy(
        update={"operations": (operation, operation.model_copy())}
    )

    with pytest.raises(RevisionValidationError, match="DUPLICATE_RULE_ID"):
        validate_revision_proposal(request, proposal)


def test_revision_prompt_contains_only_visible_eligible_evidence() -> None:
    request = _request()

    prompt = build_revision_prompt(request)

    assert "finding-1" in prompt.payload_json
    assert "unverified" in prompt.system_instructions.lower()
    payload = json.loads(prompt.payload_json)
    assert "assertions" not in payload["visible_scenarios"][0]


def test_revision_prompt_excludes_real_holdout_facts_and_gold_answers() -> None:
    request = _request()
    gold_token = "gold-label-private-token"
    holdout = make_scenario(
        index=1,
        origins=frozenset({"gold"}),
        facts=request.suite.scenarios[0].facts.model_copy(
            update={"amount_minor": 987654}
        ),
        assertions=(
            Assertion(
                assertion_id="gold-private-assertion",
                target_kind="effect_value",
                dimension="claim_cap_minor",
                operator="lte",
                expected_value=1234,
                origin="gold",
                gold_label_id=gold_token,
            ),
        ),
        partition="holdout",
    )
    suite = make_scenario_suite(
        scenarios=(request.suite.scenarios[0], holdout),
        document_sha256=request.document_sha256,
        policy_contract_sha256=request.policy_contract_sha256,
        rule_set_sha256=request.rule_set_sha256,
    )
    mixed = request.model_copy(
        update={
            "suite": suite,
            "suite_sha256": canonical_sha256(complete_payload_projection(suite)),
        }
    )

    prompt = build_revision_prompt(mixed)

    assert gold_token not in prompt.payload_json
    assert "987654" not in prompt.payload_json
    assert {
        item["scenario_id"]
        for item in json.loads(prompt.payload_json)["visible_scenarios"]
    } == {"scenario-0"}


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
            "decisions": (FindingDecision(finding_id="finding-1", decision="reject"),)
        }
    )

    with pytest.raises(RevisionValidationError, match="NO_ACCEPTED_FINDINGS"):
        build_revision_prompt(request)


@pytest.mark.asyncio
async def test_llm_revision_planner_uses_restricted_payload_and_returns_proposal() -> (
    None
):
    request = _request()
    llm = ScriptedLLMClient(
        (LLMResponse(output=_proposal(request).model_dump(mode="json")),)
    )

    result = await LLMRevisionPlanner(llm).propose(request)

    assert result.proposal_id.startswith("proposal-")
    assert result.draft_policy_wording.startswith("[AI-GENERATED, UNVERIFIED]")
    assert llm.requests[0].operation == "revision_proposal"
    sent = json.loads(llm.requests[0].untrusted_payload_json)
    assert "assertions" not in sent["visible_scenarios"][0]
    assert "holdout" not in llm.requests[0].untrusted_payload_json


@pytest.mark.asyncio
async def test_llm_revision_planner_repairs_schema_once_without_sending_output() -> (
    None
):
    request = _request()
    secret = "GOLD-ANSWER-secret"
    llm = ScriptedLLMClient(
        (
            LLMResponse(output={"invalid": secret}),
            LLMResponse(output=_proposal(request).model_dump(mode="json")),
        )
    )

    result = await LLMRevisionPlanner(llm).propose(request)

    assert result.proposal_id.startswith("proposal-")
    assert len(llm.requests) == 2
    assert secret not in llm.requests[1].system_instructions
    assert secret not in llm.requests[1].untrusted_payload_json
