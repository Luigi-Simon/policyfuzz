"""Private run state and clock types used by workflow infrastructure."""

from collections.abc import Callable
from datetime import UTC, datetime
from time import monotonic as system_monotonic
from typing import Annotated, Protocol

from pydantic import Field

from app.domain.models import CreateRunRequest, PendingConfirmation, RunRecord


class StoredRun(RunRecord):
    """Server-held run data that is never projected directly onto the wire."""

    version: Annotated[int, Field(ge=0)] = 0
    source_request: CreateRunRequest | None = Field(default=None, repr=False)
    pending_confirmation: PendingConfirmation | None = None


class Clock(Protocol):
    """Separate display time from elapsed-time expiry."""

    def wall_now(self) -> datetime: ...

    def monotonic(self) -> float: ...


class SystemClock:
    """Production clock using UTC wall time and a monotonic elapsed timer."""

    def wall_now(self) -> datetime:
        return datetime.now(UTC)

    def monotonic(self) -> float:
        return system_monotonic()


RunMutation = Callable[[StoredRun], StoredRun]
