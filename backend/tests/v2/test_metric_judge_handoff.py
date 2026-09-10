"""Core integration with the friend's Judge port; all model calls are fake."""

import asyncio

import pytest

from app.v2.judge_contracts import JudgeResult, NextStep, judge_request_fingerprint
from app.v2.judge_examples import make_judge_example
from app.v2.metric.sample import SAMPLE_POLICY
from app.v2.orchestrator import AdapterExecutionError, AdapterTimeoutError, Orchestrator
from app.v2.run_models import RunMetricRequest


class FakeJudge:
    def __init__(self, *, stale=False, fail=False, slow=False):
        self.stale, self.fail, self.slow = stale, fail, slow
        self.seen = None

    async def run(self, request):
        self.seen = request
        if self.fail:
            raise RuntimeError("PRIVATE_PROVIDER_DETAILS")
        if self.slow:
            await asyncio.sleep(1)
        return JudgeResult(
            request_id=request.request_id,
            run_id="stale-run" if self.stale else request.run_id,
            policy_version=request.policy_version,
            policy_text_sha256=request.policy_text_sha256,
            request_fingerprint=judge_request_fingerprint(request),
            execution_mode="fixture",
            status="partial",
            summary="A fake adapter demonstrates the core Judge handoff.",
            recommendation="insufficient_evidence",
            next_steps=(
                NextStep(
                    action="Collect policy-specific Sandbox evidence.",
                    reason="Sandbox evidence is missing from this run.",
                ),
            ),
            limitations=(
                "Fake Judge for offline integration tests; no model was called.",
            ),
        )


def test_builder_binds_policy_and_marks_missing_sandbox():
    fixture, _ = make_judge_example()
    request = Orchestrator().prepare_judge(SAMPLE_POLICY, fixture.metric)
    assert request.metric == fixture.metric
    assert request.run_id == fixture.metric.run_id
    assert request.sandbox is None
    assert any("Sandbox" in item for item in request.limitations)
    assert "original_records" not in request.model_dump_json()


def test_builder_rejects_changed_policy_inputs():
    fixture, _ = make_judge_example()
    changed = SAMPLE_POLICY.model_copy(update={"agent_seed": "Different voices."})
    with pytest.raises(ValueError):
        Orchestrator().prepare_judge(changed, fixture.metric)


def test_judge_port_preserves_input_evidence():
    fixture, _ = make_judge_example()
    orchestrator = Orchestrator()
    request = orchestrator.prepare_judge(SAMPLE_POLICY, fixture.metric)
    service = FakeJudge()
    before = request.model_dump_json()
    result = asyncio.run(orchestrator.judge(request, service))
    assert service.seen == request
    assert result.status == "partial"
    assert request.model_dump_json() == before


def test_executed_metric_cases_reach_judge_without_losing_failed_evidence():
    orchestrator = Orchestrator()
    review = orchestrator.prepare_metric(SAMPLE_POLICY)
    metric = orchestrator.run_metric(
        RunMetricRequest(
            policy=SAMPLE_POLICY, review_fingerprint=review.review_fingerprint
        )
    )
    request = orchestrator.prepare_judge(SAMPLE_POLICY, metric)
    service = FakeJudge()
    result = asyncio.run(orchestrator.judge(request, service))
    assert service.seen.metric == metric
    assert service.seen.metric.generation_method == "rule_templates"
    assert service.seen.metric.failed > 0
    assert all(
        case.trace and case.assertions
        for case in service.seen.metric.cases
        if case.verdict == "fail"
    )
    assert result.run_id == metric.run_id
    assert result.status == "partial"
    assert result.recommendation == "insufficient_evidence"


@pytest.mark.parametrize("options", [{"stale": True}, {"fail": True}])
def test_judge_errors_are_safe_and_never_substitute_evidence(options):
    request, _ = make_judge_example()
    with pytest.raises(AdapterExecutionError, match="^Judge execution failed\\.$"):
        asyncio.run(Orchestrator().judge(request, FakeJudge(**options)))


def test_judge_timeout_is_bounded():
    request, _ = make_judge_example()
    with pytest.raises(AdapterTimeoutError, match="^Judge execution timed out\\.$"):
        asyncio.run(
            Orchestrator(timeout_seconds=0.001).judge(request, FakeJudge(slow=True))
        )
