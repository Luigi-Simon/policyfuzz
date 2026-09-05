from typing import Literal

import pytest
from pydantic import BaseModel, ConfigDict

from app.features.policy.model_output import (
    MAX_MODEL_OUTPUT_CHARS,
    ModelOutputValidationError,
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
        ('{"rules":[{"field":"amount_minor","value":"5000"}]}', "rules.0.value", "int_type"),
        ('{"rules":[],"verdict":"PASS"}', "verdict", "extra_forbidden"),
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
        parse_typed_output("x" * (MAX_MODEL_OUTPUT_CHARS + 1), response_model=ExampleExtraction)


def test_validation_issues_are_sorted_deterministically() -> None:
    payload = '{"rules":[{"field":"wrong","extra":true}]}'

    with pytest.raises(ModelOutputValidationError) as exc_info:
        parse_typed_output(payload, response_model=ExampleExtraction)

    assert exc_info.value.issues == tuple(sorted(exc_info.value.issues))
