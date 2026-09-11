"""Explicit offline Judge demonstration using the actual supplied evidence."""

from .contracts import ExecutionMode
from .judge_contracts import (
    Citation,
    CitedFinding,
    JudgeResult,
    NextStep,
    judge_request_fingerprint,
    validate_judge_result,
)


class FixtureWorkflowJudge:
    async def run(self, request):
        metric, sandbox = request.metric, request.sandbox
        incomplete = (
            metric is None
            or metric.status != "completed"
            or not metric.cases
            or metric.unscored > 0
            or sandbox is None
            or sandbox.status != "completed"
        )
        limitations = (
            "Fixture Judge: deterministic report demonstration; no Judge model was called.",
            "Fixture Sandbox dialogue does not analyse the submitted policy or personality seed.",
            *request.limitations,
        )
        if metric:
            limitations += metric.limitations
        if sandbox:
            limitations += sandbox.limitations
        pros, cons = [], []
        if metric:
            for case in metric.cases:
                if case.verdict not in {"pass", "fail"}:
                    continue
                finding = CitedFinding(
                    text=f"Fixture advice: the deterministic case '{case.title}' returned {case.verdict.value}.",
                    citations=(Citation(kind="metric_case", id=case.case_id),),
                )
                (cons if case.verdict == "fail" else pros).append(finding)
        interactions = []
        if sandbox:
            messages = {m.message_id: m for m in sandbox.messages}
            for reply in sandbox.messages:
                for parent_id in reply.reply_to_message_ids:
                    parent = messages[parent_id]
                    if (
                        reply.persona_id != parent.persona_id
                        and reply.translation_status != "unavailable"
                        and parent.translation_status != "unavailable"
                    ):
                        interactions.append(
                            CitedFinding(
                                text="Fixture dialogue contains a reply between two distinct sample participants; this is not policy-specific simulation evidence.",
                                citations=(
                                    Citation(kind="sandbox_message", id=parent_id),
                                    Citation(
                                        kind="sandbox_message", id=reply.message_id
                                    ),
                                ),
                            )
                        )
        failed = bool(metric and metric.failed)
        result = JudgeResult(
            request_id=request.request_id,
            run_id=request.run_id,
            policy_version=request.policy_version,
            policy_text_sha256=request.policy_text_sha256,
            request_fingerprint=judge_request_fingerprint(request),
            execution_mode=ExecutionMode.FIXTURE,
            status="partial" if incomplete else "completed",
            summary="Fixture advice combines deterministic Metric results with authored Sandbox dialogue. Inspect the cited tests and resolve evidence limitations before making policy decisions.",
            recommendation="revise_before_pilot" if failed else "insufficient_evidence",
            pros=tuple(pros[:5]),
            cons=tuple(cons[:5]),
            key_interactions=tuple(interactions[:5]),
            next_steps=(
                NextStep(
                    action="Review the failing assertions and revise their cited policy clauses."
                    if failed
                    else "Clarify executable requirements and collect live stakeholder evidence.",
                    reason="Deterministic failures need correction; fixture dialogue cannot support a pilot decision."
                    if failed
                    else "A fixture report cannot establish policy readiness.",
                    citations=cons[0].citations if cons else (),
                ),
            ),
            limitations=tuple(dict.fromkeys(limitations)),
        )
        validate_judge_result(request, result)
        return result
