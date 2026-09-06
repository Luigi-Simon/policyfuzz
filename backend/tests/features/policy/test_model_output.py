from typing import Literal

import pytest
from pydantic import BaseModel, ConfigDict

from app.core.errors import LLMTransportError
from app.core.fakes import ScriptedLLMClient
from app.domain.models import LLMError, LLMRequest, LLMResponse
from app.features.policy.model_output import (
    MAX_MODEL_OUTPUT_CHARS,
    ModelOutputValidationError,
    complete_typed,
    parse_typed_output,
)


class ExampleRule(BaseModel):
    model_config = ConfigDict(extra="forbid")

    field: Literal["amount_minor"]
    value: int


class ExampleExtraction(BaseModel):
    model_config = ConfigDict(extra="forbid")

    rules: tuple[ExampleRule, ...]


def test_valid_json_returns_typed_model() -> None:
    result = parse_typed_output(
        '{"rules":[{"field":"amount_minor","value":5000}]}',
        response_model=ExampleExtraction,
    )

    assert isinstance(result, ExampleExtraction)
    assert result.rules[0].value == 5000


@pytest.mark.parametrize("raw_output", ["", "   ", "\n\t"])
def test_empty_model_output_is_rejected(raw_output: str) -> None:
    with pytest.raises(ModelOutputValidationError, match="EMPTY_MODEL_OUTPUT"):
        parse_typed_output(raw_output, response_model=ExampleExtraction)


def test_malformed_json_is_rejected_without_echoing_output() -> None:
    secret = "CONFIDENTIAL-policy-clause"
    with pytest.raises(ModelOutputValidationError) as exc_info:
        parse_typed_output(
            '{"rules": invalid, "secret": "' + secret + '"}',
            response_model=ExampleExtraction,
        )

    assert exc_info.value.code == "INVALID_JSON"
    assert secret not in str(exc_info.value)


@pytest.mark.parametrize(
    ("payload", "expected_path", "expected_type"),
    [
        ('{"rules":[{"field":"amount_minor"}]}', "rules.0.value", "missing"),
        (
            '{"rules":[{"field":"amount_minor","value":"5000"}]}',
            "rules.0.value",
            "int_type",
        ),
        ('{"rules":[],"verdict":"PASS"}', "$", "extra_forbidden"),
    ],
)
def test_schema_errors_return_only_paths_and_codes(
    payload: str,
    expected_path: str,
    expected_type: str,
) -> None:
    with pytest.raises(ModelOutputValidationError) as exc_info:
        parse_typed_output(payload, response_model=ExampleExtraction)

    assert exc_info.value.code == "SCHEMA_VALIDATION_FAILED"
    assert (expected_path, expected_type) in exc_info.value.issues


def test_schema_error_does_not_include_raw_values() -> None:
    secret = "PRIVATE-employee-information"
    payload = '{"rules":[{"field":"' + secret + '","value":5000}]}'

    with pytest.raises(ModelOutputValidationError) as exc_info:
        parse_typed_output(payload, response_model=ExampleExtraction)

    assert secret not in str(exc_info.value)
    assert secret not in repr(exc_info.value)


def test_non_string_output_is_rejected() -> None:
    with pytest.raises(ModelOutputValidationError, match="INVALID_OUTPUT_TYPE"):
        parse_typed_output({"rules": []}, response_model=ExampleExtraction)  # type: ignore[arg-type]


def test_oversized_output_is_rejected_before_json_parsing() -> None:
    with pytest.raises(ModelOutputValidationError, match="MODEL_OUTPUT_TOO_LARGE"):
        parse_typed_output(
            "x" * (MAX_MODEL_OUTPUT_CHARS + 1), response_model=ExampleExtraction
        )


def test_validation_issues_are_sorted_deterministically() -> None:
    payload = '{"rules":[{"field":"wrong","extra":true}]}'

    with pytest.raises(ModelOutputValidationError) as exc_info:
        parse_typed_output(payload, response_model=ExampleExtraction)

    assert exc_info.value.issues == tuple(sorted(exc_info.value.issues))


def _request(*, payload: str = '{"policy":"UNTRUSTED-secret"}') -> LLMRequest:
    return LLMRequest(
        operation="policy_extraction",
        system_instructions="Return the requested JSON object.",
        untrusted_payload_json=payload,
        response_schema=ExampleExtraction.model_json_schema(),
        response_schema_name="ExampleExtraction",
    )


@pytest.mark.asyncio
async def test_complete_typed_repairs_invalid_output_exactly_once() -> None:
    llm = ScriptedLLMClient(
        (
            LLMResponse(output={"rules": "invalid"}),
            LLMResponse(output={"rules": [{"field": "amount_minor", "value": 5000}]}),
        )
    )

    result = await complete_typed(
        llm,
        request=_request(),
        response_model=ExampleExtraction,
        repair_operation="policy_extraction",
    )

    assert result.rules[0].value == 5000
    assert [item.repair_attempt for item in llm.requests] == [0, 1]
    assert llm.requests[1].operation == "policy_extraction"
    assert "UNTRUSTED-secret" not in llm.requests[1].system_instructions


@pytest.mark.asyncio
async def test_complete_typed_stops_after_one_repair_with_safe_error() -> None:
    secret = "PRIVATE-model-output"
    llm = ScriptedLLMClient(
        (
            LLMResponse(output={"rules": [{"field": secret, "value": 1}]}),
            LLMResponse(output="not-json-" + secret),
        )
    )

    with pytest.raises(ModelOutputValidationError) as exc_info:
        await complete_typed(
            llm,
            request=_request(),
            response_model=ExampleExtraction,
            repair_operation="policy_extraction",
        )

    assert exc_info.value.repair_attempted is True
    assert len(llm.requests) == 2
    assert secret not in str(exc_info.value)
    assert secret not in llm.requests[1].system_instructions


def _exception_text(error: BaseException) -> str:
    seen: set[int] = set()
    pending: list[BaseException] = [error]
    text: list[str] = []
    while pending:
        current = pending.pop()
        if id(current) in seen:
            continue
        seen.add(id(current))
        text.extend((str(current), repr(current)))
        if current.__cause__ is not None:
            pending.append(current.__cause__)
        if current.__context__ is not None:
            pending.append(current.__context__)
    return "\n".join(text)


@pytest.mark.asyncio
async def test_repair_transport_failure_has_no_private_validation_context() -> None:
    secret = "PRIVATE_POLICY_FRAGMENT"
    llm = ScriptedLLMClient(
        (
            LLMResponse(output={"rules": [], secret: 1}),
            LLMTransportError(LLMError(code="timeout", operation="policy_extraction")),
        )
    )

    with pytest.raises(LLMTransportError) as exc_info:
        await complete_typed(
            llm,
            request=_request(),
            response_model=ExampleExtraction,
            repair_operation="policy_extraction",
        )

    assert secret not in _exception_text(exc_info.value)


@pytest.mark.asyncio
async def test_premarked_repair_sanitizes_private_validation_paths() -> None:
    secret = "PRIVATE_POLICY_FRAGMENT"
    request = _request().model_copy(update={"repair_attempt": 1})
    llm = ScriptedLLMClient((LLMResponse(output={"rules": [], secret: 1}),))

    with pytest.raises(ModelOutputValidationError) as exc_info:
        await complete_typed(
            llm,
            request=request,
            response_model=ExampleExtraction,
            repair_operation="policy_extraction",
        )

    assert exc_info.value.repair_attempted is True
    assert secret not in _exception_text(exc_info.value)


def test_parse_error_has_no_private_pydantic_context() -> None:
    secret = "PRIVATE_POLICY_FRAGMENT"

    with pytest.raises(ModelOutputValidationError) as exc_info:
        parse_typed_output(
            '{"rules":[],"' + secret + '":1}',
            response_model=ExampleExtraction,
        )

    assert secret not in _exception_text(exc_info.value)
