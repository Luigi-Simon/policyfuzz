"""Stateless Orchestrator Agent entry point for the v2 fixture milestone."""

from __future__ import annotations

import asyncio
import hashlib
from collections.abc import Callable
from uuid import uuid4

from .contracts import (
    ExecutionMode,
    SandboxRequest,
    public_sandbox_result,
    validate_sandbox_result,
)
from .fixtures import FixtureName, FixtureSandboxService
from .protocols import SandboxService
from .run_models import CreateRunRequest, PublicSandboxResult

ServiceFactory = Callable[[FixtureName], SandboxService]


class AdapterExecutionError(RuntimeError):
    """Raised when an adapter fails or returns untrusted evidence."""


class AdapterTimeoutError(RuntimeError):
    """Raised when an adapter does not finish within the configured bound."""


def _fixture_service_factory(fixture_name: FixtureName) -> SandboxService:
    return FixtureSandboxService(fixture_name)


class Orchestrator:
    """Build, execute, validate, and publicly project one Sandbox request."""

    def __init__(
        self,
        service_factory: ServiceFactory = _fixture_service_factory,
        timeout_seconds: float = 30,
    ) -> None:
        if timeout_seconds <= 0:
            raise ValueError("timeout_seconds must be positive")
        self._service_factory = service_factory
        self._timeout_seconds = timeout_seconds

    async def run(self, create_request: CreateRunRequest) -> PublicSandboxResult:
        policy = create_request.policy
        policy_hash = hashlib.sha256(policy.description.encode("utf-8")).hexdigest()
        request = SandboxRequest(
            request_id=str(uuid4()),
            run_id=str(uuid4()),
            policy_version="1",
            policy_title=policy.title,
            policy_text=policy.description,
            policy_text_sha256=policy_hash,
            personality_seed=policy.agent_seed,
            stakeholder_count=policy.agent_count,
            test_budget=8,
            context=(),
            scenario_setups=(),
        )

        try:
            service = self._service_factory(create_request.fixture_name)
            result = await asyncio.wait_for(
                service.run(request), timeout=self._timeout_seconds
            )
        except TimeoutError as error:
            raise AdapterTimeoutError("Sandbox execution timed out.") from error
        except Exception as error:
            raise AdapterExecutionError("Sandbox execution failed.") from error

        try:
            validate_sandbox_result(request, result)
            if result.execution_mode is not ExecutionMode.FIXTURE:
                raise ValueError("non-fixture execution mode")
            return PublicSandboxResult.model_validate(public_sandbox_result(result))
        except Exception as error:
            raise AdapterExecutionError("Sandbox execution failed.") from error
