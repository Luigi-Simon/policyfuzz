"""Authored, offline contract examples; these are not a Judge implementation."""

import asyncio
from typing import Literal

from .contracts import SandboxRequest, public_sandbox_result, validate_sandbox_result
from .fixtures import FixtureSandboxService
from .judge_contracts import (
    Citation,
    CitedFinding,
    JudgeRequest,
    JudgeResult,
    NextStep,
    judge_request_fingerprint,
    validate_judge_result,
)
from .judge_metric_fixtures import make_metric_fixture
from .metric.sample import SAMPLE_POLICY
from .run_models import PublicSandboxResult, RunPolicyInput

ExampleKind = Literal["complete", "partial", "unscored"]


def make_judge_example(
    kind: ExampleKind = "complete",
) -> tuple[JudgeRequest, JudgeResult]:
    """Synchronous tooling helper; never call inside an existing async event loop."""
    if kind not in ("complete", "partial", "unscored"):
        raise ValueError("Unknown Judge example")
    policy = SAMPLE_POLICY
    if kind == "unscored":
        policy = RunPolicyInput.model_validate(
            {
                **policy.model_dump(),
                "description": "A synthetic policy without supported executable clauses.",
            }
        )
    metric = make_metric_fixture(policy, f"judge-example-{kind}")
    sandbox = None
    if kind != "unscored":
        sandbox_request = SandboxRequest(
            request_id=f"sandbox-example-{kind}",
            run_id=metric.run_id,
            policy_version=metric.policy_version,
            policy_title=policy.title,
            policy_text=policy.description,
            policy_text_sha256=metric.policy_text_sha256,
            personality_seed=policy.agent_seed,
            stakeholder_count=3,
            test_budget=len(metric.cases),
            context=(),
        )
        fixture = FixtureSandboxService(
            "partial_translation_unavailable" if kind == "partial" else "completed"
        )
        raw = asyncio.run(fixture.run(sandbox_request))
        validate_sandbox_result(sandbox_request, raw)
        sandbox = PublicSandboxResult.model_validate(public_sandbox_result(raw))
    limitations = (
        "Authored Judge contract example; no Judge model was called.",
        "Sandbox dialogue is a citation-format fixture and does not analyze the transport claims policy.",
    )
    if kind == "unscored":
        limitations += (
            "Metric policy needs clarification; Sandbox was not requested.",
        )
    request = JudgeRequest(
        request_id=f"judge-request-{kind}",
        run_id=metric.run_id,
        policy_version=metric.policy_version,
        policy_title=policy.title,
        policy_text_sha256=metric.policy_text_sha256,
        metric=metric,
        sandbox=sandbox,
        limitations=limitations,
    )
    pros = ()
    cons = ()
    interactions = ()
    if kind == "unscored":
        next_steps = (
            NextStep(
                action="Clarify the supported policy clauses and review the explicit goals.",
                reason="The policy has no supported executable interpretation and no scored tests.",
            ),
        )
    else:
        passed = next(case for case in metric.cases if case.verdict == "pass")
        failed = next(case for case in metric.cases if case.verdict == "fail")
        pros = (
            CitedFinding(
                text="The authored fixture includes a passing Metric case for report development.",
                citations=(Citation(kind="metric_case", id=passed.case_id),),
            ),
        )
        cons = (
            CitedFinding(
                text="The authored fixture includes a failing Metric case; no policy runner was executed.",
                citations=(Citation(kind="metric_case", id=failed.case_id),),
            ),
        )
        if sandbox is not None:
            available = next(
                m
                for m in sandbox.messages
                if m.translation_status.value != "unavailable"
            )
            interactions = (
                CitedFinding(
                    text="This authored stakeholder message demonstrates a resolvable citation, not policy-specific simulation evidence.",
                    citations=(
                        Citation(kind="sandbox_message", id=available.message_id),
                    ),
                ),
            )
        next_steps = (
            NextStep(
                action="Inspect the failing trace, revise the relevant operative clauses and rerun the same cases.",
                reason="The supplied mock case is marked as failing its budget assertion.",
                citations=(Citation(kind="metric_case", id=failed.case_id),),
            ),
        )
    if kind == "partial":
        limitations += (
            "One Sandbox translation is unavailable and cannot support a finding.",
        )
    result = JudgeResult(
        request_id=request.request_id,
        run_id=request.run_id,
        policy_version=request.policy_version,
        policy_text_sha256=request.policy_text_sha256,
        request_fingerprint=judge_request_fingerprint(request),
        execution_mode="fixture",
        status="completed" if kind == "complete" else "partial",
        summary=(
            "The policy needs clarification before executable testing."
            if kind == "unscored"
            else "This authored fixture demonstrates reporting a failing Metric case; no policy test was executed."
        ),
        recommendation="insufficient_evidence"
        if kind == "unscored"
        else "revise_before_pilot",
        pros=pros,
        cons=cons,
        next_steps=next_steps,
        key_interactions=interactions,
        limitations=limitations,
    )
    validate_judge_result(request, result)
    return request, result
