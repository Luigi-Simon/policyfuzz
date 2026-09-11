"""Additive API boundary for the assembled four-agent workflow."""

from typing import Literal

from pydantic import Field, model_validator

from .contracts import AgentRole, ContractModel, ExecutionMode
from .fixtures import FixtureName
from .judge_contracts import JudgeResult
from .metric_contracts import MetricRunResult
from .run_models import PublicSandboxResult, RunPolicyInput


class WorkflowRequest(ContractModel):
    policy: RunPolicyInput
    mode: Literal["fixture", "live"] = "fixture"
    fixture_name: FixtureName = "completed"
    test_budget: int = Field(default=12, strict=True, ge=1, le=12)
    max_rounds: int = Field(default=4, strict=True, ge=1, le=20)
    sandbox_timeout_seconds: int = Field(default=180, strict=True, ge=1, le=600)


class StageResult(ContractModel):
    role: AgentRole
    status: Literal[
        "completed", "partial", "failed", "cancelled", "needs_clarification"
    ]
    detail: str


class WorkflowResult(ContractModel):
    schema_version: Literal["2.0"] = "2.0"
    run_id: str
    policy_version: Literal["1"] = "1"
    policy_title: str
    policy_text_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    execution_mode: ExecutionMode
    status: Literal["completed", "partial"]
    metric: MetricRunResult
    sandbox: PublicSandboxResult | None
    judge: JudgeResult | None
    stages: tuple[StageResult, ...]
    limitations: tuple[str, ...]

    @model_validator(mode="after")
    def stage_identity_matches(self):
        for evidence in (self.metric, self.sandbox, self.judge):
            if evidence and (
                evidence.run_id != self.run_id
                or evidence.policy_version != self.policy_version
                or evidence.policy_text_sha256 != self.policy_text_sha256
            ):
                raise ValueError("Workflow evidence identity mismatch")
        for evidence in (self.sandbox, self.judge):
            if evidence and evidence.execution_mode != self.execution_mode:
                raise ValueError("Workflow evidence mode mismatch")
        if self.status == "completed" and (
            any(stage.status != "completed" for stage in self.stages)
            or self.sandbox is None
            or self.judge is None
        ):
            raise ValueError("Incomplete stages cannot produce a completed workflow")
        return self


class WorkflowCapabilities(ContractModel):
    fixture_available: bool = True
    live_available: bool
    live_detail: str
    max_test_budget: int = 12
    max_live_stakeholders: int = 50


class WorkflowHealth(ContractModel):
    status: Literal["ok"] = "ok"
    live_configured: bool
    mirofish: Literal["reachable", "unavailable", "not_checked"]
    provider: Literal["configured_not_checked", "not_configured"]
    detail: str
