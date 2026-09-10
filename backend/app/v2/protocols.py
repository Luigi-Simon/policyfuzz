"""Adapter protocols shared by v2 core and Sandbox implementations."""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from .contracts import SandboxRequest, SandboxResult


@runtime_checkable
class SandboxService(Protocol):
    async def run(self, request: SandboxRequest) -> SandboxResult:
        """Execute a Sandbox request without changing its identity."""
        ...
