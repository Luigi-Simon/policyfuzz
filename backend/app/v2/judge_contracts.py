"""Shared Judge boundary. Core owns evidence validation; friend owns the adapter."""

from __future__ import annotations

from typing import Annotated, Literal

from pydantic import AfterValidator, Field, model_validator

from app.core.hashing import canonical_sha256

from .contracts import (
    ContractModel,
    ExecutionMode,
    SandboxStatus,
    TranslationStatus,
    _english_display,
)
from .metric_contracts import MetricRunResult
from .run_models import PublicSandboxResult


def _judge_text(value: str) -> str:
    if not value.strip():
        raise ValueError("Judge display text must not be blank")
    return _english_display(value)


EnglishText = Annotated[
    str, Field(min_length=1, max_length=8000), AfterValidator(_judge_text)
]
Sha256 = Annotated[str, Field(pattern=r"^[0-9a-f]{64}$")]


class JudgeRequest(ContractModel):
    """Only core-validated public evidence; never raw source records or prompts."""

    schema_version: Literal["2.0"] = "2.0"
    request_id: str = Field(min_length=1)
    run_id: str = Field(min_length=1)
    policy_version: str = Field(min_length=1)
    policy_title: EnglishText
    policy_text_sha256: Sha256
    metric: MetricRunResult | None = None
    sandbox: PublicSandboxResult | None = None
    limitations: tuple[EnglishText, ...] = ()

    @model_validator(mode="after")
    def evidence_is_bound(self) -> JudgeRequest:
        for stage in (self.metric, self.sandbox):
            if stage is not None and (
                stage.run_id != self.run_id
                or stage.policy_version != self.policy_version
                or stage.policy_text_sha256 != self.policy_text_sha256
            ):
                raise ValueError("Judge evidence identity mismatch")
        if (self.metric is None or self.sandbox is None) and not self.limitations:
            raise ValueError("Missing stages require an explicit limitation")
        return self


class Citation(ContractModel):
    kind: Literal["policy_clause", "metric_case", "metric_step", "sandbox_message"]
    id: str = Field(min_length=1)
    case_id: str | None = None

    @model_validator(mode="after")
    def step_is_scoped(self) -> Citation:
        if (self.kind == "metric_step") != (self.case_id is not None):
            raise ValueError("Only a metric step citation requires case_id")
        return self


class CitedFinding(ContractModel):
    text: EnglishText
    citations: tuple[Citation, ...] = Field(min_length=1, max_length=20)


class NextStep(ContractModel):
    action: EnglishText
    reason: EnglishText
    citations: tuple[Citation, ...] = Field(default=(), max_length=20)


class JudgeResult(ContractModel):
    """Advice only. There are deliberately no writable verdict/count fields."""

    schema_version: Literal["2.0"] = "2.0"
    request_id: str = Field(min_length=1)
    run_id: str = Field(min_length=1)
    policy_version: str = Field(min_length=1)
    policy_text_sha256: Sha256
    request_fingerprint: Sha256
    execution_mode: ExecutionMode
    status: Literal["completed", "partial", "failed"]
    summary: EnglishText
    recommendation: Literal[
        "revise_before_pilot", "consider_limited_pilot", "insufficient_evidence"
    ]
    pros: tuple[CitedFinding, ...] = Field(default=(), max_length=20)
    cons: tuple[CitedFinding, ...] = Field(default=(), max_length=20)
    next_steps: tuple[NextStep, ...] = Field(default=(), max_length=20)
    key_interactions: tuple[CitedFinding, ...] = Field(default=(), max_length=20)
    limitations: tuple[EnglishText, ...] = ()
    errors: tuple[EnglishText, ...] = ()


def judge_request_fingerprint(request: JudgeRequest) -> str:
    payload = request.model_dump(mode="json")
    if request.metric is not None:
        # The canonical hasher accepts integer-only numbers. A validated rate is
        # fully determined by these counts; bind its exact rational form.
        denominator = request.metric.passed + request.metric.failed
        payload["metric"]["pass_rate"] = (
            {"numerator": request.metric.passed, "denominator": denominator}
            if denominator
            else None
        )
    return canonical_sha256(payload)


def _incomplete(request: JudgeRequest) -> bool:
    return (
        request.metric is None
        or request.metric.status != "completed"
        or request.metric.unscored > 0
        or not request.metric.cases
        or request.sandbox is None
        or request.sandbox.status is not SandboxStatus.COMPLETED
    )


def validate_judge_result(request: JudgeRequest, result: JudgeResult) -> None:
    """Check identity, references and advisory gates, not semantic LLM truth."""
    # Revalidate even model_copy/model_construct inputs at this boundary.
    request = JudgeRequest.model_validate(request.model_dump(mode="json"))
    result = JudgeResult.model_validate(result.model_dump(mode="json"))
    if (
        result.request_id != request.request_id
        or result.run_id != request.run_id
        or result.policy_version != request.policy_version
        or result.policy_text_sha256 != request.policy_text_sha256
        or result.request_fingerprint != judge_request_fingerprint(request)
    ):
        raise ValueError("Judge result identity mismatch")
    if result.status == "failed":
        if not result.errors or result.recommendation != "insufficient_evidence":
            raise ValueError("Failed Judge requires errors and insufficient evidence")
        if result.pros or result.cons or result.key_interactions or result.next_steps:
            raise ValueError("Failed Judge cannot carry findings")
    else:
        if result.errors or not result.next_steps:
            raise ValueError("Successful Judge requires next steps and no errors")
        if _incomplete(request) and result.status != "partial":
            raise ValueError("Incomplete evidence requires partial Judge status")
    if result.status == "partial" and not result.limitations:
        raise ValueError("Partial Judge requires limitations")
    if result.recommendation == "consider_limited_pilot" and (
        _incomplete(request)
        or request.metric is None
        or request.metric.failed > 0
        or request.metric.passed == 0
        or request.metric.generation_method == "authored_fixture"
        or request.sandbox is None
        or request.sandbox.execution_mode is ExecutionMode.FIXTURE
        or result.execution_mode is ExecutionMode.FIXTURE
    ):
        raise ValueError("Evidence does not support a pilot recommendation")

    cases = (
        {case.case_id: case for case in request.metric.cases} if request.metric else {}
    )
    clauses = (
        {
            clause.id
            for clause in (*request.metric.review.clauses, *request.metric.review.goals)
        }
        if request.metric
        else set()
    )
    messages = (
        {m.message_id: m for m in request.sandbox.messages} if request.sandbox else {}
    )

    def check_ref(ref: Citation) -> None:
        if ref.kind == "metric_case":
            valid = ref.id in cases
        elif ref.kind == "metric_step":
            case = cases.get(ref.case_id or "")
            valid = case is not None and ref.id in {s.step_id for s in case.trace}
        elif ref.kind == "policy_clause":
            valid = ref.id in clauses
        else:
            message = messages.get(ref.id)
            valid = (
                message is not None
                and message.translation_status is not TranslationStatus.UNAVAILABLE
            )
        if not valid:
            raise ValueError("Judge citation does not resolve to available evidence")

    for finding in (*result.pros, *result.cons, *result.key_interactions):
        for ref in finding.citations:
            check_ref(ref)
    for finding in result.key_interactions:
        if not any(ref.kind == "sandbox_message" for ref in finding.citations):
            raise ValueError("Key interactions require Sandbox message citations")
    for step in result.next_steps:
        for ref in step.citations:
            check_ref(ref)
