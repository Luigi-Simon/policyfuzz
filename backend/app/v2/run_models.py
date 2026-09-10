"""Public transport models for the standalone v2 API."""

from __future__ import annotations

import re
from typing import ClassVar, Literal

from pydantic import Field, field_validator

from .contracts import (
    ContractModel,
    ExecutionMode,
    Persona,
    PolicyInput,
    SandboxMessage,
    SandboxStatus,
    SourceEvidence,
)
from .fixtures import FixtureName

_HAN_SCRIPT = re.compile(
    r"[\u3400-\u4dbf\u4e00-\u9fff\uf900-\ufaff\U00020000-\U0003134f]"
)


class RunPolicyInput(PolicyInput):
    """The four policy fields accepted by the first-run milestone."""

    title: str = Field(min_length=1, max_length=200)
    description: str = Field(min_length=1, max_length=50_000)
    agent_seed: str = Field(min_length=1, max_length=2_000)
    agent_count: int = Field(strict=True, ge=1, le=100)
    supporting_documents: ClassVar[None] = None

    @field_validator("title", "description", "agent_seed")
    @classmethod
    def strings_are_not_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("value must not be blank")
        return value

    @field_validator("title")
    @classmethod
    def title_has_no_han_script(cls, value: str) -> str:
        if _HAN_SCRIPT.search(value):
            raise ValueError("title must use English display text")
        return value


class CreateRunRequest(ContractModel):
    policy: RunPolicyInput
    fixture_name: FixtureName = "completed"


class PrepareMetricRequest(ContractModel):
    policy: RunPolicyInput


class RunMetricRequest(PrepareMetricRequest):
    review_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")


class PublicSandboxResult(ContractModel):
    """Explicit public allowlist for Sandbox evidence."""

    schema_version: Literal["2.0"] = "2.0"
    request_id: str = Field(min_length=1)
    run_id: str = Field(min_length=1)
    policy_version: str = Field(min_length=1)
    policy_title: str = Field(min_length=1)
    policy_text_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    request_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")
    execution_mode: ExecutionMode
    status: SandboxStatus
    requested_stakeholder_count: int = Field(ge=1)
    configured_stakeholder_count: int = Field(ge=0)
    observed_stakeholder_count: int = Field(ge=0)
    personas: tuple[Persona, ...] = ()
    messages: tuple[SandboxMessage, ...] = ()
    sources: tuple[SourceEvidence, ...] = ()
    limitations: tuple[str, ...] = ()
    errors: tuple[str, ...] = ()


class HealthResponse(ContractModel):
    status: Literal["ok"] = "ok"
    execution_mode: Literal["fixture"] = "fixture"


class PublicError(ContractModel):
    detail: str = Field(min_length=1)
