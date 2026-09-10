"""Version 2 Sandbox boundary models and validation."""

from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime
from enum import Enum
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

SCHEMA_VERSION = "2.0"
FOUNDATION_MAX_STAKEHOLDERS = 100
ENGLISH_TRANSLATION_UNAVAILABLE = "[English translation unavailable for this record.]"
_HAN_SCRIPT = re.compile(
    r"[\u3400-\u4dbf\u4e00-\u9fff\uf900-\ufaff\U00020000-\U0003134f]"
)


def _english_display(value: str) -> str:
    """Reject visible Han script; this is not a complete English-language detector."""
    if _HAN_SCRIPT.search(value):
        raise ValueError("English display field contains Han-script text")
    return value


class ContractModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class AgentRole(str, Enum):
    ORCHESTRATOR = "Orchestrator Agent"
    METRIC = "Metric Agent"
    SANDBOX = "Sandbox Agent"
    JUDGE = "Judge Agent"


class ExecutionMode(str, Enum):
    FIXTURE = "fixture"
    RECORDED = "recorded"
    LIVE = "live"


class SandboxStatus(str, Enum):
    COMPLETED = "completed"
    PARTIAL = "partial"
    FAILED = "failed"
    CANCELLED = "cancelled"


class TranslationStatus(str, Enum):
    ORIGINAL_ENGLISH = "original_english"
    TRANSLATED = "translated"
    UNAVAILABLE = "unavailable"


class SupportingDocument(ContractModel):
    document_id: str = Field(min_length=1)
    title: str = Field(min_length=1)
    text: str = Field(min_length=1)
    source_uri: str | None = None


class PolicyInput(ContractModel):
    title: str = Field(min_length=1)
    description: str = Field(min_length=1)
    agent_seed: str = Field(min_length=1)
    agent_count: int = Field(ge=1, le=FOUNDATION_MAX_STAKEHOLDERS)
    supporting_documents: tuple[SupportingDocument, ...] = ()


class ContextSource(ContractModel):
    source_id: str = Field(min_length=1)
    title: str = Field(min_length=1)
    text: str = Field(min_length=1)
    source_uri: str | None = None


class ScenarioSetup(ContractModel):
    scenario_id: str = Field(min_length=1)
    title: str = Field(min_length=1)
    circumstances: str = Field(min_length=1)
    stakeholder_actions: tuple[str, ...] = ()


class SandboxRequest(ContractModel):
    schema_version: Literal["2.0"] = SCHEMA_VERSION
    request_id: str = Field(min_length=1)
    run_id: str = Field(min_length=1)
    policy_version: str = Field(min_length=1)
    policy_title: str = Field(min_length=1)
    policy_text: str = Field(min_length=1)
    policy_text_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    personality_seed: str = Field(min_length=1)
    random_seed: int | None = None
    stakeholder_count: int = Field(ge=1, le=FOUNDATION_MAX_STAKEHOLDERS)
    test_budget: int = Field(ge=1, le=100)
    context: tuple[ContextSource, ...]
    scenario_setups: tuple[ScenarioSetup, ...] = ()
    target_language: Literal["English"] = "English"
    max_rounds: int = Field(default=4, ge=1, le=20)
    timeout_seconds: int = Field(default=120, ge=1, le=600)

    @model_validator(mode="after")
    def exact_policy_hash_matches(self) -> SandboxRequest:
        expected = hashlib.sha256(self.policy_text.encode("utf-8")).hexdigest()
        if self.policy_text_sha256 != expected:
            raise ValueError("policy_text_sha256 does not match exact policy_text")
        return self


class Persona(ContractModel):
    persona_id: str = Field(min_length=1)
    display_name: str = Field(min_length=1)
    description: str = Field(min_length=1)

    _display_name_is_english = field_validator("display_name")(_english_display)
    _description_is_english = field_validator("description")(_english_display)


class SandboxMessage(ContractModel):
    message_id: str = Field(min_length=1)
    sequence: int = Field(ge=1)
    persona_id: str = Field(min_length=1)
    content: str = Field(min_length=1)
    translation_status: TranslationStatus
    source_refs: tuple[str, ...] = ()
    reply_to_message_ids: tuple[str, ...] = ()
    round_number: int | None = Field(default=None, ge=1)
    recorded_at: datetime | None = None

    _content_is_english = field_validator("content")(_english_display)


class SourceEvidence(ContractModel):
    source_id: str = Field(min_length=1)
    record_id: str = Field(min_length=1)
    title: str = Field(min_length=1)
    excerpt: str = Field(min_length=1)

    _title_is_english = field_validator("title")(_english_display)
    _excerpt_is_english = field_validator("excerpt")(_english_display)


class OriginalRecord(ContractModel):
    record_id: str = Field(min_length=1)
    speaker_id: str = Field(min_length=1)
    source_id: str = Field(min_length=1)
    content: str = Field(min_length=1)
    language: str = Field(min_length=1)
    reply_to_record_ids: tuple[str, ...] = ()


class SandboxResult(ContractModel):
    schema_version: Literal["2.0"] = SCHEMA_VERSION
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
    original_records: tuple[OriginalRecord, ...] = ()

    _title_is_english = field_validator("policy_title")(_english_display)

    @field_validator("limitations", "errors")
    @classmethod
    def public_notes_are_english(cls, values: tuple[str, ...]) -> tuple[str, ...]:
        return tuple(_english_display(value) for value in values)


_PUBLIC_RESULT_FIELDS = {
    "schema_version",
    "request_id",
    "run_id",
    "policy_version",
    "policy_title",
    "policy_text_sha256",
    "request_fingerprint",
    "execution_mode",
    "status",
    "requested_stakeholder_count",
    "configured_stakeholder_count",
    "observed_stakeholder_count",
    "personas",
    "messages",
    "sources",
    "limitations",
    "errors",
}


def request_fingerprint(request: SandboxRequest) -> str:
    """Hash the canonical serialization of the complete, validated request."""
    canonical = json.dumps(
        request.model_dump(mode="json"),
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _require_unique(kind: str, values: list[str]) -> None:
    if len(values) != len(set(values)):
        raise ValueError(f"duplicate {kind} ID")


def validate_sandbox_result(request: SandboxRequest, result: SandboxResult) -> None:
    """Validate identity, provenance, ordering, references, counts, and status."""
    request = SandboxRequest.model_validate(request.model_dump(warnings=False))
    result = SandboxResult.model_validate(result.model_dump(warnings=False))
    identity = (
        ("request_id", request.request_id, result.request_id),
        ("run_id", request.run_id, result.run_id),
        ("policy_version", request.policy_version, result.policy_version),
        ("policy_title", request.policy_title, result.policy_title),
        ("policy_text_sha256", request.policy_text_sha256, result.policy_text_sha256),
    )
    for name, expected, actual in identity:
        if actual != expected:
            raise ValueError(f"result {name} does not match request")
    if result.request_fingerprint != request_fingerprint(request):
        raise ValueError("result request_fingerprint does not match complete request")

    persona_ids = [persona.persona_id for persona in result.personas]
    message_ids = [message.message_id for message in result.messages]
    source_ids = [source.source_id for source in result.sources]
    source_record_ids = [source.record_id for source in result.sources]
    record_ids = [record.record_id for record in result.original_records]
    _require_unique("persona", persona_ids)
    _require_unique("message", message_ids)
    _require_unique("source", source_ids)
    _require_unique("source record", source_record_ids)
    _require_unique("original record", record_ids)

    for source in result.sources:
        if source.record_id not in set(message_ids):
            raise ValueError(f"source {source.source_id} references unknown record")

    if [message.sequence for message in result.messages] != list(
        range(1, len(result.messages) + 1)
    ):
        raise ValueError("message sequence must be contiguous and ordered from 1")

    persona_id_set = set(persona_ids)
    source_id_set = set(source_ids)
    seen_messages: set[str] = set()
    for message in result.messages:
        if message.persona_id not in persona_id_set:
            raise ValueError(f"message {message.message_id} references unknown persona")
        if len(message.source_refs) != len(set(message.source_refs)):
            raise ValueError(
                f"message {message.message_id} has duplicate source references"
            )
        unknown_sources = set(message.source_refs) - source_id_set
        if unknown_sources:
            raise ValueError(f"message {message.message_id} references unknown source")
        if len(message.reply_to_message_ids) != len(set(message.reply_to_message_ids)):
            raise ValueError(
                f"message {message.message_id} has duplicate reply references"
            )
        if set(message.reply_to_message_ids) - seen_messages:
            raise ValueError(
                f"message {message.message_id} has unknown reply reference"
            )
        seen_messages.add(message.message_id)

    message_by_id = {message.message_id: message for message in result.messages}
    source_by_record = {source.record_id: source for source in result.sources}
    original_by_id = {record.record_id: record for record in result.original_records}
    for message in result.messages:
        if result.status is SandboxStatus.COMPLETED:
            own_source = source_by_record.get(message.message_id)
            if own_source is None or own_source.source_id not in message.source_refs:
                raise ValueError("completed message must cite its own source record")
        if (
            message.round_number is not None
            and message.round_number > request.max_rounds
        ):
            raise ValueError("message round_number exceeds request max_rounds")
        if (
            message.translation_status
            in {
                TranslationStatus.TRANSLATED,
                TranslationStatus.UNAVAILABLE,
            }
            and message.message_id not in original_by_id
        ):
            raise ValueError(
                "translated or unavailable message must retain original record"
            )
        if message.translation_status is TranslationStatus.UNAVAILABLE:
            if result.status is not SandboxStatus.PARTIAL:
                raise ValueError(
                    "unavailable translation requires partial result status"
                )
            if message.content != ENGLISH_TRANSLATION_UNAVAILABLE:
                raise ValueError(
                    "unavailable translation must use the exact placeholder"
                )
            if any(
                source.excerpt != ENGLISH_TRANSLATION_UNAVAILABLE
                for source in result.sources
                if source.source_id in message.source_refs
            ):
                raise ValueError(
                    "unavailable translation evidence must use the exact placeholder"
                )
    seen_records: set[str] = set()
    for record in result.original_records:
        if record.speaker_id not in persona_id_set:
            raise ValueError(
                f"original record {record.record_id} references unknown persona"
            )
        if record.source_id not in source_id_set:
            raise ValueError(
                f"original record {record.record_id} references unknown source"
            )
        if len(record.reply_to_record_ids) != len(set(record.reply_to_record_ids)):
            raise ValueError(
                f"original record {record.record_id} has duplicate reply references"
            )
        if set(record.reply_to_record_ids) - seen_records:
            raise ValueError(
                f"original record {record.record_id} has unknown reply reference"
            )
        translated = message_by_id.get(record.record_id)
        if translated is None:
            raise ValueError(
                f"original record {record.record_id} has no public message"
            )
        if translated.persona_id != record.speaker_id:
            raise ValueError(
                f"original record {record.record_id} changed speaker identity"
            )
        if translated.reply_to_message_ids != record.reply_to_record_ids:
            raise ValueError(
                f"original record {record.record_id} changed reply identity"
            )
        source = source_by_record.get(record.record_id)
        if source is None or source.source_id != record.source_id:
            raise ValueError(
                f"original record {record.record_id} changed source identity"
            )
        if record.source_id not in translated.source_refs:
            raise ValueError(
                f"message {record.record_id} does not cite its original source"
            )
        if (
            translated.translation_status is TranslationStatus.ORIGINAL_ENGLISH
            and (
                record.language.casefold() != "english"
                or translated.content != record.content
            )
        ):
            raise ValueError(
                f"message {record.record_id} has invalid original-English provenance"
            )
        seen_records.add(record.record_id)

    if result.original_records and set(record_ids) != set(message_ids):
        raise ValueError("public message and original record identities do not match")
    if result.requested_stakeholder_count != request.stakeholder_count:
        raise ValueError("requested_stakeholder_count does not match request")
    if result.configured_stakeholder_count != len(persona_ids):
        raise ValueError("configured_stakeholder_count does not match personas")
    observed = len({message.persona_id for message in result.messages})
    if result.observed_stakeholder_count != observed:
        raise ValueError("observed_stakeholder_count does not match message authors")
    if result.observed_stakeholder_count > result.configured_stakeholder_count:
        raise ValueError("observed stakeholder count exceeds configured count")
    if result.configured_stakeholder_count > result.requested_stakeholder_count:
        raise ValueError("configured stakeholder count exceeds requested count")

    if result.status is SandboxStatus.COMPLETED:
        if not result.personas or not result.messages or not result.sources:
            raise ValueError(
                "completed result requires personas, messages, and evidence"
            )
        if result.errors:
            raise ValueError("completed result cannot contain errors")
        if result.observed_stakeholder_count != result.requested_stakeholder_count:
            raise ValueError(
                "completed result must observe every requested stakeholder"
            )
        if any(not message.source_refs for message in result.messages):
            raise ValueError("completed result messages require evidence references")
    elif result.status is SandboxStatus.FAILED and not result.errors:
        raise ValueError("failed result requires at least one error")
    elif result.status in {SandboxStatus.PARTIAL, SandboxStatus.CANCELLED}:
        if not result.limitations and not result.errors:
            raise ValueError(
                f"{result.status.value} result requires a limitation or error"
            )


def public_sandbox_result(result: SandboxResult) -> dict[str, Any]:
    """Return the explicit public allowlist, excluding backend-only originals."""
    result = SandboxResult.model_validate(result.model_dump(warnings=False))
    return result.model_dump(mode="json", include=_PUBLIC_RESULT_FIELDS)


def make_example_request() -> SandboxRequest:
    policy_text = (
        "The city will extend late-night transit service for six months and review "
        "ridership, accessibility, worker safety, and operating cost each month."
    )
    return SandboxRequest(
        request_id="request-example-001",
        run_id="run-example-001",
        policy_version="2026-09-10",
        policy_title="Synthetic late-night transit pilot",
        policy_text=policy_text,
        policy_text_sha256=hashlib.sha256(policy_text.encode("utf-8")).hexdigest(),
        personality_seed=(
            "Include practical, safety-focused, and accessibility-focused voices."
        ),
        random_seed=90210,
        stakeholder_count=3,
        test_budget=8,
        context=(
            ContextSource(
                source_id="context-rider-survey",
                title="Synthetic rider survey summary",
                text=(
                    "Authored fixture context: riders report limited transport options "
                    "after midnight."
                ),
                source_uri="https://example.invalid/context/rider-survey",
            ),
        ),
        scenario_setups=(
            ScenarioSetup(
                scenario_id="scenario-late-shift",
                title="Late shift journey",
                circumstances="A rider finishes work after midnight during the pilot.",
                stakeholder_actions=("Ask how often the service runs.",),
            ),
        ),
        target_language="English",
        max_rounds=3,
        timeout_seconds=90,
    )
