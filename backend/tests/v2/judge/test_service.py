import asyncio
import json
from copy import deepcopy

import pytest

from app.v2.judge.service import JudgeAgentService
from app.v2.judge_contracts import judge_request_fingerprint, validate_judge_result
from app.v2.judge_protocols import JudgeService

APPROVED = {
    "english": True,
    "claims_grounded": True,
    "metric_results_preserved": True,
    "interaction_claims_grounded": True,
    "limitations_preserved": True,
    "provenance_preserved": True,
    "issues": [],
}


class FakeModel:
    execution_mode = "fixture"

    def __init__(self, *responses):
        self.responses = iter(responses)
        self.calls = []
        self.citation_calls = []

    async def complete(self, **kwargs):
        # These legacy tests isolate draft/global-review behavior. Dedicated
        # citation-scope tests exercise acceptance, rejection and repair.
        if "citation_check" in kwargs["payload"]:
            self.citation_calls.append(deepcopy(kwargs))
            return json.dumps({"supported": True, "problem": ""})
        self.calls.append(deepcopy(kwargs))
        response = next(self.responses)
        if isinstance(response, BaseException):
            raise response
        return response if isinstance(response, str) else json.dumps(response)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "kind,status",
    [("complete", "completed"), ("partial", "partial"), ("unscored", "partial")],
)
async def test_examples_return_bound_cited_advice_without_mutating_metrics(
    examples, drafts, kind, status
):
    request, _ = examples[kind]
    before = request.model_dump_json()
    model = FakeModel(drafts[kind], APPROVED)
    service = JudgeAgentService(model)
    assert isinstance(service, JudgeService)
    result = await service.run(request)
    validate_judge_result(request, result)
    assert result.status == status
    assert result.execution_mode == "fixture"
    assert result.request_fingerprint == judge_request_fingerprint(request)
    assert result.next_steps and not result.errors
    assert request.model_dump_json() == before
    assert "passed" not in result.model_dump()
    assert len(model.calls) == (2 if request.metric.review.status == "ready" else 0)


@pytest.mark.asyncio
async def test_malformed_response_gets_one_bounded_repair(examples, drafts):
    model = FakeModel("not JSON", drafts["complete"], APPROVED)
    result = await JudgeAgentService(model).run(examples["complete"][0])
    assert result.status == "completed" and len(model.calls) == 3
    assert model.calls[1]["payload"]["repair_codes"] == ["invalid_output"]


@pytest.mark.asyncio
async def test_unknown_citation_is_rejected_and_failure_has_no_findings(
    examples, drafts
):
    draft = deepcopy(drafts["complete"])
    draft["cons"][0]["citations"][0]["id"] = "made-up-case"
    model = FakeModel(draft, draft)
    request = examples["complete"][0]
    result = await JudgeAgentService(model).run(request)
    validate_judge_result(request, result)
    assert (
        result.status == "failed" and result.recommendation == "insufficient_evidence"
    )
    assert not result.pros and not result.cons and not result.next_steps
    assert result.errors and len(model.calls) == 2


@pytest.mark.asyncio
async def test_resolving_citation_with_false_claim_is_rejected_semantically(
    examples, drafts
):
    draft = deepcopy(drafts["complete"])
    draft["cons"][0]["text"] = "The cited case passed and proves the policy is safe."
    rejection = APPROVED | {
        "metric_results_preserved": False,
        "issues": ["metric_contradiction"],
    }
    model = FakeModel(draft, rejection, draft, rejection)
    result = await JudgeAgentService(model).run(examples["complete"][0])
    assert result.status == "failed" and len(model.calls) == 4
    assert "metric_contradiction" in result.errors[0]


@pytest.mark.asyncio
async def test_repair_receives_previous_draft_and_specific_private_feedback(
    examples, drafts
):
    feedback = [
        {
            "field": "cons",
            "item_index": 0,
            "problem": "The cited case failed; this finding incorrectly calls it a pass.",
        }
    ]
    review = APPROVED | {
        "metric_results_preserved": False,
        "issues": ["metric_contradiction"],
        "feedback": feedback,
    }
    model = FakeModel(drafts["complete"], review, drafts["complete"], APPROVED)
    result = await JudgeAgentService(model).run(examples["complete"][0])
    assert result.status == "completed" and len(model.calls) == 4
    assert model.calls[2]["payload"]["repair_feedback"] == feedback
    assert (
        model.calls[2]["payload"]["previous_draft"]
        == model.calls[1]["payload"]["draft"]
    )
    assert "feedback" not in result.model_dump()


@pytest.mark.asyncio
async def test_two_repairs_can_recover_format_then_grounding_failure(examples, drafts):
    rejection = APPROVED | {"claims_grounded": False, "issues": ["unsupported_claim"]}
    model = FakeModel(
        "invalid JSON", drafts["complete"], rejection, drafts["complete"], APPROVED
    )
    result = await JudgeAgentService(model, max_repairs=2).run(examples["complete"][0])
    assert result.status == "completed" and len(model.calls) == 5
    assert model.calls[3]["payload"]["repair_codes"] == ["unsupported_claim"]


@pytest.mark.asyncio
async def test_provider_failure_is_sanitized_and_never_substitutes_fixtures(examples):
    model = FakeModel(RuntimeError("秘密 api_key=secret"))
    result = await JudgeAgentService(model).run(examples["complete"][0])
    assert result.status == "failed"
    assert (
        "秘密" not in result.model_dump_json()
        and "secret" not in result.model_dump_json()
    )
    assert len(model.calls) == 1


@pytest.mark.asyncio
async def test_timeout_bounds_entire_call(examples):
    class SlowModel(FakeModel):
        async def complete(self, **kwargs):
            await asyncio.sleep(60)

    result = await JudgeAgentService(SlowModel(), timeout_seconds=0.01).run(
        examples["complete"][0]
    )
    assert result.status == "failed" and result.errors[0].startswith("judge_timeout:")


@pytest.mark.asyncio
async def test_caller_cancellation_propagates_to_core(examples):
    entered = asyncio.Event()

    class SlowModel(FakeModel):
        async def complete(self, **kwargs):
            entered.set()
            await asyncio.sleep(60)

    task = asyncio.create_task(
        JudgeAgentService(SlowModel()).run(examples["complete"][0])
    )
    await entered.wait()
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task


@pytest.mark.asyncio
async def test_tampered_nested_request_is_revalidated_before_model_call(examples):
    request = examples["complete"][0]
    tampered = request.model_copy(
        update={"metric": request.metric.model_copy(update={"passed": 999})}
    )
    model = FakeModel()
    with pytest.raises(ValueError):
        await JudgeAgentService(model).run(tampered)
    assert not model.calls
