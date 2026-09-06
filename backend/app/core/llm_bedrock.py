"""Amazon Bedrock adapter for the provider-neutral LLM transport protocol."""

import asyncio
from copy import deepcopy
from typing import Protocol, cast

import boto3
from botocore.config import Config
from botocore.exceptions import (
    BotoCoreError,
    ClientError,
    ConnectTimeoutError,
    CredentialRetrievalError,
    NoCredentialsError,
    ParamValidationError,
    PartialCredentialsError,
    ReadTimeoutError,
)
from pydantic import ValidationError

from app.core.config import Settings
from app.core.errors import LLMConfigurationError, LLMTransportError
from app.domain.models import GenerationUsage, LLMError, LLMRequest, LLMResponse

_UNTRUSTED_INPUT_LABEL = "UNTRUSTED_JSON_INPUT:\n"
_JSON_INSTRUCTION = (
    "Call the required response tool exactly once with the complete PolicyFuzz "
    "result. Do not answer with prose or call any other tool."
)
_REMOVED_SCHEMA_KEYS = frozenset(
    {
        "$defs",
        "$id",
        "$schema",
        "additionalProperties",
        "default",
        "definitions",
        "deprecated",
        "description",
        "discriminator",
        "examples",
        "format",
        "readOnly",
        "title",
        "uniqueItems",
        "writeOnly",
    }
)


class _BedrockRuntime(Protocol):
    def converse(self, **kwargs: object) -> object: ...

    def close(self) -> None: ...


def _transport_error(code: str, request: LLMRequest) -> LLMTransportError:
    return LLMTransportError(LLMError(code=code, operation=request.operation))


def _client_error_code(error: ClientError) -> str:
    try:
        value = error.response["Error"]["Code"]
    except (KeyError, TypeError):
        return "unavailable"
    if value == "ModelTimeoutException":
        return "timeout"
    if value in {
        "ServiceQuotaExceededException",
        "ThrottlingException",
        "TooManyRequestsException",
    }:
        return "rate_limit"
    if value in {
        "AccessDeniedException",
        "ExpiredTokenException",
        "InvalidSignatureException",
        "UnrecognizedClientException",
    }:
        return "authentication"
    if value in {
        "ResourceNotFoundException",
        "ValidationException",
    }:
        return "invalid_request"
    return "unavailable"


def bedrock_tool_schema(source: dict[str, object]) -> dict[str, object]:
    """Inline local references and retain Nova-compatible schema constraints."""

    root = deepcopy(source)
    definitions: dict[str, object] = {}
    for key in ("$defs", "definitions"):
        value = root.get(key)
        if isinstance(value, dict):
            definitions.update(value)

    def normalize(value: object, stack: tuple[str, ...] = ()) -> object:
        if isinstance(value, list):
            return [normalize(item, stack) for item in value]
        if not isinstance(value, dict):
            return deepcopy(value)

        reference = value.get("$ref")
        if isinstance(reference, str):
            prefixes = ("#/$defs/", "#/definitions/")
            name = next(
                (
                    reference.removeprefix(prefix)
                    for prefix in prefixes
                    if reference.startswith(prefix)
                ),
                None,
            )
            if name is None or name not in definitions or name in stack:
                raise LLMConfigurationError() from None
            target = definitions[name]
            if not isinstance(target, dict):
                raise LLMConfigurationError() from None
            merged = deepcopy(target)
            merged.update({key: item for key, item in value.items() if key != "$ref"})
            return normalize(merged, stack + (name,))

        normalized: dict[str, object] = {}
        for key, item in value.items():
            if key in _REMOVED_SCHEMA_KEYS:
                continue
            if key == "const":
                normalized["enum"] = [normalize(item, stack)]
                continue
            if key == "oneOf":
                normalized["anyOf"] = normalize(item, stack)
                continue
            normalized[key] = normalize(item, stack)
        return normalized

    normalized = normalize(root)
    if not isinstance(normalized, dict):
        raise LLMConfigurationError() from None
    properties = normalized.get("properties")
    if normalized.get("type") != "object" or not isinstance(properties, dict):
        raise LLMConfigurationError() from None
    required = normalized.get("required", [])
    if not isinstance(required, list):
        raise LLMConfigurationError() from None
    return {
        "type": "object",
        "properties": properties,
        "required": required,
    }


class BedrockLLMClient:
    """Call Bedrock Converse without coupling workflow stages to AWS shapes."""

    def __init__(
        self,
        *,
        model: str,
        timeout_seconds: float,
        sdk_client: object,
    ) -> None:
        self._configure(
            model=model,
            timeout_seconds=timeout_seconds,
            sdk_client=sdk_client,
            owned_client=None,
        )

    def _configure(
        self,
        *,
        model: str,
        timeout_seconds: float,
        sdk_client: object,
        owned_client: _BedrockRuntime | None,
    ) -> None:
        if not isinstance(model, str) or not model.strip():
            raise LLMConfigurationError() from None
        if (
            isinstance(timeout_seconds, bool)
            or not isinstance(timeout_seconds, (int, float))
            or not 0 < timeout_seconds <= 120
        ):
            raise LLMConfigurationError() from None
        if not callable(getattr(sdk_client, "converse", None)):
            raise LLMConfigurationError() from None
        self._sdk_client = cast(_BedrockRuntime, sdk_client)
        self._model = model.strip()
        self._timeout_seconds = float(timeout_seconds)
        self._owned_client = owned_client
        self._closed = False

    @classmethod
    def from_settings(cls, settings: Settings) -> "BedrockLLMClient":
        model = settings.llm_model
        region = settings.aws_region
        if model is None or not model.strip() or not region.strip():
            raise LLMConfigurationError() from None
        try:
            sdk_client = boto3.client(
                "bedrock-runtime",
                region_name=region,
                config=Config(
                    connect_timeout=settings.llm_timeout_seconds,
                    read_timeout=settings.llm_timeout_seconds,
                    retries={"total_max_attempts": 1, "mode": "standard"},
                ),
            )
        except Exception:  # noqa: BLE001 - sanitize credential/config discovery
            raise LLMConfigurationError() from None
        instance = cls.__new__(cls)
        instance._configure(
            model=model,
            timeout_seconds=settings.llm_timeout_seconds,
            sdk_client=sdk_client,
            owned_client=cast(_BedrockRuntime, sdk_client),
        )
        return instance

    async def complete_json(self, request: LLMRequest) -> LLMResponse:
        schema = deepcopy(request.response_schema)
        tool_schema = bedrock_tool_schema(schema)
        system_text = (
            f"{request.system_instructions}\n\n{_JSON_INSTRUCTION}\n"
            f"REQUIRED_RESPONSE_TOOL: {request.response_schema_name}"
        )
        kwargs: dict[str, object] = {
            "modelId": self._model,
            "system": [{"text": system_text}],
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {
                            "text": _UNTRUSTED_INPUT_LABEL
                            + request.untrusted_payload_json
                        }
                    ],
                }
            ],
            "inferenceConfig": {
                "maxTokens": request.generation_config.max_output_tokens,
                "temperature": 0,
            },
            "toolConfig": {
                "tools": [
                    {
                        "toolSpec": {
                            "name": request.response_schema_name,
                            "description": (
                                "Return the requested PolicyFuzz structured result."
                            ),
                            "inputSchema": {"json": tool_schema},
                        }
                    }
                ],
                "toolChoice": {
                    "tool": {"name": request.response_schema_name},
                },
            },
        }
        try:
            result = await asyncio.to_thread(self._sdk_client.converse, **kwargs)
        except asyncio.CancelledError:
            raise
        except (ConnectTimeoutError, ReadTimeoutError):
            raise _transport_error("timeout", request) from None
        except (
            CredentialRetrievalError,
            NoCredentialsError,
            PartialCredentialsError,
        ):
            raise _transport_error("authentication", request) from None
        except ParamValidationError:
            raise _transport_error("invalid_request", request) from None
        except ClientError as error:
            raise _transport_error(_client_error_code(error), request) from None
        except BotoCoreError:
            raise _transport_error("unavailable", request) from None
        except Exception:  # noqa: BLE001 - unknown SDK errors are safely unavailable
            raise _transport_error("unavailable", request) from None
        return self._response(result, request)

    @staticmethod
    def _response(result: object, request: LLMRequest) -> LLMResponse:
        try:
            if not isinstance(result, dict):
                raise TypeError
            stop_reason = result["stopReason"]
            if stop_reason in {"content_filtered", "guardrail_intervened"}:
                raise _transport_error("refusal", request) from None
            if stop_reason != "tool_use":
                raise _transport_error("invalid_response", request) from None
            message = result["output"]["message"]
            if message.get("role") != "assistant":
                raise TypeError
            content = message["content"]
            if not isinstance(content, list) or not content:
                raise TypeError
            tool_inputs: list[dict[str, object]] = []
            for block in content:
                if not isinstance(block, dict):
                    raise TypeError
                if "toolUse" not in block:
                    if set(block) == {"text"} and isinstance(block["text"], str):
                        continue
                    raise TypeError
                tool_use = block["toolUse"]
                if not isinstance(tool_use, dict):
                    raise TypeError
                if tool_use.get("name") != request.response_schema_name:
                    raise TypeError
                tool_input = tool_use.get("input")
                if not isinstance(tool_input, dict):
                    raise TypeError
                tool_inputs.append(tool_input)
            if len(tool_inputs) != 1:
                raise TypeError
            output = deepcopy(tool_inputs[0])
            provider_usage = result.get("usage")
            if provider_usage is None:
                usage = GenerationUsage(repair_calls=request.repair_attempt)
            else:
                usage = GenerationUsage(
                    input_tokens=provider_usage["inputTokens"],
                    output_tokens=provider_usage["outputTokens"],
                    repair_calls=request.repair_attempt,
                    transport_retries=0,
                )
            return LLMResponse(output=output, usage=usage)
        except LLMTransportError:
            raise
        except (AttributeError, KeyError, TypeError, ValidationError):
            raise _transport_error("invalid_response", request) from None

    async def aclose(self) -> None:
        if self._owned_client is not None and not self._closed:
            try:
                await asyncio.to_thread(self._owned_client.close)
            except asyncio.CancelledError:
                raise
            except Exception:  # noqa: BLE001 - sanitize owned SDK close failures
                raise LLMConfigurationError() from None
            self._closed = True

    async def close(self) -> None:
        await self.aclose()


__all__ = ["BedrockLLMClient", "bedrock_tool_schema"]
