import asyncio
from copy import deepcopy

import pytest

from app.v2.contracts import (
    SandboxRequest,
    make_example_request,
    public_sandbox_result,
    request_fingerprint,
    validate_sandbox_result,
)
from app.v2.sandbox.personas import SeedPersona
from app.v2.sandbox.service import MiroFishSandboxService, UnsupportedPolicyTitle
from app.v2.sandbox.translation import EnglishText


class FakeLanguage:
    def __init__(self):
        self.seeds = []
        self.fail_translation = False

    async def personas(self, request, count):
        self.seeds.append((request.personality_seed, count))
        return tuple(
            SeedPersona(
                display_name=f"Participant {i + 1}",
                description=f"Practical rider shaped by {request.personality_seed}",
                opening_statement="How will the pilot affect late shifts?",
            )
            for i in range(count)
        )

    async def english(self, text):
        if "服务" in text:
            if self.fail_translation:
                raise TimeoutError()
            return EnglishText(
                text="Keep the service.", language="Chinese", translated=True
            )
        return EnglishText(text=text, language="English", translated=False)


class FakeMiroFish:
    max_agents = 50

    def __init__(self):
        self.jobs = {}
        self.prepares = self.starts = self.stops = 0
        self.state = "completed"
        self.rows = {
            "posts": [
                {"post_id": 1, "user_id": 0, "content": "Keep the service."},
                {"post_id": 2, "user_id": 1, "content": "Keep the service."},
            ],
            "comments": [
                {
                    "comment_id": 1,
                    "post_id": 2,
                    "user_id": 0,
                    "content": "Your point about late shifts makes sense.",
                },
                {
                    "comment_id": 2,
                    "post_id": 1,
                    "user_id": 1,
                    "content": "I agree, with enough staff.",
                },
                {
                    "comment_id": 3,
                    "post_id": 1,
                    "user_id": 2,
                    "content": "What about accessibility?",
                },
            ],
            "actions": [],
        }

    async def lookup(self, fingerprint):
        return deepcopy(self.jobs.get(fingerprint))

    async def prepare(self, request, personas):
        self.prepares += 1
        fp = request_fingerprint(request)
        job = {
            "request_fingerprint": fp,
            "request": request.model_dump(mode="json"),
            "simulation_id": f"sim_{self.prepares:012x}",
            "status": "ready",
            "personas": [p.model_dump() for p in personas],
            "profiles_count": len(personas),
        }
        self.jobs[fp] = job
        return deepcopy(job)

    async def start(self, fingerprint):
        self.starts += 1
        self.jobs[fingerprint]["status"] = self.state

    async def status(self, fingerprint):
        return deepcopy(self.jobs[fingerprint])

    async def capture(self, simulation_id):
        return deepcopy(self.rows), []

    async def stop(self, fingerprint):
        self.stops += 1
        self.jobs[fingerprint]["status"] = "cancelled"


def changed(request, **updates):
    return SandboxRequest.model_validate(request.model_dump() | updates)


@pytest.mark.asyncio
async def test_exact_seed_count_and_real_reply_evidence():
    request = make_example_request()
    engine, language = FakeMiroFish(), FakeLanguage()
    service = MiroFishSandboxService(engine, language, poll_seconds=0.001)
    result = await service.run(request)
    validate_sandbox_result(request, result)
    assert result.status == "completed"
    assert result.execution_mode == "live"
    assert language.seeds == [(request.personality_seed, 3)]
    assert (
        result.requested_stakeholder_count,
        result.configured_stakeholder_count,
        result.observed_stakeholder_count,
    ) == (3, 3, 3)
    assert len(result.messages) == 5  # Equal text by distinct speakers is retained.
    assert result.messages[-1].reply_to_message_ids == (result.messages[0].message_id,)
    assert "original_records" not in public_sandbox_result(result)
    assert result.messages[0].recorded_at is None
    assert result.messages[0].round_number is None


@pytest.mark.asyncio
async def test_safe_retry_reuses_job_even_with_a_new_service():
    request = make_example_request()
    engine, language = FakeMiroFish(), FakeLanguage()
    first = await MiroFishSandboxService(engine, language).run(request)
    second = await MiroFishSandboxService(engine, language).run(request)
    assert engine.prepares == engine.starts == 1
    assert first.messages == second.messages
    assert len(language.seeds) == 1


@pytest.mark.asyncio
async def test_full_request_change_creates_new_version_bound_capture():
    engine, language = FakeMiroFish(), FakeLanguage()
    service = MiroFishSandboxService(engine, language)
    request = make_example_request()
    first = await service.run(request)
    second = await service.run(
        changed(request, personality_seed="Cautious night workers")
    )
    assert engine.prepares == 2
    assert first.request_fingerprint != second.request_fingerprint
    assert first.messages[0].message_id != second.messages[0].message_id


@pytest.mark.asyncio
async def test_unknown_speaker_duplicate_and_malformed_rows_are_partial():
    engine, language = FakeMiroFish(), FakeLanguage()
    engine.rows["posts"] += [
        deepcopy(engine.rows["posts"][0]),
        {"post_id": 7, "user_id": 100, "content": "Unknown"},
        {"content": "No source ID"},
        None,
    ]
    request = make_example_request()
    result = await MiroFishSandboxService(engine, language).run(request)
    validate_sandbox_result(request, result)
    assert result.status == "partial"
    assert len(result.messages) == 5
    assert any("unknown_speaker" in x for x in result.limitations)


@pytest.mark.asyncio
async def test_translation_failure_is_english_placeholder_and_internal_original():
    engine, language = FakeMiroFish(), FakeLanguage()
    language.fail_translation = True
    engine.rows["posts"][0]["content"] = "保留服务。"
    request = make_example_request()
    result = await MiroFishSandboxService(engine, language).run(request)
    validate_sandbox_result(request, result)
    assert result.status == "partial"
    assert result.messages[0].translation_status == "unavailable"
    assert "保留" in result.original_records[0].content
    assert "保留" not in str(public_sandbox_result(result))


@pytest.mark.asyncio
async def test_tampered_request_is_rejected_before_any_provider_call():
    engine, language = FakeMiroFish(), FakeLanguage()
    request = make_example_request().model_copy(update={"policy_text": "Changed"})
    with pytest.raises(ValueError):
        await MiroFishSandboxService(engine, language).run(request)
    assert engine.prepares == 0 and not language.seeds


@pytest.mark.asyncio
async def test_cancellation_stops_owned_job_and_returns_valid_evidence():
    engine, language = FakeMiroFish(), FakeLanguage()
    engine.state = "running"
    service = MiroFishSandboxService(engine, language, poll_seconds=0.001)
    request = make_example_request()
    task = asyncio.create_task(service.run(request))
    while not engine.starts:
        await asyncio.sleep(0)
    task.cancel()
    result = await task
    assert result.status == "cancelled"
    assert engine.stops == 1
    validate_sandbox_result(request, result)


@pytest.mark.asyncio
@pytest.mark.parametrize("count", [1, 2, 7, 50, 100])
async def test_count_is_independent_from_metric_budget_and_reports_cap(count):
    engine, language = FakeMiroFish(), FakeLanguage()
    request = changed(make_example_request(), stakeholder_count=count, test_budget=1)
    result = await MiroFishSandboxService(engine, language).run(request)
    validate_sandbox_result(request, result)
    assert language.seeds[0][1] == min(count, 50)
    assert result.configured_stakeholder_count == min(count, 50)
    assert result.requested_stakeholder_count == count
    if count == 100:
        assert result.status == "partial"
        assert any(n.startswith("population_cap:") for n in result.limitations)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "field,value",
    [
        ("request_fingerprint", "0" * 64),
        ("profiles_count", 900),
        ("simulation_id", None),
        ("personas", []),
    ],
)
async def test_unbound_or_malformed_jobs_never_start_or_supply_evidence(field, value):
    engine, language = FakeMiroFish(), FakeLanguage()
    request = make_example_request()
    people = await language.personas(request, 3)
    await engine.prepare(request, people)
    engine.jobs[request_fingerprint(request)][field] = value
    result = await MiroFishSandboxService(engine, language).run(request)
    validate_sandbox_result(request, result)
    assert result.status == "failed"
    assert engine.starts == 0 and not result.messages


@pytest.mark.asyncio
async def test_failed_empty_simulation_never_becomes_fixture():
    engine, language = FakeMiroFish(), FakeLanguage()
    engine.state, engine.rows = "failed", {}
    result = await MiroFishSandboxService(engine, language).run(make_example_request())
    assert result.status == "failed" and result.execution_mode == "live"
    assert result.errors and not result.messages


@pytest.mark.asyncio
async def test_simulation_timeout_retains_partial_evidence_and_stops():
    engine, language = FakeMiroFish(), FakeLanguage()
    engine.state = "running"
    request = changed(make_example_request(), timeout_seconds=1)
    result = await MiroFishSandboxService(engine, language, poll_seconds=0.01).run(
        request
    )
    assert result.status == "partial" and result.messages
    assert engine.stops == 1 and any(e.startswith("timeout:") for e in result.errors)
    validate_sandbox_result(request, result)


@pytest.mark.asyncio
async def test_stop_failure_is_explicit_and_sanitized():
    engine, language = FakeMiroFish(), FakeLanguage()
    engine.state = "running"

    async def stop(_):
        raise RuntimeError("秘密 token=secret")

    engine.stop = stop
    result = await MiroFishSandboxService(engine, language, poll_seconds=0.01).run(
        changed(make_example_request(), timeout_seconds=1)
    )
    assert any(e.startswith("stop_unacknowledged:") for e in result.errors)
    assert "secret" not in str(public_sandbox_result(result))


@pytest.mark.asyncio
async def test_roster_provider_failure_before_prepare_does_not_cancel_future_retry():
    engine, language = FakeMiroFish(), FakeLanguage()

    async def failed(*_):
        raise RuntimeError("provider transient error")

    language.personas = failed
    result = await MiroFishSandboxService(engine, language).run(make_example_request())
    assert result.status == "failed"
    assert engine.prepares == engine.stops == 0


@pytest.mark.asyncio
async def test_successful_translation_preserves_identity_and_archive():
    engine, language = FakeMiroFish(), FakeLanguage()
    engine.rows["posts"][0]["content"] = "保留服务。"
    before = deepcopy(engine.rows)
    request = make_example_request()
    service = MiroFishSandboxService(engine, language)
    result = await service.run(request)
    assert result.messages[0].translation_status == "translated"
    assert engine.rows == before
    assert "保留服务。" in service.internal_capture(request_fingerprint(request))
    assert result.original_records[0].record_id == result.messages[0].message_id
    assert (
        result.original_records[0].reply_to_record_ids
        == result.messages[0].reply_to_message_ids
    )
    validate_sandbox_result(request, result)


@pytest.mark.asyncio
async def test_hanging_translation_returns_placeholders_without_losing_other_records():
    engine, language = FakeMiroFish(), FakeLanguage()
    original = language.english

    async def translate(text):
        if text == "Keep the service.":
            await asyncio.sleep(60)
        return await original(text)

    language.english = translate
    result = await MiroFishSandboxService(
        engine, language, translation_seconds=0.01
    ).run(make_example_request())
    assert len(result.messages) == 5
    assert sum(m.translation_status == "unavailable" for m in result.messages) == 2


@pytest.mark.asyncio
async def test_cancelled_with_untranslated_evidence_preserves_reason_under_shared_partial_rule():
    engine, language = FakeMiroFish(), FakeLanguage()
    engine.state, language.fail_translation = "stopped", True
    engine.rows["posts"][0]["content"] = "保留服务。"
    result = await MiroFishSandboxService(engine, language).run(make_example_request())
    assert result.status == "partial"
    assert any(n.startswith("simulation_cancelled:") for n in result.limitations)


@pytest.mark.asyncio
async def test_latin_non_english_title_is_rejected_without_changing_identity():
    engine, language = FakeMiroFish(), FakeLanguage()

    async def french_title(_):
        return EnglishText(text="Transport policy", language="French", translated=True)

    language.english = french_title
    request = changed(make_example_request(), policy_title="Politique de transport")
    with pytest.raises(UnsupportedPolicyTitle):
        await MiroFishSandboxService(engine, language).run(request)
    assert engine.prepares == 0


@pytest.mark.asyncio
async def test_non_latin_title_is_rejected_without_provider_use():
    engine, language = FakeMiroFish(), FakeLanguage()
    request = changed(make_example_request(), policy_title="公共交通政策")
    with pytest.raises(UnsupportedPolicyTitle):
        await MiroFishSandboxService(engine, language).run(request)
    assert not language.seeds and engine.prepares == 0


@pytest.mark.asyncio
async def test_total_translation_deadline_retains_already_projected_messages():
    engine, language = FakeMiroFish(), FakeLanguage()
    original = language.english

    async def translate(text):
        if text == "Keep the service.":
            await asyncio.sleep(60)
        return await original(text)

    language.english = translate
    result = await MiroFishSandboxService(engine, language).run(
        changed(make_example_request(), timeout_seconds=1)
    )
    assert len(result.messages) == 5
    assert sum(m.translation_status == "unavailable" for m in result.messages) == 2
    assert len(result.original_records) == 5
