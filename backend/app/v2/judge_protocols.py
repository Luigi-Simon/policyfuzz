"""Async port for the friend's Judge Agent implementation."""

from typing import Protocol, runtime_checkable

from .judge_contracts import JudgeRequest, JudgeResult


@runtime_checkable
class JudgeService(Protocol):
    async def run(self, request: JudgeRequest) -> JudgeResult:
        """Return evidence-grounded English advice preserving request identity."""
        ...
