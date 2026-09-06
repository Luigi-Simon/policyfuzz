import math
from typing import get_args

import pytest
from pydantic import ValidationError

from app.domain.models import (
    LLMError,
    LLMErrorCode,
    LLMOperation,
    LLMRequest,
    LLMResponse,
)


def make_request(**changes: object) -> LLMRequest:
    values = {
        "operation": "policy_extraction",
        "system_instructions": "trusted-secret-instructions",
        "untrusted_payload_json": '{"policy":"sensitive-payload"}',
        "response_schema": {
            "type": "object",
            "properties": {"rules": {"type": "array"}},
        },
        "response_schema_name": "policy_extraction_v1",
    }
    return LLMRequest(**(values | changes))


def test_llm_contracts_round_trip_through_json() -> None:
    request = make_request(repair_attempt=1)
    response = LLMResponse(output={"rules": [], "accepted": True})
    error = LLMError(
        code="invalid_response", operation="policy_extraction", transport_retries=2
    )

    assert LLMRequest.model_validate_json(request.model_dump_json()) == request
    assert LLMResponse.model_validate_json(response.model_dump_json()) == response
    assert LLMError.model_validate_json(error.model_dump_json()) == error


def test_sensitive_llm_fields_are_absent_from_repr() -> None:
    request = make_request()
    response = LLMResponse(output="sensitive-model-output")

    diagnostic = repr(request) + repr(response)
    assert "trusted-secret-instructions" not in diagnostic
    assert "sensitive-payload" not in diagnostic
    assert "properties" not in diagnostic
    assert "sensitive-model-output" not in diagnostic


@pytest.mark.parametrize(
    ("changes", "safe_message"),
    [
        (
            {"untrusted_payload_json": "private-invalid-json"},
            "payload must be a JSON object",
        ),
        ({"untrusted_payload_json": "[1, 2]"}, "payload must be a JSON object"),
        (
            {"untrusted_payload_json": '{"private":NaN}'},
            "payload must contain finite JSON values",
        ),
        (
            {"untrusted_payload_json": '{"private":1e309}'},
            "payload must contain finite JSON values",
        ),
        (
            {"response_schema": {"type": "array"}},
            "response schema root must be an object",
        ),
        (
            {"response_schema": {"type": "object", "x": math.inf}},
            "response schema must contain finite JSON values",
        ),
    ],
)
def test_request_rejects_invalid_json_with_safe_validation_messages(
    changes: dict[str, object], safe_message: str
) -> None:
    with pytest.raises(ValidationError) as raised:
        make_request(**changes)

    messages = [item["msg"] for item in raised.value.errors(include_input=False)]
    assert messages == [f"Value error, {safe_message}"]
    assert "private" not in messages[0]
    assert "private" not in str(raised.value)


@pytest.mark.parametrize("output", [{"score": math.nan}, {"score": math.inf}])
def test_response_rejects_nonfinite_structured_output(output: dict[str, float]) -> None:
    output = {"private-model-value": next(iter(output.values()))}
    with pytest.raises(
        ValidationError, match="output must contain finite JSON values"
    ) as raised:
        LLMResponse(output=output)
    assert "private-model-value" not in str(raised.value)


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("operation", "chat"),
        ("repair_attempt", 2),
        ("response_schema_name", "contains spaces"),
        ("response_schema_name", "x" * 65),
    ],
)
def test_request_rejects_values_outside_bounded_contract(
    field: str, value: object
) -> None:
    with pytest.raises(ValidationError):
        make_request(**{field: value})


def test_error_contract_has_exact_safe_codes_and_bounds() -> None:
    assert set(get_args(LLMOperation)) == {
        "policy_extraction",
        "invariant_suggestion",
        "scenario_generation",
        "targeted_scenario_generation",
        "revision_proposal",
    }
    assert set(get_args(LLMErrorCode)) == {
        "timeout",
        "rate_limit",
        "authentication",
        "invalid_request",
        "unavailable",
        "invalid_response",
        "refusal",
        "script_exhausted",
    }
    with pytest.raises(ValidationError):
        LLMError(code="provider_error", operation="policy_extraction")
    with pytest.raises(ValidationError):
        LLMError(code="timeout", operation="policy_extraction", transport_retries=3)


def test_raw_response_output_deliberately_allows_malformed_json() -> None:
    assert LLMResponse(output="{malformed").output == "{malformed"
