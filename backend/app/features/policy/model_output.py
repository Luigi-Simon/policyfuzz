"""Sanitized parsing and strict validation for model-generated JSON."""

from __future__ import annotations

import json
from typing import TypeVar

from pydantic import BaseModel, ValidationError


MAX_MODEL_OUTPUT_CHARS = 100_000
ModelT = TypeVar("ModelT", bound=BaseModel)
ValidationIssue = tuple[str, str]


class ModelOutputValidationError(ValueError):
    """A safe error containing validation locations and codes, never values."""

    def __init__(
        self,
        code: str,
        *,
        issues: tuple[ValidationIssue, ...] = (),
    ) -> None:
        self.code = code
        self.issues = issues
        message = code
        if issues:
            message += ": " + ", ".join(
                f"{path}={issue_type}" for path, issue_type in issues
            )
        super().__init__(message)


def _format_location(location: tuple[object, ...]) -> str:
    return ".".join(str(part) for part in location) or "$"


def parse_typed_output(
    raw_output: str,
    *,
    response_model: type[ModelT],
    max_characters: int = MAX_MODEL_OUTPUT_CHARS,
) -> ModelT:
    """Parse model JSON and validate it strictly against a Pydantic model.

    Raw output, invalid values, policy text, and Pydantic input snapshots are
    deliberately excluded from all raised errors.
    """

    if not isinstance(raw_output, str):
        raise ModelOutputValidationError("INVALID_OUTPUT_TYPE")
    if not raw_output.strip():
        raise ModelOutputValidationError("EMPTY_MODEL_OUTPUT")
    if max_characters < 1:
        raise ValueError("max_characters must be positive")
    if len(raw_output) > max_characters:
        raise ModelOutputValidationError("MODEL_OUTPUT_TOO_LARGE")

    try:
        json.loads(raw_output)
    except (json.JSONDecodeError, RecursionError) as exc:
        raise ModelOutputValidationError("INVALID_JSON") from exc

    try:
        # Validate from JSON so JSON arrays may populate tuple fields while
        # scalar coercions (for example "5000" to 5000) remain disabled.
        return response_model.model_validate_json(raw_output, strict=True)
    except ValidationError as exc:
        issues = tuple(
            sorted(
                {
                    (_format_location(tuple(error["loc"])), str(error["type"]))
                    for error in exc.errors(include_url=False, include_context=False, include_input=False)
                }
            )
        )
        raise ModelOutputValidationError(
            "SCHEMA_VALIDATION_FAILED",
            issues=issues,
        ) from exc
