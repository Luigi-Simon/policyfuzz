from types import SimpleNamespace

import httpx
import openai
import pytest

from app.core.config import Settings
from app.core.errors import LLMConfigurationError, LLMTransportError
from app.core.llm_openai import OpenAILLMClient
from app.domain.models import GenerationConfig, GenerationUsage, LLMRequest


def request(**changes: object) -> LLMRequest:
    values = {
        "operation": "policy_extraction",
        "system_instructions": "trusted system canary",
        "untrusted_payload_json": '{"policy":"untrusted payload canary"}',
        "response_schema": {
            "type": "object",
            "properties": {"rules": {"type": "array", "default": []}},
        },
        "response_schema_name": "policy_extraction_v1",
        "generation_config": GenerationConfig(
            temperature_milli=250,
            top_p_percent=75,
            max_output_tokens=123,
            seed=42,
        ),
    }
    return LLMRequest(**(values | changes))


def completion(
    *,
    content: str | None = '{"rules":[]}',
    finish_reason: str = "stop",
    refusal: str | None = None,
    tool_calls: object = None,
    usage: object = None,
) -> object:
    if usage is None:
        usage = SimpleNamespace(prompt_tokens=11, completion_tokens=7)
    return SimpleNamespace(
        choices=[
            SimpleNamespace(
                finish_reason=finish_reason,
                message=SimpleNamespace(
                    content=content, refusal=refusal, tool_calls=tool_calls
                ),
            )
        ],
        usage=usage,
    )


class FakeCompletions:
    def __init__(self, outcome: object) -> None:
        self.outcome = outcome
        self.calls: list[dict[str, object]] = []

    async def create(self, **kwargs: object) -> object:
        self.calls.append(kwargs)
        if isinstance(self.outcome, BaseException):
            raise self.outcome
        return self.outcome


class FakeSDK:
    def __init__(self, outcome: object) -> None:
        self.completions = FakeCompletions(outcome)
        self.chat = SimpleNamespace(completions=self.completions)
        self.options: list[dict[str, object]] = []
        self.close_calls = 0

    def with_options(self, **kwargs: object) -> "FakeSDK":
        self.options.append(kwargs)
        return self

    async def close(self) -> None:
        self.close_calls += 1


@pytest.mark.asyncio
async def test_openai_adapter_sends_exact_safe_wire_contract_without_mutating_schema() -> (
    None
):
    sdk = FakeSDK(completion())
    original = request()
    schema_snapshot = original.model_copy(deep=True).response_schema
    client = OpenAILLMClient(
        model="synthetic-model", timeout_seconds=12.5, sdk_client=sdk
    )

    response = await client.complete_json(original)

    assert sdk.options == [{"max_retries": 0, "timeout": 12.5}]
    assert sdk.completions.calls == [
        {
            "model": "synthetic-model",
            "messages": [
                {"role": "system", "content": "trusted system canary"},
                {
                    "role": "user",
                    "content": "UNTRUSTED_JSON_INPUT:\n"
                    '{"policy":"untrusted payload canary"}',
                },
            ],
            "response_format": {
                "type": "json_schema",
                "json_schema": {
                    "name": "policy_extraction_v1",
                    "schema": schema_snapshot,
                    "strict": False,
                },
            },
            "max_completion_tokens": 123,
            "temperature": 0.25,
            "top_p": 0.75,
            "seed": 42,
            "stream": False,
            "store": False,
        }
    ]
    assert original.response_schema == schema_snapshot
    assert response.output == '{"rules":[]}'
    assert response.usage == GenerationUsage(input_tokens=11, output_tokens=7)


@pytest.mark.asyncio
async def test_openai_adapter_omits_seed_and_passes_malformed_stopped_content() -> None:
    sdk = FakeSDK(completion(content="{malformed"))
    config = GenerationConfig(seed=None)

    response = await OpenAILLMClient(
        model="synthetic-model", timeout_seconds=30, sdk_client=sdk
    ).complete_json(request(generation_config=config, repair_attempt=1))

    assert "seed" not in sdk.completions.calls[0]
    assert response.output == "{malformed"
    assert response.usage.repair_calls == 1


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("result", "code"),
    [
        (completion(refusal="private refusal"), "refusal"),
        (completion(finish_reason="content_filter"), "refusal"),
        (completion(finish_reason="length"), "invalid_response"),
        (
            completion(finish_reason="tool_calls", tool_calls=[object()]),
            "invalid_response",
        ),
        (completion(finish_reason="unknown"), "invalid_response"),
        (completion(content=None), "invalid_response"),
        (completion(content=""), "invalid_response"),
        (SimpleNamespace(choices=[], usage=None), "invalid_response"),
        (
            completion(usage=SimpleNamespace(prompt_tokens=-1, completion_tokens=1)),
            "invalid_response",
        ),
    ],
)
async def test_openai_adapter_maps_invalid_provider_responses_safely(
    result: object, code: str
) -> None:
    sdk = FakeSDK(result)

    with pytest.raises(LLMTransportError) as raised:
        await OpenAILLMClient(
            model="synthetic-model", timeout_seconds=30, sdk_client=sdk
        ).complete_json(request())

    assert raised.value.error.code == code
    assert raised.value.error.transport_retries == 0
    assert "private refusal" not in str(raised.value)


def sdk_error(kind: str, canary: str) -> Exception:
    sdk_request = httpx.Request("POST", "https://provider.invalid")
    response = httpx.Response(400, request=sdk_request)
    if kind == "timeout":
        return openai.APITimeoutError(request=sdk_request)
    if kind == "connection":
        return openai.APIConnectionError(message=canary, request=sdk_request)
    cls = getattr(openai, kind)
    if cls is openai.APIResponseValidationError:
        return cls(response=response, body={"private": canary}, message=canary)
    return cls(canary, response=response, body={"private": canary})


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("sdk_kind", "code"),
    [
        ("timeout", "timeout"),
        ("RateLimitError", "rate_limit"),
        ("AuthenticationError", "authentication"),
        ("PermissionDeniedError", "authentication"),
        ("BadRequestError", "invalid_request"),
        ("NotFoundError", "invalid_request"),
        ("UnprocessableEntityError", "invalid_request"),
        ("connection", "unavailable"),
        ("InternalServerError", "unavailable"),
        ("APIResponseValidationError", "invalid_response"),
    ],
)
async def test_openai_adapter_maps_sdk_errors_without_leaking_provider_details(
    sdk_kind: str, code: str
) -> None:
    canary = "private-provider-error-canary"
    sdk = FakeSDK(sdk_error(sdk_kind, canary))

    with pytest.raises(LLMTransportError) as raised:
        await OpenAILLMClient(
            model="synthetic-model", timeout_seconds=30, sdk_client=sdk
        ).complete_json(request())

    assert raised.value.error.code == code
    assert canary not in str(raised.value)
    assert raised.value.__cause__ is None
    assert raised.value.__suppress_context__ is True


@pytest.mark.asyncio
async def test_openai_adapter_maps_unknown_exception_and_preserves_cancellation() -> (
    None
):
    client = OpenAILLMClient(
        model="synthetic-model",
        timeout_seconds=30,
        sdk_client=FakeSDK(RuntimeError("private unknown provider error")),
    )
    with pytest.raises(LLMTransportError) as raised:
        await client.complete_json(request())
    assert raised.value.error.code == "unavailable"
    assert "private" not in str(raised.value)

    cancelled = OpenAILLMClient(
        model="synthetic-model",
        timeout_seconds=30,
        sdk_client=FakeSDK(__import__("asyncio").CancelledError()),
    )
    with pytest.raises(__import__("asyncio").CancelledError):
        await cancelled.complete_json(request())


def test_openai_from_settings_requires_nonblank_credentials() -> None:
    with pytest.raises(LLMConfigurationError):
        OpenAILLMClient.from_settings(Settings())
    with pytest.raises(LLMConfigurationError):
        OpenAILLMClient.from_settings(Settings(llm_model="model"))


def test_openai_from_settings_constructs_owned_sdk_with_secret_and_safe_options(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: list[dict[str, object]] = []
    sdk = FakeSDK(completion())

    def fake_openai(**kwargs: object) -> FakeSDK:
        captured.append(kwargs)
        return sdk

    monkeypatch.setattr("app.core.llm_openai.openai.AsyncOpenAI", fake_openai)
    settings = Settings(
        app_mode="live",
        llm_model="synthetic-model",
        openai_api_key="synthetic-secret",
        llm_timeout_seconds=9,
    )

    client = OpenAILLMClient.from_settings(settings)

    assert captured == [
        {"api_key": "synthetic-secret", "max_retries": 0, "timeout": 9.0}
    ]
    assert "synthetic-secret" not in repr(client)


@pytest.mark.asyncio
async def test_openai_adapter_only_closes_owned_client(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    borrowed = FakeSDK(completion())
    borrowed_client = OpenAILLMClient(
        model="synthetic-model", timeout_seconds=30, sdk_client=borrowed
    )
    await borrowed_client.aclose()
    await borrowed_client.close()
    assert borrowed.close_calls == 0

    owned = FakeSDK(completion())
    monkeypatch.setattr("app.core.llm_openai.openai.AsyncOpenAI", lambda **_: owned)
    owned_client = OpenAILLMClient.from_settings(
        Settings(llm_model="synthetic-model", openai_api_key="synthetic-secret")
    )
    await owned_client.close()
    await owned_client.aclose()
    assert owned.close_calls == 1
