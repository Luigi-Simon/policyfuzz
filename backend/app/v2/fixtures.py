"""Deterministic, clearly labelled Sandbox fixtures with no provider calls."""

from __future__ import annotations

from typing import Literal

from .contracts import (
    ENGLISH_TRANSLATION_UNAVAILABLE,
    ExecutionMode,
    OriginalRecord,
    Persona,
    SandboxMessage,
    SandboxRequest,
    SandboxResult,
    SandboxStatus,
    SourceEvidence,
    TranslationStatus,
    make_example_request,
    request_fingerprint,
)

FixtureName = Literal["completed", "partial_translation_unavailable"]


class FixtureSandboxService:
    """Offline fixture service; it never substitutes for recorded or live work."""

    def __init__(self, fixture_name: FixtureName = "completed") -> None:
        if fixture_name not in {"completed", "partial_translation_unavailable"}:
            raise ValueError(f"unknown fixture: {fixture_name}")
        self.fixture_name = fixture_name

    async def run(self, request: SandboxRequest) -> SandboxResult:
        request = SandboxRequest.model_validate(request.model_dump(warnings=False))
        partial = self.fixture_name == "partial_translation_unavailable"
        personas, messages, sources, original_records = _fixture_records(
            request.stakeholder_count,
            partial=partial,
        )
        limitations = [
            "Authored synthetic fixture dialogue; it does not analyze the supplied "
            "policy or personality seed, and no live Sandbox was executed."
        ]
        if partial:
            limitations.append(
                "English translation unavailable for one preserved original record."
            )
        return SandboxResult(
            request_id=request.request_id,
            run_id=request.run_id,
            policy_version=request.policy_version,
            policy_title=request.policy_title,
            policy_text_sha256=request.policy_text_sha256,
            request_fingerprint=request_fingerprint(request),
            execution_mode=ExecutionMode.FIXTURE,
            status=(SandboxStatus.PARTIAL if partial else SandboxStatus.COMPLETED),
            requested_stakeholder_count=request.stakeholder_count,
            configured_stakeholder_count=len(personas),
            observed_stakeholder_count=len(personas),
            personas=personas,
            messages=messages,
            sources=sources,
            limitations=tuple(limitations),
            original_records=original_records,
        )


def _fixture_records(
    count: int,
    *,
    partial: bool,
) -> tuple[
    tuple[Persona, ...],
    tuple[SandboxMessage, ...],
    tuple[SourceEvidence, ...],
    tuple[OriginalRecord, ...],
]:
    persona_details = [
        (
            "Night-shift rider",
            "A hospital worker who depends on transit after midnight.",
        ),
        (
            "Transit operator",
            "A driver focused on safe schedules and reliable breaks.",
        ),
        (
            "Accessibility advocate",
            "A rider who evaluates step-free late-night journeys.",
        ),
    ]
    translated_content = [
        "The rider asks the city to retain late-night service.",
        "Late-night service needs adequate rest time and clear safety procedures.",
        "Every pilot stop should preserve an accessible route.",
    ]
    original_content = [
        "乘客要求保留夜间服务。",
        "夜间服务需要足够的休息时间和清晰的安全程序。",
        "Every pilot stop should preserve an accessible route.",
    ]
    source_titles = [
        "Rider response",
        "Operator response",
        "Accessibility response",
    ]
    source_excerpts = [
        "The rider requests continued late-night service.",
        "The operator requests rest time and clear safety procedures.",
        "The advocate requests an accessible route at every stop.",
    ]
    original_languages = ["Chinese", "Chinese", "English"]
    while len(persona_details) < count:
        number = len(persona_details) + 1
        persona_details.append(
            (
                f"Synthetic stakeholder {number}",
                "An authored fixture participant used only to exercise count handling.",
            )
        )
        translated_content.append(
            f"Authored fixture response from synthetic stakeholder {number}."
        )
        original_content.append(translated_content[-1])
        source_titles.append(f"Synthetic stakeholder {number} response")
        source_excerpts.append(translated_content[-1])
        original_languages.append("English")

    unavailable_index = min(1, count - 1) if partial else None
    personas: list[Persona] = []
    messages: list[SandboxMessage] = []
    sources: list[SourceEvidence] = []
    originals: list[OriginalRecord] = []
    for index in range(count):
        number = index + 1
        persona_id = f"persona-{number:03d}"
        message_id = f"message-{number:03d}"
        source_id = f"source-{number:03d}"
        reply_ids = () if index == 0 else ("message-001",)
        is_unavailable = index == unavailable_index
        content = (
            ENGLISH_TRANSLATION_UNAVAILABLE
            if is_unavailable
            else translated_content[index]
        )
        excerpt = (
            ENGLISH_TRANSLATION_UNAVAILABLE
            if is_unavailable
            else source_excerpts[index]
        )
        if is_unavailable:
            translation_status = TranslationStatus.UNAVAILABLE
        elif original_languages[index] == "English":
            translation_status = TranslationStatus.ORIGINAL_ENGLISH
        else:
            translation_status = TranslationStatus.TRANSLATED
        name, description = persona_details[index]
        personas.append(
            Persona(
                persona_id=persona_id,
                display_name=name,
                description=description,
            )
        )
        messages.append(
            SandboxMessage(
                message_id=message_id,
                sequence=number,
                persona_id=persona_id,
                content=content,
                translation_status=translation_status,
                source_refs=(source_id,),
                reply_to_message_ids=reply_ids,
                round_number=1,
            )
        )
        sources.append(
            SourceEvidence(
                source_id=source_id,
                record_id=message_id,
                title=source_titles[index],
                excerpt=excerpt,
            )
        )
        originals.append(
            OriginalRecord(
                record_id=message_id,
                speaker_id=persona_id,
                source_id=source_id,
                content=original_content[index],
                language=original_languages[index],
                reply_to_record_ids=reply_ids,
            )
        )
    return tuple(personas), tuple(messages), tuple(sources), tuple(originals)


__all__ = ["FixtureName", "FixtureSandboxService", "make_example_request"]
