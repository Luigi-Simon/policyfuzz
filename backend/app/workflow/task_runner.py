"""Owned, awaitable jobs with monotonic expiry and explicit cancellation drain."""

import asyncio
from collections.abc import Awaitable, Callable
from typing import Protocol, TypeVar

from app.workflow.errors import InvalidRunCommandError, RunNotFoundError
from app.workflow.store import RunStore
from app.workflow.types import Clock

T = TypeVar("T")


class TaskRunner(Protocol):
    def start(self) -> None: ...
    def submit(
        self, run_id: str, work: Callable[[], Awaitable[T]]
    ) -> asyncio.Task[T]: ...
    async def run(self, run_id: str, work: Callable[[], Awaitable[T]]) -> T: ...
    async def cancel(self, run_id: str) -> None: ...
    async def sweep(self) -> None: ...
    async def aclose(self) -> None: ...


class AsyncTaskRunner:
    def __init__(
        self,
        store: RunStore,
        clock: Clock,
        *,
        cleanup: Callable[[str], None] | None = None,
    ):
        self.store, self.clock = store, clock
        self._jobs: dict[str, set[asyncio.Task]] = {}
        self._runs: set[str] = set()
        self._cleanup = cleanup or (lambda run_id: None)
        self._reaper: asyncio.Task | None = None
        self._closed = False

    @property
    def pending_count(self) -> int:
        return sum(not job.done() for jobs in self._jobs.values() for job in jobs)

    def start(self) -> None:
        if self._closed:
            raise InvalidRunCommandError()
        if self._reaper is None:
            self._reaper = asyncio.create_task(self._expire_loop())

    async def _expire_loop(self) -> None:
        while True:
            await asyncio.sleep(0.25)
            await self.sweep()

    def submit(self, run_id: str, work: Callable[[], Awaitable[T]]) -> asyncio.Task[T]:
        if self._closed:
            raise InvalidRunCommandError()
        self._runs.add(run_id)
        task = asyncio.create_task(work())
        self._jobs.setdefault(run_id, set()).add(task)

        def completed(job):
            self._jobs.get(run_id, set()).discard(job)
            if not self._jobs.get(run_id):
                self._jobs.pop(run_id, None)
            if not job.cancelled():
                # Retrieve background failures without logging sensitive exceptions.
                job.exception()

        task.add_done_callback(completed)
        return task

    async def run(self, run_id: str, work: Callable[[], Awaitable[T]]) -> T:
        task = self.submit(run_id, work)
        try:
            return await task
        except asyncio.CancelledError:
            if not asyncio.current_task().cancelling():
                raise RunNotFoundError() from None
            raise

    async def drain(self, run_id: str) -> None:
        jobs = tuple(self._jobs.get(run_id, ()))
        if jobs:
            await asyncio.gather(*jobs, return_exceptions=True)

    async def cancel(self, run_id: str) -> None:
        jobs = tuple(self._jobs.pop(run_id, ()))
        for job in jobs:
            job.cancel()
        if jobs:
            await asyncio.gather(*jobs, return_exceptions=True)
        self._runs.discard(run_id)
        self._cleanup(run_id)

    async def sweep(self) -> None:
        await self.store.purge_expired(self.clock.monotonic())
        for run_id in tuple(self._runs):
            try:
                await self.store.get(run_id)
            except RunNotFoundError:
                await self.cancel(run_id)

    async def aclose(self) -> None:
        if self._closed:
            return
        self._closed = True
        if self._reaper is not None:
            self._reaper.cancel()
            await asyncio.gather(self._reaper, return_exceptions=True)
        # Invalidate writes before cancellation so jobs cannot recreate data.
        await self.store.aclose()
        for run_id in tuple(self._runs):
            await self.cancel(run_id)
