"""Provider-neutral LLM transport retry policy."""

import asyncio
from collections.abc import Awaitable, Callable

from app.core.errors import LLMTransportError
from app.domain.models import LLMError, LLMRequest, LLMResponse
from app.domain.protocols import LLMClient

_RETRYABLE_CODES = frozenset({"timeout", "rate_limit"})
_BACKOFF_SECONDS = (1.0, 2.0)


class RetryingLLMClient:
    """Apply the fixed per-request transport budget around one LLM client."""

    def __init__(
        self,
        delegate: LLMClient,
        *,
        sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
    ) -> None:
        if isinstance(delegate, RetryingLLMClient):
            raise TypeError("retrying LLM clients cannot be nested")
        self._delegate = delegate
        self._sleep = sleep

    async def complete_json(self, request: LLMRequest) -> LLMResponse:
        source = LLMRequest.model_validate(request).model_copy(deep=True)
        retries = 0
        while True:
            try:
                response = await self._delegate.complete_json(
                    source.model_copy(deep=True)
                )
            except LLMTransportError as error:
                if error.error.code not in _RETRYABLE_CODES or retries == 2:
                    terminal = LLMError(
                        code=error.error.code,
                        operation=source.operation,
                        transport_retries=retries,
                    )
                    raise LLMTransportError(terminal) from None
                await self._sleep(_BACKOFF_SECONDS[retries])
                retries += 1
                continue
            usage = response.usage.model_copy(update={"transport_retries": retries})
            return response.model_copy(deep=True, update={"usage": usage})


__all__ = ["RetryingLLMClient"]
