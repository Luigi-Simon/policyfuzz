"""OpenAI SDK adapter for the provider-neutral LLM transport protocol."""

import asyncio
from copy import deepcopy
from typing import Protocol, cast

import openai
from pydantic import ValidationError

from app.core.config import Settings
from app.core.errors import LLMConfigurationError, LLMTransportError
from app.domain.models import GenerationUsage, LLMError, LLMRequest, LLMResponse

_UNTRUSTED_INPUT_LABEL = "UNTRUSTED_JSON_INPUT:\n"
_NO_SAMPLING_PREFIXES = ("gpt-5", "gpt-6", "o1", "o3", "o4")
_NONE_REASONING_PREFIXES = (
    "gpt-5.1",
    "gpt-5.2",
    "gpt-5.4",
    "gpt-5.5",
    "gpt-5.6",
)


class _Completions(Protocol):
    async def create(self, **kwargs: object) -> object: ...


class _Chat(Protocol):
    completions: _Completions


class _AsyncSDK(Protocol):
    chat: _Chat

    def with_options(self, **kwargs: object) -> "_AsyncSDK": ...

    async def close(self) -> None: ...


def _transport_error(code: str, request: LLMRequest) -> LLMTransportError:
    return LLMTransportError(LLMError(code=code, operation=request.operation))


def openai_strict_schema(source: dict[str, object]) -> dict[str, object]:
    """Return an OpenAI strict-mode schema without mutating the domain schema."""

    def normalize(value: object) -> object:
        if isinstance(value, list):
            return [normalize(item) for item in value]
        if not isinstance(value, dict):
            return value

        normalized: dict[str, object] = {}
        for key, item in value.items():
            if key in {"default", "discriminator"}:
                continue
            normalized["anyOf" if key == "oneOf" else key] = normalize(item)

        if normalized.get("type") == "object":
            properties = normalized.get("properties")
            if isinstance(properties, dict):
                normalized["required"] = list(properties)
                normalized["additionalProperties"] = False
        return normalized

    schema = normalize(deepcopy(source))
    if not isinstance(schema, dict):
        raise LLMConfigurationError() from None
    return schema


class OpenAILLMClient:
    """Submit isolated instructions, payload, and schema through the public SDK."""

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
        owned_client: _AsyncSDK | None,
    ) -> None:
        if not isinstance(model, str) or not model.strip():
            raise LLMConfigurationError() from None
        if (
            isinstance(timeout_seconds, bool)
            or not isinstance(timeout_seconds, (int, float))
            or not 0 < timeout_seconds <= 120
        ):
            raise LLMConfigurationError() from None
        try:
            source = cast(_AsyncSDK, sdk_client)
            self._sdk_client = source.with_options(
                max_retries=0, timeout=float(timeout_seconds)
            )
        except Exception:  # noqa: BLE001 - sanitize injected SDK configuration failures
            raise LLMConfigurationError() from None
        self._model = model.strip()
        self._timeout_seconds = float(timeout_seconds)
        self._owned_client = owned_client
        self._closed = False

    @classmethod
    def from_settings(cls, settings: Settings) -> "OpenAILLMClient":
        model = settings.llm_model
        key = settings.openai_api_key
        if model is None or not model.strip() or key is None:
            raise LLMConfigurationError() from None
        secret = key.get_secret_value()
        if not secret.strip():
            raise LLMConfigurationError() from None
        try:
            sdk_client = openai.AsyncOpenAI(
                api_key=secret,
                max_retries=0,
                timeout=settings.llm_timeout_seconds,
            )
        except Exception:  # noqa: BLE001 - sanitize SDK construction failures
            raise LLMConfigurationError() from None
        instance = cls.__new__(cls)
        instance._configure(
            model=model,
            timeout_seconds=settings.llm_timeout_seconds,
            sdk_client=sdk_client,
            owned_client=cast(_AsyncSDK, sdk_client),
        )
        return instance

    async def complete_json(self, request: LLMRequest) -> LLMResponse:
        schema = openai_strict_schema(request.response_schema)
        kwargs: dict[str, object] = {
            "model": self._model,
            "messages": [
                {"role": "system", "content": request.system_instructions},
                {
                    "role": "user",
                    "content": _UNTRUSTED_INPUT_LABEL + request.untrusted_payload_json,
                },
            ],
            "response_format": {
                "type": "json_schema",
                "json_schema": {
                    "name": request.response_schema_name,
                    "schema": schema,
                    "strict": True,
                },
            },
            "max_completion_tokens": request.generation_config.max_output_tokens,
            "stream": False,
            "store": False,
        }
        if self._model.startswith(_NONE_REASONING_PREFIXES):
            kwargs["reasoning_effort"] = "none"
        if not self._model.startswith(_NO_SAMPLING_PREFIXES):
            kwargs["temperature"] = request.generation_config.temperature_milli / 1000
            kwargs["top_p"] = request.generation_config.top_p_percent / 100
            if request.generation_config.seed is not None:
                kwargs["seed"] = request.generation_config.seed
        try:
            completion = await self._sdk_client.chat.completions.create(**kwargs)
        except asyncio.CancelledError:
            raise
        except openai.APITimeoutError:
            raise _transport_error("timeout", request) from None
        except openai.RateLimitError:
            raise _transport_error("rate_limit", request) from None
        except (openai.AuthenticationError, openai.PermissionDeniedError):
            raise _transport_error("authentication", request) from None
        except (
            openai.BadRequestError,
            openai.NotFoundError,
            openai.UnprocessableEntityError,
        ):
            raise _transport_error("invalid_request", request) from None
        except openai.APIResponseValidationError:
            raise _transport_error("invalid_response", request) from None
        except (openai.APIConnectionError, openai.InternalServerError):
            raise _transport_error("unavailable", request) from None
        except Exception:  # noqa: BLE001 - unknown SDK errors are safely unavailable
            raise _transport_error("unavailable", request) from None
        return self._response(completion, request)

    @staticmethod
    def _response(completion: object, request: LLMRequest) -> LLMResponse:
        choices = getattr(completion, "choices", None)
        if not choices:
            raise _transport_error("invalid_response", request) from None
        try:
            choice = choices[0]
            message = choice.message
            finish_reason = choice.finish_reason
        except (AttributeError, IndexError, KeyError, TypeError):
            raise _transport_error("invalid_response", request) from None
        if getattr(message, "refusal", None) or finish_reason == "content_filter":
            raise _transport_error("refusal", request) from None
        if finish_reason != "stop" or getattr(message, "tool_calls", None):
            raise _transport_error("invalid_response", request) from None
        content = getattr(message, "content", None)
        if not isinstance(content, str) or not content:
            raise _transport_error("invalid_response", request) from None

        provider_usage = getattr(completion, "usage", None)
        try:
            if provider_usage is None:
                usage = GenerationUsage(repair_calls=request.repair_attempt)
            else:
                usage = GenerationUsage(
                    input_tokens=provider_usage.prompt_tokens,
                    output_tokens=provider_usage.completion_tokens,
                    repair_calls=request.repair_attempt,
                    transport_retries=0,
                )
            return LLMResponse(output=content, usage=usage)
        except (AttributeError, TypeError, ValidationError):
            raise _transport_error("invalid_response", request) from None

    async def aclose(self) -> None:
        if self._owned_client is not None and not self._closed:
            try:
                await self._owned_client.close()
            except asyncio.CancelledError:
                raise
            except Exception:  # noqa: BLE001 - sanitize owned SDK close failures
                raise LLMConfigurationError() from None
            self._closed = True

    async def close(self) -> None:
        await self.aclose()


__all__ = ["OpenAILLMClient", "openai_strict_schema"]
