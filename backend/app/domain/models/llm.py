"""Typed generation configuration; no provider integration."""

from typing import Annotated

from pydantic import Field

from .common import NonNegativeInt, Percentage, StrictModel


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
