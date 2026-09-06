"""Race-safe in-memory storage for private workflow run snapshots."""

import asyncio
import inspect
import math
from dataclasses import dataclass
from datetime import datetime, timedelta

from pydantic import ValidationError

from app.domain.models import RunAction, RunRecord

from .errors import (
    ConcurrentRunMutationError,
    InvalidRunCommandError,
    RunNotFoundError,
)
from .types import Clock, RunMutation, StoredRun


@dataclass(slots=True)
class _Entry:
    record: StoredRun
    deadline: float
    lock: asyncio.Lock


def _snapshot(record: StoredRun) -> StoredRun:
    return StoredRun.model_validate(record.model_dump(mode="python"))


class RunStore:
    """Store independent snapshots with per-run CAS mutation locks."""

    def __init__(self, clock: Clock, ttl_seconds: int = 3_600) -> None:
        if (
            isinstance(ttl_seconds, bool)
            or not isinstance(ttl_seconds, int)
            or not 1 <= ttl_seconds <= 3_600
        ):
            raise InvalidRunCommandError
        self._clock = clock
        self._ttl_seconds = ttl_seconds
        self._entries: dict[str, _Entry] = {}
        self._entries_lock = asyncio.Lock()
        self._closed = False

    def _monotonic_now(self) -> float:
        value = self._clock.monotonic()
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise InvalidRunCommandError
        result = float(value)
        if not math.isfinite(result):
            raise InvalidRunCommandError
        return result

    def _wall_now(self) -> datetime:
        value = self._clock.wall_now()
        if not isinstance(value, datetime) or value.utcoffset() is None:
            raise InvalidRunCommandError
        return value

    async def create(self, record: RunRecord) -> StoredRun:
        """Create a run with store-owned wall and monotonic expiry."""

        if not isinstance(record, RunRecord):
            raise InvalidRunCommandError
        wall_now = self._wall_now()
        now_monotonic = self._monotonic_now()
        deadline = now_monotonic + self._ttl_seconds
        if not math.isfinite(deadline) or deadline <= now_monotonic:
            raise InvalidRunCommandError
        try:
            stored = StoredRun.model_validate(
                record.model_dump(mode="python")
                | {
                    "created_at": wall_now,
                    "expires_at": wall_now + timedelta(seconds=self._ttl_seconds),
                }
            )
        except (TypeError, ValueError, ValidationError):
            raise InvalidRunCommandError from None
        entry = _Entry(
            record=_snapshot(stored),
            deadline=deadline,
            lock=asyncio.Lock(),
        )
        async with self._entries_lock:
            if self._closed:
                raise InvalidRunCommandError
            current = self._entries.get(stored.run_id)
            if current is not None and current.deadline > now_monotonic:
                raise InvalidRunCommandError
            if current is not None:
                self._entries.pop(stored.run_id, None)
            self._entries[stored.run_id] = entry
        return _snapshot(stored)

    async def _capture(self, run_id: str) -> _Entry:
        async with self._entries_lock:
            if self._closed:
                raise RunNotFoundError
            entry = self._entries.get(run_id)
            if entry is None:
                raise RunNotFoundError
            return entry

    async def _current_record(self, run_id: str, entry: _Entry) -> StoredRun:
        async with self._entries_lock:
            if self._closed or self._entries.get(run_id) is not entry:
                raise RunNotFoundError
            if entry.deadline <= self._monotonic_now():
                self._entries.pop(run_id, None)
                raise RunNotFoundError
            return _snapshot(entry.record)

    async def get(self, run_id: str) -> StoredRun:
        """Read an independent snapshot, removing it first when expired."""

        entry = await self._capture(run_id)
        async with entry.lock:
            return await self._current_record(run_id, entry)

    async def mutate(
        self,
        run_id: str,
        expected_version: int,
        change: RunMutation,
    ) -> StoredRun:
        """Apply one synchronous mutation when the expected version matches."""

        if (
            isinstance(expected_version, bool)
            or not isinstance(expected_version, int)
            or expected_version < 0
            or not callable(change)
        ):
            raise InvalidRunCommandError
        entry = await self._capture(run_id)
        async with entry.lock:
            current = await self._current_record(run_id, entry)
            if current.version != expected_version:
                from .state_machine import allowed_actions

                raise ConcurrentRunMutationError(
                    current_stage=current.stage,
                    allowed_actions=allowed_actions(current.stage),
                )
            candidate = change(_snapshot(current))
            if inspect.isawaitable(candidate):
                close = getattr(candidate, "close", None)
                if callable(close):
                    close()
                raise InvalidRunCommandError(
                    current_stage=current.stage,
                    allowed_actions=self._actions_for(current),
                )
            if not isinstance(candidate, StoredRun):
                raise InvalidRunCommandError(
                    current_stage=current.stage,
                    allowed_actions=self._actions_for(current),
                )
            try:
                validated = _snapshot(candidate)
            except (TypeError, ValueError, ValidationError):
                raise InvalidRunCommandError(
                    current_stage=current.stage,
                    allowed_actions=self._actions_for(current),
                ) from None
            if any(
                getattr(validated, field) != getattr(current, field)
                for field in ("run_id", "manifest", "created_at", "expires_at")
            ):
                raise InvalidRunCommandError(
                    current_stage=current.stage,
                    allowed_actions=self._actions_for(current),
                )
            try:
                updated = StoredRun.model_validate(
                    validated.model_dump(mode="python")
                    | {"version": current.version + 1}
                )
            except (TypeError, ValueError, ValidationError):
                raise InvalidRunCommandError(
                    current_stage=current.stage,
                    allowed_actions=self._actions_for(current),
                ) from None
            async with self._entries_lock:
                if self._closed or self._entries.get(run_id) is not entry:
                    raise RunNotFoundError
                if entry.deadline <= self._monotonic_now():
                    self._entries.pop(run_id, None)
                    raise RunNotFoundError
                entry.record = _snapshot(updated)
            return _snapshot(updated)

    @staticmethod
    def _actions_for(record: StoredRun) -> tuple[RunAction, ...]:
        from .state_machine import allowed_actions

        return allowed_actions(record.stage)

    async def delete(self, run_id: str) -> None:
        """Remove a run immediately without waiting for an old per-run lock."""

        async with self._entries_lock:
            if self._closed or self._entries.pop(run_id, None) is None:
                raise RunNotFoundError

    async def purge_expired(self, now_monotonic: float) -> int:
        """Remove runs whose private monotonic deadline has elapsed."""

        if isinstance(now_monotonic, bool) or not isinstance(
            now_monotonic, (int, float)
        ):
            raise InvalidRunCommandError
        now = float(now_monotonic)
        if not math.isfinite(now):
            raise InvalidRunCommandError
        async with self._entries_lock:
            if self._closed:
                return 0
            expired = [
                run_id
                for run_id, entry in self._entries.items()
                if entry.deadline <= now
            ]
            for run_id in expired:
                self._entries.pop(run_id, None)
            return len(expired)

    async def aclose(self) -> None:
        """Release all run data and permanently close the store."""

        async with self._entries_lock:
            self._closed = True
            self._entries.clear()
