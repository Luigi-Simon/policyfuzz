from app.core.errors import (
    LLMConfigurationError,
    LLMTransportError,
    to_public_error,
)
from app.domain.models import LLMError


def transport(code: str) -> LLMTransportError:
    return LLMTransportError(LLMError(code=code, operation="policy_extraction"))


def test_transport_error_exposes_only_typed_safe_error() -> None:
    error = transport("timeout")

    assert error.error == LLMError(code="timeout", operation="policy_extraction")
    assert str(error) == "llm_transport_error:timeout"
    assert "provider" not in repr(error).lower()


def test_known_errors_map_to_fixed_public_errors() -> None:
    assert to_public_error(transport("invalid_response")).model_dump() == {
        "schema_version": "1.0",
        "code": "MALFORMED_MODEL_OUTPUT",
        "message": "The model returned malformed output.",
        "error_id": None,
        "retryable": False,
    }
    assert to_public_error(transport("timeout")).model_dump() == {
        "schema_version": "1.0",
        "code": "PROVIDER_UNAVAILABLE",
        "message": "The model provider is unavailable.",
        "error_id": None,
        "retryable": True,
    }
    assert to_public_error(transport("authentication")).retryable is False
    assert to_public_error(LLMConfigurationError()).model_dump() == {
        "schema_version": "1.0",
        "code": "PROVIDER_UNAVAILABLE",
        "message": "The model provider is not configured.",
        "error_id": None,
        "retryable": False,
    }


def test_unknown_exception_maps_to_fixed_internal_error_without_leaking_input() -> None:
    public = to_public_error(RuntimeError("private provider response"))

    assert public.code == "INTERNAL_ERROR"
    assert public.message == "An internal error occurred."
    assert "private" not in repr(public)
