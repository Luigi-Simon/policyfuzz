"""Safe infrastructure exceptions and their public error projection."""

from app.domain.models import LLMError, PublicError


class LLMTransportError(Exception):
    """A provider-neutral model transport failure with no free-form detail."""

    __slots__ = ("_error",)

    def __init__(self, error: LLMError) -> None:
        validated = LLMError.model_validate(error)
        self._error = validated
        super().__init__(f"llm_transport_error:{validated.code}")

    @property
    def error(self) -> LLMError:
        return self._error


class LLMConfigurationError(Exception):
    """A fixed diagnostic for unusable live-provider configuration."""

    def __init__(self) -> None:
        super().__init__("llm_configuration_error")


def to_public_error(error: Exception) -> PublicError:
    """Project internal exceptions to fixed, non-sensitive public errors."""

    if isinstance(error, LLMConfigurationError):
        return PublicError(
            code="PROVIDER_UNAVAILABLE",
            message="The model provider is not configured.",
            error_id="provider-configuration",
            retryable=False,
        )
    if isinstance(error, LLMTransportError):
        if error.error.code == "invalid_response":
            return PublicError(
                code="MALFORMED_MODEL_OUTPUT",
                message="The model returned malformed output.",
                retryable=False,
            )
        return PublicError(
            code="PROVIDER_UNAVAILABLE",
            message="The model provider is unavailable.",
            error_id=f"provider-{error.error.code.replace('_', '-')}",
            retryable=error.error.code in {"timeout", "rate_limit", "unavailable"},
        )
    return PublicError(
        code="INTERNAL_ERROR",
        message="An internal error occurred.",
        retryable=False,
    )


__all__ = ["LLMConfigurationError", "LLMTransportError", "to_public_error"]
