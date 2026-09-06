"""Deterministic fake infrastructure for offline tests and cached workflows."""

from collections import deque
from collections.abc import Iterable

from app.core.errors import LLMTransportError
from app.domain.models import LLMError, LLMRequest, LLMResponse

ScriptedOutcome = LLMResponse | LLMTransportError


def _copy_outcome(outcome: ScriptedOutcome) -> ScriptedOutcome:
    if isinstance(outcome, LLMResponse):
        return outcome.model_copy(deep=True)
    if isinstance(outcome, LLMTransportError):
        return LLMTransportError(outcome.error.model_copy(deep=True))
    raise TypeError("scripted outcomes must be typed LLM results")


class ScriptedLLMClient:
    """Consume a finite typed script while recording independent request snapshots."""

    def __init__(self, outcomes: Iterable[ScriptedOutcome] = ()) -> None:
        self._outcomes = deque(_copy_outcome(outcome) for outcome in outcomes)
        self.requests: list[LLMRequest] = []

    def queue(self, outcome: ScriptedOutcome) -> None:
        self._outcomes.append(_copy_outcome(outcome))

    async def complete_json(self, request: LLMRequest) -> LLMResponse:
        snapshot = LLMRequest.model_validate(request).model_copy(deep=True)
        self.requests.append(snapshot)
        if not self._outcomes:
            raise LLMTransportError(
                LLMError(code="script_exhausted", operation=snapshot.operation)
            ) from None
        outcome = self._outcomes.popleft()
        if isinstance(outcome, LLMTransportError):
            rebound = outcome.error.model_copy(update={"operation": snapshot.operation})
            raise LLMTransportError(rebound) from None
        return outcome.model_copy(deep=True)


__all__ = ["ScriptedLLMClient", "ScriptedOutcome"]
