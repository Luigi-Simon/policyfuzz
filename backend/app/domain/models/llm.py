"""Provider-neutral LLM transport contracts and generation accounting."""

import json
import math
from typing import Annotated, Literal

from pydantic import ConfigDict, Field, JsonValue, field_validator

from .common import NonEmptyText, NonNegativeInt, Percentage, StrictModel

LLMOperation = Literal[
    "policy_extraction",
    "invariant_suggestion",
    "scenario_generation",
    "targeted_scenario_generation",
    "revision_proposal",
]
LLMErrorCode = Literal[
    "timeout",
    "rate_limit",
    "authentication",
    "invalid_request",
    "unavailable",
    "invalid_response",
    "refusal",
    "script_exhausted",
]


def _has_nonfinite_number(value: JsonValue) -> bool:
    if isinstance(value, float):
        return not math.isfinite(value)
    if isinstance(value, list):
        return any(_has_nonfinite_number(item) for item in value)
    if isinstance(value, dict):
        return any(_has_nonfinite_number(item) for item in value.values())
    return False


class GenerationConfig(StrictModel):
    temperature_milli: Annotated[int, Field(ge=0, le=2000)] = 0
    top_p_percent: Percentage = 100
    max_output_tokens: Annotated[int, Field(ge=1)] = 4096
    seed: NonNegativeInt | None = None


class GenerationUsage(StrictModel):
    input_tokens: NonNegativeInt = 0
    output_tokens: NonNegativeInt = 0
    repair_calls: Annotated[int, Field(ge=0, le=1)] = 0
    transport_retries: Annotated[int, Field(ge=0, le=2)] = 0


class LLMRequest(StrictModel):
    model_config = ConfigDict(hide_input_in_errors=True)

    operation: LLMOperation
    system_instructions: NonEmptyText = Field(repr=False)
    untrusted_payload_json: NonEmptyText = Field(repr=False)
    response_schema: dict[str, JsonValue] = Field(repr=False)
    response_schema_name: Annotated[
        str, Field(min_length=1, max_length=64, pattern=r"^[A-Za-z0-9_-]+$")
    ]
    generation_config: GenerationConfig = Field(default_factory=GenerationConfig)
    repair_attempt: Literal[0, 1] = 0

    @field_validator("untrusted_payload_json")
    @classmethod
    def json_object_payload(cls, value: str) -> str:
        nonfinite = False

        def reject_constant(_: str) -> None:
            nonlocal nonfinite
            nonfinite = True

        try:
            parsed = json.loads(value, parse_constant=reject_constant)
        except (json.JSONDecodeError, TypeError):
            raise ValueError("payload must be a JSON object") from None
        if nonfinite or _has_nonfinite_number(parsed):
            raise ValueError("payload must contain finite JSON values")
        if not isinstance(parsed, dict):
            # Pydantic v2 does not convert TypeError from validators to ValidationError.
            raise ValueError("payload must be a JSON object")  # noqa: TRY004
        return value

    @field_validator("response_schema")
    @classmethod
    def object_schema(cls, value: dict[str, JsonValue]) -> dict[str, JsonValue]:
        if _has_nonfinite_number(value):
            raise ValueError("response schema must contain finite JSON values")
        if value.get("type") != "object":
            raise ValueError("response schema root must be an object")
        return value


class LLMResponse(StrictModel):
    model_config = ConfigDict(hide_input_in_errors=True)

    output: dict[str, JsonValue] | str = Field(repr=False)
    usage: GenerationUsage = Field(default_factory=GenerationUsage)

    @field_validator("output")
    @classmethod
    def finite_structured_output(
        cls, value: dict[str, JsonValue] | str
    ) -> dict[str, JsonValue] | str:
        if isinstance(value, dict) and _has_nonfinite_number(value):
            raise ValueError("output must contain finite JSON values")
        return value


class LLMError(StrictModel):
    code: LLMErrorCode
    operation: LLMOperation
    transport_retries: Annotated[int, Field(ge=0, le=2)] = 0
