import asyncio

import pytest

from app.core.errors import LLMTransportError
from app.core.fakes import ScriptedLLMClient
from app.core.llm import RetryingLLMClient
from app.domain.models import GenerationUsage, LLMError, LLMRequest, LLMResponse


def request(**changes: object) -> LLMRequest:
    values = {
        "operation": "policy_extraction",
        "system_instructions": "trusted instructions",
        "untrusted_payload_json": '{"policy":"synthetic"}',
        "response_schema": {"type": "object", "properties": {}},
        "response_schema_name": "policy_extraction_v1",
    }
    return LLMRequest(**(values | changes))


def failure(code: str, *, operation: str = "policy_extraction") -> LLMTransportError:
    return LLMTransportError(LLMError(code=code, operation=operation))


@pytest.mark.asyncio
async def test_scripted_client_consumes_ordered_outcomes_and_records_attempts() -> None:
    first = LLMResponse(output={"value": 1})
    client = ScriptedLLMClient([first])
    client.queue(LLMResponse(output={"value": 2}))

    assert (await client.complete_json(request())).output == {"value": 1}
    assert (await client.complete_json(request())).output == {"value": 2}
    assert len(client.requests) == 2


@pytest.mark.asyncio
async def test_scripted_client_defensively_copies_fixtures_requests_and_responses() -> (
    None
):
    schema = {"type": "object", "properties": {"value": {"type": "integer"}}}
    output = {"value": 1}
    original_request = request(response_schema=schema)
    original_response = LLMResponse(output=output)
    client = ScriptedLLMClient([original_response])
    original_response.output["value"] = 99

    returned = await client.complete_json(original_request)
    original_request.response_schema["properties"]["late"] = {"type": "boolean"}
    assert returned.output == {"value": 1}
    returned.output["value"] = 5
    assert client.requests[0].response_schema == {
        "type": "object",
        "properties": {"value": {"type": "integer"}},
    }


@pytest.mark.asyncio
async def test_scripted_client_raises_typed_exhaustion_after_recording_request() -> (
    None
):
    client = ScriptedLLMClient()

    with pytest.raises(LLMTransportError) as raised:
        await client.complete_json(request(operation="revision_proposal"))

    assert raised.value.error == LLMError(
        code="script_exhausted", operation="revision_proposal"
    )
    assert len(client.requests) == 1


@pytest.mark.asyncio
async def test_scripted_client_rebinds_queued_error_to_request_operation() -> None:
    client = ScriptedLLMClient([failure("timeout", operation="policy_extraction")])

    with pytest.raises(LLMTransportError) as raised:
        await client.complete_json(request(operation="revision_proposal"))

    assert raised.value.error.operation == "revision_proposal"


@pytest.mark.asyncio
async def test_retry_client_uses_exact_three_attempts_and_one_two_second_delays() -> (
    None
):
    delegate = ScriptedLLMClient(
        [failure("timeout"), failure("rate_limit"), LLMResponse(output={"ok": True})]
    )
    delays: list[float] = []

    async def record_sleep(delay: float) -> None:
        delays.append(delay)

    response = await RetryingLLMClient(delegate, sleep=record_sleep).complete_json(
        request()
    )

    assert response.output == {"ok": True}
    assert response.usage.transport_retries == 2
    assert len(delegate.requests) == 3
    assert delays == [1.0, 2.0]
    assert [item.model_dump() for item in delegate.requests] == [
        delegate.requests[0].model_dump()
    ] * 3
    assert len({id(item.response_schema) for item in delegate.requests}) == 3


@pytest.mark.asyncio
async def test_retry_client_terminal_timeout_reports_two_retries_and_no_extra_sleep() -> (
    None
):
    delegate = ScriptedLLMClient([failure("timeout")] * 3)
    delays: list[float] = []

    async def record_sleep(delay: float) -> None:
        delays.append(delay)

    with pytest.raises(LLMTransportError) as raised:
        await RetryingLLMClient(delegate, sleep=record_sleep).complete_json(request())

    assert raised.value.error.transport_retries == 2
    assert len(delegate.requests) == 3
    assert delays == [1.0, 2.0]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "code",
    [
        "authentication",
        "invalid_request",
        "unavailable",
        "invalid_response",
        "refusal",
        "script_exhausted",
    ],
)
async def test_retry_client_does_not_retry_nonretryable_typed_errors(code: str) -> None:
    delegate = ScriptedLLMClient([failure(code)])
    delays: list[float] = []

    async def record_sleep(delay: float) -> None:
        delays.append(delay)

    with pytest.raises(LLMTransportError) as raised:
        await RetryingLLMClient(delegate, sleep=record_sleep).complete_json(request())

    assert raised.value.error.code == code
    assert raised.value.error.transport_retries == 0
    assert len(delegate.requests) == 1
    assert delays == []


@pytest.mark.asyncio
async def test_retry_client_preserves_usage_and_resets_budget_for_each_call() -> None:
    delegate = ScriptedLLMClient(
        [
            failure("timeout"),
            LLMResponse(
                output={},
                usage=GenerationUsage(input_tokens=3, output_tokens=4, repair_calls=1),
            ),
            failure("rate_limit"),
            LLMResponse(output={}),
        ]
    )
    client = RetryingLLMClient(delegate, sleep=lambda _: asyncio.sleep(0))

    repaired = await client.complete_json(request(repair_attempt=1))
    initial = await client.complete_json(request())

    assert repaired.usage == GenerationUsage(
        input_tokens=3, output_tokens=4, repair_calls=1, transport_retries=1
    )
    assert initial.usage.transport_retries == 1


@pytest.mark.asyncio
async def test_retry_client_propagates_arbitrary_exception_and_cancellation() -> None:
    class RaisingClient:
        def __init__(self, error: BaseException) -> None:
            self.error = error
            self.attempts = 0

        async def complete_json(self, request: LLMRequest) -> LLMResponse:
            self.attempts += 1
            raise self.error

    runtime_delegate = RaisingClient(RuntimeError("programming failure"))
    with pytest.raises(RuntimeError, match="programming failure"):
        await RetryingLLMClient(runtime_delegate).complete_json(request())
    cancellation_delegate = RaisingClient(asyncio.CancelledError())
    with pytest.raises(asyncio.CancelledError):
        await RetryingLLMClient(cancellation_delegate).complete_json(request())
    assert runtime_delegate.attempts == cancellation_delegate.attempts == 1


def test_retry_client_rejects_direct_nested_wrapper() -> None:
    inner = RetryingLLMClient(ScriptedLLMClient())

    with pytest.raises(TypeError, match="cannot be nested"):
        RetryingLLMClient(inner)
