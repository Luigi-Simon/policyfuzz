import asyncio
import json

import pytest
from botocore.exceptions import (
    ClientError,
    ConnectTimeoutError,
    EndpointConnectionError,
)

from app.core.config import Settings
from app.core.errors import LLMConfigurationError, LLMTransportError
from app.core.llm_bedrock import BedrockLLMClient, bedrock_tool_schema
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


def response(
    *,
    output: object | None = None,
    stop_reason: str = "tool_use",
    usage: object | None = None,
    content: object | None = None,
) -> dict[str, object]:
    if usage is None:
        usage = {"inputTokens": 11, "outputTokens": 7, "totalTokens": 18}
    if output is None:
        output = {"rules": []}
    if content is None:
        content = [
            {
                "toolUse": {
                    "toolUseId": "synthetic-tool-use",
                    "name": "policy_extraction_v1",
                    "input": output,
                }
            }
        ]
    return {
        "output": {"message": {"role": "assistant", "content": content}},
        "stopReason": stop_reason,
        "usage": usage,
    }


class FakeBedrockSDK:
    def __init__(self, outcome: object) -> None:
        self.outcome = outcome
        self.calls: list[dict[str, object]] = []
        self.close_calls = 0

    def converse(self, **kwargs: object) -> object:
        self.calls.append(kwargs)
        if isinstance(self.outcome, BaseException):
            raise self.outcome
        return self.outcome

    def close(self) -> None:
        self.close_calls += 1


@pytest.mark.asyncio
async def test_bedrock_adapter_sends_safe_converse_contract_and_maps_response() -> None:
    sdk = FakeBedrockSDK(response())
    original = request()
    schema_snapshot = original.model_copy(deep=True).response_schema
    client = BedrockLLMClient(
        model="amazon.synthetic-v1:0", timeout_seconds=12.5, sdk_client=sdk
    )

    result = await client.complete_json(original)

    assert len(sdk.calls) == 1
    call = sdk.calls[0]
    assert call["modelId"] == "amazon.synthetic-v1:0"
    assert call["messages"] == [
        {
            "role": "user",
            "content": [
                {"text": 'UNTRUSTED_JSON_INPUT:\n{"policy":"untrusted payload canary"}'}
            ],
        }
    ]
    assert call["inferenceConfig"] == {
        "maxTokens": 123,
        "temperature": 0,
    }
    system_text = call["system"][0]["text"]
    assert system_text.startswith("trusted system canary\n\n")
    assert "policy_extraction_v1" in system_text
    assert "untrusted payload canary" not in system_text
    assert call["toolConfig"] == {
        "tools": [
            {
                "toolSpec": {
                    "name": "policy_extraction_v1",
                    "description": "Return the requested PolicyFuzz structured result.",
                    "inputSchema": {
                        "json": {
                            "type": "object",
                            "properties": {"rules": {"type": "array"}},
                            "required": [],
                        }
                    },
                }
            }
        ],
        "toolChoice": {"tool": {"name": "policy_extraction_v1"}},
    }
    assert original.response_schema == schema_snapshot
    assert result.output == {"rules": []}
    assert result.usage == GenerationUsage(input_tokens=11, output_tokens=7)


def test_bedrock_tool_schema_inlines_local_refs_without_mutating_source() -> None:
    source = {
        "$defs": {
            "Item": {
                "title": "Private title",
                "type": "object",
                "properties": {
                    "kind": {"const": "rule", "default": "rule"},
                    "value": {"type": "integer", "minimum": 0},
                },
                "required": ["value"],
                "additionalProperties": False,
            }
        },
        "title": "Private root title",
        "description": "Private root description",
        "type": "object",
        "properties": {
            "items": {
                "type": "array",
                "items": {"$ref": "#/$defs/Item"},
                "default": [],
            }
        },
        "required": ["items"],
        "additionalProperties": False,
    }
    snapshot = json.loads(json.dumps(source))

    result = bedrock_tool_schema(source)

    assert result == {
        "type": "object",
        "properties": {
            "items": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "kind": {"enum": ["rule"]},
                        "value": {"type": "integer", "minimum": 0},
                    },
                    "required": ["value"],
                },
            }
        },
        "required": ["items"],
    }
    assert source == snapshot


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("result", "code"),
    [
        (response(stop_reason="content_filtered"), "refusal"),
        (response(stop_reason="guardrail_intervened"), "refusal"),
        (response(stop_reason="max_tokens"), "invalid_response"),
        (response(content=[]), "invalid_response"),
        (response(content=[{"text": "private"}]), "invalid_response"),
        (
            response(
                content=[
                    {
                        "toolUse": {
                            "toolUseId": "synthetic",
                            "name": "wrong_private_tool",
                            "input": {},
                        }
                    }
                ]
            ),
            "invalid_response",
        ),
        (
            response(
                content=[
                    {
                        "toolUse": {
                            "toolUseId": "one",
                            "name": "policy_extraction_v1",
                            "input": {},
                        }
                    },
                    {
                        "toolUse": {
                            "toolUseId": "two",
                            "name": "policy_extraction_v1",
                            "input": {},
                        }
                    },
                ]
            ),
            "invalid_response",
        ),
        (
            response(
                content=[
                    {
                        "toolUse": {
                            "toolUseId": "synthetic",
                            "name": "policy_extraction_v1",
                            "input": "private invalid input",
                        }
                    }
                ]
            ),
            "invalid_response",
        ),
        (response(content=[{"text": ""}]), "invalid_response"),
        (response(usage={"inputTokens": -1, "outputTokens": 1}), "invalid_response"),
        (
            {
                "output": {"message": "private malformed message"},
                "stopReason": "end_turn",
            },
            "invalid_response",
        ),
        ({}, "invalid_response"),
    ],
)
async def test_bedrock_adapter_rejects_unsafe_or_invalid_responses(
    result: object, code: str
) -> None:
    with pytest.raises(LLMTransportError) as raised:
        await BedrockLLMClient(
            model="amazon.synthetic-v1:0",
            timeout_seconds=30,
            sdk_client=FakeBedrockSDK(result),
        ).complete_json(request())

    assert raised.value.error.code == code
    assert "private" not in str(raised.value)


def client_error(code: str) -> ClientError:
    return ClientError(
        {"Error": {"Code": code, "Message": "private provider error"}},
        "Converse",
    )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("error", "code"),
    [
        (ConnectTimeoutError(endpoint_url="https://private.invalid"), "timeout"),
        (
            EndpointConnectionError(endpoint_url="https://private.invalid"),
            "unavailable",
        ),
        (client_error("ModelTimeoutException"), "timeout"),
        (client_error("ThrottlingException"), "rate_limit"),
        (client_error("ServiceQuotaExceededException"), "rate_limit"),
        (client_error("AccessDeniedException"), "authentication"),
        (client_error("ExpiredTokenException"), "authentication"),
        (client_error("ValidationException"), "invalid_request"),
        (client_error("ResourceNotFoundException"), "invalid_request"),
        (client_error("InternalServerException"), "unavailable"),
        (client_error("UnknownPrivateFailure"), "unavailable"),
    ],
)
async def test_bedrock_adapter_maps_sdk_errors_without_leaking_details(
    error: Exception, code: str
) -> None:
    with pytest.raises(LLMTransportError) as raised:
        await BedrockLLMClient(
            model="amazon.synthetic-v1:0",
            timeout_seconds=30,
            sdk_client=FakeBedrockSDK(error),
        ).complete_json(request())

    assert raised.value.error.code == code
    assert "private" not in str(raised.value)
    assert raised.value.__cause__ is None


@pytest.mark.asyncio
async def test_bedrock_adapter_preserves_cancellation() -> None:
    with pytest.raises(asyncio.CancelledError):
        await BedrockLLMClient(
            model="amazon.synthetic-v1:0",
            timeout_seconds=30,
            sdk_client=FakeBedrockSDK(asyncio.CancelledError()),
        ).complete_json(request())


def test_bedrock_from_settings_requires_model_and_region() -> None:
    with pytest.raises(LLMConfigurationError):
        BedrockLLMClient.from_settings(Settings(llm_provider="bedrock"))
    with pytest.raises(LLMConfigurationError):
        BedrockLLMClient.from_settings(
            Settings(
                llm_provider="bedrock",
                llm_model="model",
                aws_region="us-east-1",
            ).model_copy(update={"aws_region": ""})
        )


def test_bedrock_from_settings_builds_owned_runtime_client(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: list[tuple[str, dict[str, object]]] = []
    sdk = FakeBedrockSDK(response())

    def fake_client(service_name: str, **kwargs: object) -> FakeBedrockSDK:
        captured.append((service_name, kwargs))
        return sdk

    monkeypatch.setattr("app.core.llm_bedrock.boto3.client", fake_client)
    client = BedrockLLMClient.from_settings(
        Settings(
            app_mode="live",
            llm_provider="bedrock",
            llm_model="amazon.synthetic-v1:0",
            aws_region="ap-southeast-1",
            llm_timeout_seconds=9,
        )
    )

    assert captured[0][0] == "bedrock-runtime"
    assert captured[0][1]["region_name"] == "ap-southeast-1"
    config = captured[0][1]["config"]
    assert config.connect_timeout == 9
    assert config.read_timeout == 9
    assert config.retries["total_max_attempts"] == 1
    assert "synthetic" not in repr(client)


@pytest.mark.asyncio
async def test_bedrock_adapter_only_closes_owned_client(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    borrowed = FakeBedrockSDK(response())
    borrowed_client = BedrockLLMClient(
        model="amazon.synthetic-v1:0", timeout_seconds=30, sdk_client=borrowed
    )
    await borrowed_client.aclose()
    await borrowed_client.close()
    assert borrowed.close_calls == 0

    owned = FakeBedrockSDK(response())
    monkeypatch.setattr("app.core.llm_bedrock.boto3.client", lambda *_, **__: owned)
    owned_client = BedrockLLMClient.from_settings(
        Settings(
            llm_provider="bedrock",
            llm_model="amazon.synthetic-v1:0",
        )
    )
    await owned_client.close()
    await owned_client.aclose()
    assert owned.close_calls == 1
