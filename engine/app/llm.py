"""OpenAI-compatible LLM adapter with JSON-mode + mock."""

from __future__ import annotations

import json
import re
from typing import Any

from openai import OpenAI

from app.config import Settings, get_settings


class LLMError(RuntimeError):
    pass


def _strip_fences(text: str) -> str:
    cleaned = re.sub(r"<think>[\s\S]*?</think>", "", text).strip()
    cleaned = re.sub(r"^```(?:json)?\s*\n?", "", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"\n?```\s*$", "", cleaned)
    return cleaned.strip()


def parse_json_object(text: str) -> dict[str, Any]:
    cleaned = _strip_fences(text)
    try:
        value = json.loads(cleaned)
        if isinstance(value, dict):
            return value
    except json.JSONDecodeError:
        pass
    start = cleaned.find("{")
    end = cleaned.rfind("}")
    if start >= 0 and end > start:
        value = json.loads(cleaned[start : end + 1])
        if isinstance(value, dict):
            return value
    raise LLMError("Model did not return a JSON object")


class LLMAdapter:
    def __init__(self, settings: Settings | None = None):
        self.settings = settings or get_settings()
        self._client: OpenAI | None = None

    @property
    def enabled(self) -> bool:
        return self.settings.use_llm

    def _client_or_raise(self) -> OpenAI:
        if not self.enabled:
            raise LLMError("LLM is disabled (set LLM_API_KEY and LLM_MOCK=false)")
        if self._client is None:
            self._client = OpenAI(
                api_key=self.settings.llm_api_key,
                base_url=self.settings.llm_base_url,
                timeout=self.settings.llm_timeout_seconds,
            )
        return self._client

    def complete_json(
        self,
        *,
        system: str,
        user: str,
        temperature: float = 0.1,
    ) -> dict[str, Any]:
        client = self._client_or_raise()
        messages = [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ]
        try:
            response = client.chat.completions.create(
                model=self.settings.llm_model_name,
                messages=messages,
                temperature=temperature,
                response_format={"type": "json_object"},
            )
        except Exception as first_error:
            try:
                response = client.chat.completions.create(
                    model=self.settings.llm_model_name,
                    messages=messages,
                    temperature=temperature,
                )
            except Exception as second_error:
                raise LLMError(f"LLM call failed: {second_error}") from first_error

        content = (response.choices[0].message.content or "").strip()
        if not content:
            raise LLMError("LLM returned an empty response")
        return parse_json_object(content)
