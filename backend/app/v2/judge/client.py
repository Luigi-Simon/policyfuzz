"""Injectable Judge transport; credentials and endpoint configuration stay in Core."""

import json
import math
from typing import Literal, Protocol

from app.core.config import Settings
from app.v2.contracts import ExecutionMode


class JudgeModelClient(Protocol):
    execution_mode: ExecutionMode | str

    async def complete(
        self, *, system_prompt: str, payload: dict, response_schema: dict
    ) -> str: ...


def validate_timeout(value: float) -> float:
    if (
        isinstance(value, bool)
        or not isinstance(value, (int, float))
        or not math.isfinite(value)
        or not 0 < value <= 600
    ):
        raise ValueError(
            "Judge timeout must be a finite number between 0 and 600 seconds"
        )
    return float(value)


class OpenAIJudgeClient:
    """OpenAI SDK transport. JSON-object compatibility must be selected explicitly."""

    execution_mode = ExecutionMode.LIVE

    def __init__(
        self,
        *,
        model: str,
        sdk_client,
        timeout_seconds: float = 30,
        response_format: Literal["json_schema", "json_object"] = "json_schema",
        max_output_tokens: int = 8192,
    ):
        if not isinstance(model, str) or not model.strip():
            raise ValueError("Judge requires a configured model")
        if response_format not in ("json_schema", "json_object"):
            raise ValueError("Unsupported Judge response format")
        if type(max_output_tokens) is not int or not 256 <= max_output_tokens <= 32768:
            raise ValueError("Invalid Judge output token budget")
        self._sdk = sdk_client.with_options(
            max_retries=0, timeout=validate_timeout(timeout_seconds)
        )
        self._model = model.strip()
        self._response_format = response_format
        self._max_output_tokens = max_output_tokens
        self._owned_sdk = None

    @classmethod
    def from_settings(
        cls,
        settings: Settings,
        *,
        response_format: Literal["json_schema", "json_object"] = "json_schema",
    ) -> "OpenAIJudgeClient":
        """Reuse Core's LLM_MODEL/OPENAI_API_KEY/LLM_BASE_URL configuration."""
        import openai

        key = settings.openai_api_key
        if (
            not settings.llm_model
            or not settings.llm_model.strip()
            or key is None
            or not key.get_secret_value().strip()
        ):
            raise ValueError("Judge requires LLM_MODEL and OPENAI_API_KEY")
        sdk = openai.AsyncOpenAI(
            api_key=key.get_secret_value(),
            base_url=settings.llm_base_url,
            timeout=validate_timeout(settings.llm_timeout_seconds),
            max_retries=0,
        )
        client = cls(
            model=settings.llm_model,
            sdk_client=sdk,
            timeout_seconds=settings.llm_timeout_seconds,
            response_format=response_format,
        )
        client._owned_sdk = sdk
        return client

    async def complete(
        self, *, system_prompt: str, payload: dict, response_schema: dict
    ) -> str:
        if self._response_format == "json_schema":
            response_format = {
                "type": "json_schema",
                "json_schema": {
                    "name": "policyfuzz_judge",
                    "schema": response_schema,
                    "strict": True,
                },
            }
            data = payload
        else:
            response_format = {"type": "json_object"}
            data = {"input": payload, "response_schema": response_schema}
        completion = await self._sdk.chat.completions.create(
            model=self._model,
            messages=[
                {"role": "system", "content": system_prompt},
                {
                    "role": "user",
                    "content": json.dumps(data, ensure_ascii=False, allow_nan=False),
                },
            ],
            response_format=response_format,
            max_completion_tokens=self._max_output_tokens,
            stream=False,
            store=False,
        )
        choices = getattr(completion, "choices", None)
        if not choices or len(choices) != 1:
            raise RuntimeError("Judge provider returned no usable response")
        choice = choices[0]
        message = getattr(choice, "message", None)
        content = getattr(message, "content", None)
        if (
            getattr(choice, "finish_reason", None) != "stop"
            or getattr(message, "refusal", None)
            or getattr(message, "tool_calls", None)
            or not isinstance(content, str)
            or not content.strip()
        ):
            raise RuntimeError("Judge provider returned no usable response")
        return content

    async def aclose(self) -> None:
        if self._owned_sdk is not None:
            await self._owned_sdk.close()
            self._owned_sdk = None
