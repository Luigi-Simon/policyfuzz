"""A claim cannot borrow support from an uncited part of the conversation."""

import json
from copy import deepcopy

import pytest

from app.v2.judge.service import JudgeAgentService
from app.v2.judge_contracts import JudgeRequest

from .test_service import APPROVED, FakeModel


@pytest.mark.asyncio
async def test_uncited_feedback_elsewhere_cannot_ground_interaction(examples, drafts):
    data = examples["complete"][0].model_dump(mode="json")
    sandbox = data["sandbox"]
    parent = sandbox["messages"][0]
    parent["content"] = "How would a voluntary opt-out work?"
    reply = deepcopy(parent)
    reply.update(
        message_id="scope-reply",
        sequence=len(sandbox["messages"]) + 1,
        persona_id=next(
            p["persona_id"]
            for p in sandbox["personas"]
            if p["persona_id"] != parent["persona_id"]
        ),
        content="Could shift workers use a flexible schedule?",
        reply_to_message_ids=[parent["message_id"]],
    )
    unrelated = deepcopy(reply)
    unrelated.update(
        message_id="uncited-feedback",
        sequence=reply["sequence"] + 1,
        content="UNRELATED-FEEDBACK-SENTINEL: I propose monthly feedback surveys.",
        reply_to_message_ids=[],
    )
    sandbox["messages"].extend([reply, unrelated])
    sandbox["observed_stakeholder_count"] = len(
        {m["persona_id"] for m in sandbox["messages"]}
    )
    request = JudgeRequest.model_validate(data)
    draft = deepcopy(drafts["complete"])
    draft["key_interactions"] = [
        {
            "text": "The opt-out question led to multiple proposals for flexible schedules and monthly feedback surveys.",
            "citations": [
                {"kind": "sandbox_message", "id": mid, "case_id": None}
                for mid in [parent["message_id"], reply["message_id"]]
            ],
        }
    ]

    class Client:
        execution_mode = "fixture"

        def __init__(self):
            self.scoped = []

        async def complete(self, **kwargs):
            payload = kwargs["payload"]
            if "citation_check" in payload:
                self.scoped.append(payload)
                assert "UNRELATED-FEEDBACK-SENTINEL" not in json.dumps(payload)
                if payload["citation_check"]["field"] == "key_interactions":
                    return json.dumps(
                        {
                            "supported": False,
                            "problem": "The cited pair contains one flexibility proposal and no feedback proposal.",
                        }
                    )
                return json.dumps({"supported": True, "problem": ""})
            return json.dumps(APPROVED if "draft" in payload else draft)

    client = Client()
    result = await JudgeAgentService(client, max_repairs=0).run(request)
    assert client.scoped
    assert result.status == "partial" and not result.key_interactions
    assert result.recommendation == "insufficient_evidence" and not result.errors
    assert result.pros and result.cons and result.next_steps
    assert any(
        "1 generated finding" in note and "omitted" in note
        for note in result.limitations
    )


@pytest.mark.asyncio
async def test_citation_failure_repairs_the_finding_and_reuses_approved_checks(
    examples, drafts
):
    original = deepcopy(drafts["complete"])
    repaired = deepcopy(original)
    repaired["cons"][0]["text"] += (
        " Review the cited trace before changing the mechanism."
    )

    class Client(FakeModel):
        def __init__(self, *responses):
            super().__init__(*responses)
            self.checked = []

        async def complete(self, **kwargs):
            repair = kwargs["payload"].get("citation_repair")
            if repair:
                assert "request" not in kwargs["payload"]
                assert repair["field"] == "cons"
                return json.dumps({"text": repaired["cons"][0]["text"]})
            check = kwargs["payload"].get("citation_check")
            if check:
                self.checked.append(check)
                bad = (
                    check["field"] == "cons"
                    and "Review the cited trace" not in check["finding"]["text"]
                )
                return json.dumps(
                    {
                        "supported": not bad,
                        "problem": "Unsupported compound clause." if bad else "",
                    }
                )
            return await super().complete(**kwargs)

    client = Client(original, APPROVED, APPROVED)
    result = await JudgeAgentService(client).run(examples["complete"][0])
    assert result.status == "completed"
    assert client.calls[2]["payload"]["repair_codes"] == ["citation_not_supported"]
    assert client.calls[2]["payload"]["repair_feedback"][0]["field"] == "cons"
    assert len([c for c in client.checked if c["field"] == "cons"]) == 2
    assert len([c for c in client.checked if c["field"] == "pros"]) == len(
        original["pros"]
    )


@pytest.mark.asyncio
async def test_citation_checks_share_deadline_and_cancel_pending_calls(
    examples, drafts
):
    import asyncio

    class Client(FakeModel):
        active = 0

        async def complete(self, **kwargs):
            if "citation_check" in kwargs["payload"]:
                self.active += 1
                try:
                    await asyncio.sleep(5)
                finally:
                    self.active -= 1
            return await super().complete(**kwargs)

    client = Client(drafts["complete"], APPROVED)
    result = await JudgeAgentService(client, timeout_seconds=0.05).run(
        examples["complete"][0]
    )
    assert result.status == "failed" and "judge_timeout" in result.errors[0]
    assert client.active == 0


@pytest.mark.asyncio
async def test_no_unsupported_prose_survives_when_all_citation_checks_reject(
    examples, drafts
):
    class Client(FakeModel):
        async def complete(self, **kwargs):
            if "citation_check" in kwargs["payload"]:
                return json.dumps(
                    {
                        "supported": False,
                        "problem": "The cited material does not support this finding.",
                    }
                )
            return await super().complete(**kwargs)

    draft = deepcopy(drafts["complete"])
    draft["summary"] = "Rejected-report-summary-sentinel."
    result = await JudgeAgentService(Client(draft, APPROVED), max_repairs=0).run(
        examples["complete"][0]
    )
    assert (
        result.status == "partial"
        and not result.pros
        and not result.cons
        and not result.key_interactions
    )
    assert result.recommendation == "insufficient_evidence"
    assert "Rejected-report-summary-sentinel" not in result.model_dump_json()
    assert result.next_steps and not result.next_steps[0].citations


@pytest.mark.asyncio
async def test_repair_instructions_cannot_be_published_as_next_steps(examples, drafts):
    draft = deepcopy(drafts["complete"])
    draft["next_steps"][0]["action"] = "Revise finding to match cited evidence."
    result = await JudgeAgentService(FakeModel(draft, APPROVED), max_repairs=0).run(
        examples["complete"][0]
    )
    assert result.status == "failed" and not result.next_steps
