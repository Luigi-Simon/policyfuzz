"""Orchestrate Metric, Sandbox and Judge with validated evidence handoffs."""

import asyncio
from uuid import uuid4

from .contracts import (
    SandboxRequest,
    ScenarioSetup,
    public_sandbox_result,
    request_fingerprint,
    validate_sandbox_result,
)
from .diagnostics import record, recording
from .fixtures import FixtureSandboxService
from .judge_contracts import JudgeRequest, JudgeResult, validate_judge_result
from .metric.service import run_metric
from .run_models import PublicSandboxResult
from .workflow_fixture import FixtureWorkflowJudge
from .workflow_models import StageResult, WorkflowRequest, WorkflowResult


class WorkflowUnavailable(RuntimeError):
    """Live services have not been configured; never substitute fixtures."""


class WorkflowOrchestrator:
    def __init__(
        self,
        *,
        sandbox_factory=None,
        judge_factory=None,
        sandbox_grace_seconds=45,
        judge_timeout_seconds=95,
        diagnostics_path=None,
    ):
        self._sandbox_factory = sandbox_factory
        self._judge_factory = judge_factory
        self._sandbox_grace = sandbox_grace_seconds
        self._judge_timeout = judge_timeout_seconds
        self._diagnostics_path = diagnostics_path

    async def run(self, body: WorkflowRequest) -> WorkflowResult:
        run_id = str(uuid4())
        with recording(self._diagnostics_path, run_id):
            return await self._run(body, run_id)

    async def _run(self, body: WorkflowRequest, run_id: str) -> WorkflowResult:
        body = WorkflowRequest.model_validate_json(body.model_dump_json())
        if body.mode == "live" and (
            self._sandbox_factory is None or self._judge_factory is None
        ):
            raise WorkflowUnavailable(
                "Live Sandbox and Judge services are not configured."
            )
        metric = run_metric(body.policy, run_id, test_budget=body.test_budget)
        record("metric", metric.status.value, count=len(metric.cases))
        stages = [
            StageResult(
                role="Orchestrator Agent",
                status="completed",
                detail="Inputs bound to a single policy version and run.",
            ),
            StageResult(
                role="Metric Agent",
                status=metric.status.value,
                detail=f"{metric.passed} passed, {metric.failed} failed, {metric.unscored} unscored cases."
                if metric.cases
                else "Exact testing needs a supported policy interpretation.",
            ),
        ]
        limitations = [
            "Completion describes evidence processing, not policy correctness."
        ]
        if body.mode == "fixture":
            limitations.append(
                "Fixture mode uses authored Sandbox dialogue and a deterministic demonstration of Judge advice."
            )
        sandbox_request = SandboxRequest(
            request_id=str(uuid4()),
            run_id=run_id,
            policy_version="1",
            policy_title=body.policy.title,
            policy_text=body.policy.description,
            policy_text_sha256=metric.policy_text_sha256,
            personality_seed=body.policy.agent_seed,
            stakeholder_count=body.policy.agent_count,
            test_budget=body.test_budget,
            max_rounds=body.max_rounds,
            timeout_seconds=body.sandbox_timeout_seconds,
            context=(),
            scenario_setups=tuple(
                ScenarioSetup(
                    scenario_id=case.case_id,
                    title=case.title,
                    circumstances=case.plausibility,
                )
                for case in metric.cases
            ),
        )
        sandbox, judge = None, None
        record(
            "sandbox",
            "bound",
            request_id=sandbox_request.request_id,
            fingerprint=request_fingerprint(sandbox_request),
        )
        record("sandbox", "started")
        try:
            service = (
                self._sandbox_factory(body)
                if self._sandbox_factory
                else FixtureSandboxService(body.fixture_name)
            )
            raw = await asyncio.wait_for(
                service.run(sandbox_request),
                timeout=body.sandbox_timeout_seconds + self._sandbox_grace,
            )
            if asyncio.current_task().cancelling():
                raise asyncio.CancelledError()
            validate_sandbox_result(sandbox_request, raw)
            if raw.execution_mode.value != body.mode:
                raise ValueError("Sandbox execution mode mismatch")
            sandbox = PublicSandboxResult.model_validate(public_sandbox_result(raw))
            record("sandbox", sandbox.status.value, count=len(sandbox.messages))
            stages.append(
                StageResult(
                    role="Sandbox Agent",
                    status=sandbox.status.value,
                    detail=f"{sandbox.observed_stakeholder_count} of {sandbox.requested_stakeholder_count} requested stakeholders observed.",
                )
            )
            if sandbox.status != "completed":
                limitations.append(
                    "Sandbox evidence is incomplete; inspect its errors and limitations."
                )
        except TimeoutError:
            record("sandbox", "failed", code="workflow_deadline")
            limitations.append(
                "Sandbox execution timed out. Upstream stop acknowledgement is unavailable; inspect MiroFish before retrying."
            )
            stages.append(
                StageResult(
                    role="Sandbox Agent", status="failed", detail=limitations[-1]
                )
            )
        except Exception:  # noqa: BLE001 - provider details and invalid evidence stay private
            record("sandbox", "failed", code="evidence_unavailable")
            limitations.append(
                "Sandbox evidence could not be obtained or validated. No substitute simulation was used."
            )
            stages.append(
                StageResult(
                    role="Sandbox Agent", status="failed", detail=limitations[-1]
                )
            )
        if metric.status != "completed":
            limitations.append(
                "Metric prepared scenario questions; executable rules and expected outcomes still need review. No passing tests were invented."
                if metric.generation_method == "policy_scenarios"
                else "Metric executed clause-local boundary checks; combined policy outcomes and unsupported scenarios remain unscored."
                if metric.status == "partial"
                else "Metric needs clarification; no exact pass/fail conclusion is available for this policy."
            )
        judge_request = JudgeRequest(
            request_id=str(uuid4()),
            run_id=run_id,
            policy_version="1",
            policy_title=body.policy.title,
            policy_text_sha256=metric.policy_text_sha256,
            metric=metric,
            sandbox=sandbox,
            limitations=tuple(limitations),
        )
        record("judge", "started")
        try:
            service = (
                self._judge_factory(body.mode)
                if self._judge_factory
                else FixtureWorkflowJudge()
            )
            raw_judge = await asyncio.wait_for(
                service.run(judge_request), timeout=self._judge_timeout
            )
            validate_judge_result(judge_request, raw_judge)
            if raw_judge.execution_mode.value != body.mode:
                raise ValueError("Judge execution mode mismatch")
            judge = JudgeResult.model_validate_json(raw_judge.model_dump_json())
            record("judge", judge.status)
            stages.append(
                StageResult(
                    role="Judge Agent",
                    status=judge.status,
                    detail="Judge advice unavailable."
                    if judge.status == "failed"
                    else "Qualitative review only; policy recommendation withheld."
                    if metric.review.status != "ready"
                    else "Cited advice validated.",
                )
            )
        except Exception:  # noqa: BLE001 - retain safe evidence without publishing provider errors
            record("judge", "failed", code="evidence_unavailable")
            limitations.append(
                "Judge advice could not be obtained or validated. Inspect the retained Metric and Sandbox evidence."
            )
            stages.append(
                StageResult(role="Judge Agent", status="failed", detail=limitations[-1])
            )
        complete = all(stage.status == "completed" for stage in stages)
        return WorkflowResult(
            run_id=run_id,
            policy_title=body.policy.title,
            policy_text_sha256=metric.policy_text_sha256,
            execution_mode=body.mode,
            status="completed" if complete else "partial",
            metric=metric,
            sandbox=sandbox,
            judge=judge,
            stages=tuple(stages),
            limitations=tuple(limitations),
        )
