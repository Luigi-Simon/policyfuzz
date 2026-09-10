"""Stateless Orchestrator entry points for Metric runs and Sandbox previews."""

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
from .judge_contracts import JudgeRequest, JudgeResult, validate_judge_result
from .judge_protocols import JudgeService
from .metric_contracts import MetricReview, MetricRunResult
from .protocols import SandboxService
from .run_models import (
    CreateRunRequest,
    PublicSandboxResult,
    RunMetricRequest,
    RunPolicyInput,
)

ServiceFactory = Callable[[FixtureName], SandboxService]


class AdapterExecutionError(RuntimeError):
    """Raised when an adapter fails or returns untrusted evidence."""


class AdapterTimeoutError(RuntimeError):
    """Raised when an adapter does not finish within the configured bound."""


class StaleMetricReviewError(ValueError):
    """The reviewed interpretation no longer matches the submitted inputs."""


def _fixture_service_factory(fixture_name: FixtureName) -> SandboxService:
    return FixtureSandboxService(fixture_name)


class Orchestrator:
    """Coordinate reviewed Metric runs and validated Sandbox fixture requests."""

    def __init__(
        self,
        service_factory: ServiceFactory = _fixture_service_factory,
        timeout_seconds: float = 30,
    ) -> None:
        if timeout_seconds <= 0:
            raise ValueError("timeout_seconds must be positive")
        self._service_factory = service_factory
        self._timeout_seconds = timeout_seconds

    def prepare_metric(self, policy: RunPolicyInput) -> MetricReview:
        from .metric.service import prepare_policy

        return prepare_policy(policy)

    def run_metric(self, request: RunMetricRequest) -> MetricRunResult:
        from .metric.service import run_metric

        if (
            self.prepare_metric(request.policy).review_fingerprint
            != request.review_fingerprint
        ):
            raise StaleMetricReviewError("Policy inputs changed.")
        return run_metric(request.policy, request.review_fingerprint)

    def prepare_judge(
        self,
        policy: RunPolicyInput,
        metric: MetricRunResult,
        sandbox: PublicSandboxResult | None = None,
    ) -> JudgeRequest:
        """Bind core-validated evidence to the friend's shared Judge interface."""
        metric = MetricRunResult.model_validate(metric.model_dump(mode="json"))
        review = self.prepare_metric(policy)
        if (
            metric.review_fingerprint != review.review_fingerprint
            or metric.policy_text_sha256 != review.policy_text_sha256
            or metric.review != review
        ):
            raise StaleMetricReviewError(
                "Metric evidence does not match policy inputs."
            )
        limitations = metric.limitations
        if sandbox is None:
            limitations += ("Sandbox evidence was not requested for this Metric run.",)
        else:
            limitations += sandbox.limitations
        return JudgeRequest(
            request_id=str(uuid4()),
            run_id=metric.run_id,
            policy_version=metric.policy_version,
            policy_title=policy.title,
            policy_text_sha256=metric.policy_text_sha256,
            metric=metric,
            sandbox=sandbox,
            limitations=limitations,
        )

    async def judge(self, request: JudgeRequest, service: JudgeService) -> JudgeResult:
        """Run an injected Judge adapter; never replace a failure with a fixture."""
        try:
            # Give the adapter a separate validated snapshot so it cannot modify
            # the caller's Metric/Sandbox evidence through a shared object.
            adapter_input = JudgeRequest.model_validate(request.model_dump(mode="json"))
            result = await asyncio.wait_for(
                service.run(adapter_input), timeout=self._timeout_seconds
            )
        except TimeoutError as error:
            raise AdapterTimeoutError("Judge execution timed out.") from error
        except Exception as error:
            raise AdapterExecutionError("Judge execution failed.") from error
        try:
            validate_judge_result(request, result)
            return result
        except Exception as error:
            raise AdapterExecutionError("Judge execution failed.") from error

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
