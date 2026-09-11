import asyncio
import json

import httpx
import pytest

from app.v2.contracts import ExecutionMode
from app.v2.fixtures import FixtureSandboxService
from app.v2.main import create_app
from app.v2.metric.sample import SAMPLE_POLICY
from app.v2.workflow import WorkflowOrchestrator, WorkflowUnavailable
from app.v2.workflow_models import WorkflowRequest, WorkflowResult


@pytest.mark.asyncio
async def test_full_fixture_api_returns_bound_metric_sandbox_and_judge():
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=create_app()), base_url="http://test"
    ) as client:
        response = await client.post(
            "/api/v2/workflows", json={"policy": SAMPLE_POLICY.model_dump()}
        )
    assert response.status_code == 200
    result = WorkflowResult.model_validate(response.json())
    assert result.execution_mode == "fixture" and result.status == "completed"
    assert result.metric.failed >= 2 and result.judge.cons
    assert result.sandbox.execution_mode == result.judge.execution_mode == "fixture"
    assert result.judge.recommendation != "consider_limited_pilot"
    assert {s.role for s in result.stages} == {
        "Orchestrator Agent",
        "Metric Agent",
        "Sandbox Agent",
        "Judge Agent",
    }
    for stage in (result.metric, result.sandbox, result.judge):
        assert stage.run_id == result.run_id
        assert stage.policy_text_sha256 == result.policy_text_sha256
    assert "original_records" not in response.text
    assert SAMPLE_POLICY.agent_seed not in response.text


@pytest.mark.asyncio
async def test_sandbox_gets_exact_seed_count_and_neutral_scenarios_only():
    seen = []

    class Capture:
        async def run(self, request):
            seen.append(request)
            return await FixtureSandboxService().run(request)

    result = await WorkflowOrchestrator(sandbox_factory=lambda request: Capture()).run(
        WorkflowRequest(
            policy=SAMPLE_POLICY,
            test_budget=6,
            max_rounds=2,
            sandbox_timeout_seconds=45,
        )
    )
    request = seen[0]
    assert request.personality_seed == SAMPLE_POLICY.agent_seed
    assert request.stakeholder_count == SAMPLE_POLICY.agent_count
    assert (
        request.test_budget == 6
        and request.max_rounds == 2
        and request.timeout_seconds == 45
    )
    assert request.policy_text == SAMPLE_POLICY.description
    assert len(request.scenario_setups) == len(result.metric.cases) == 6
    seeds = json.dumps([s.model_dump() for s in request.scenario_setups]).lower()
    for forbidden in (
        "verdict",
        "assertion",
        "expected",
        "passed",
        "failed",
        "g-budget",
    ):
        assert forbidden not in seeds


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "mutation", ["run_id", "execution_mode", "request_fingerprint"]
)
async def test_foreign_or_wrong_mode_sandbox_evidence_is_never_sent_to_judge(mutation):
    class Invalid:
        async def run(self, request):
            result = await FixtureSandboxService().run(request)
            value = ExecutionMode.LIVE if mutation == "execution_mode" else "foreign"
            return result.model_copy(update={mutation: value})

    result = await WorkflowOrchestrator(sandbox_factory=lambda request: Invalid()).run(
        WorkflowRequest(policy=SAMPLE_POLICY)
    )
    assert result.status == "partial" and result.sandbox is None
    assert result.judge.status == "partial"
    assert any(
        s.role == "Sandbox Agent" and s.status == "failed" for s in result.stages
    )
    assert "foreign" not in result.model_dump_json()


@pytest.mark.asyncio
async def test_sandbox_timeout_and_judge_exception_keep_metric_and_safe_diagnostics():
    class Slow:
        async def run(self, request):
            await asyncio.sleep(10)

    class Broken:
        async def run(self, request):
            raise RuntimeError("secret provider response")

    result = await WorkflowOrchestrator(
        sandbox_factory=lambda request: Slow(),
        judge_factory=lambda mode: Broken(),
        sandbox_grace_seconds=0,
    ).run(WorkflowRequest(policy=SAMPLE_POLICY, sandbox_timeout_seconds=1))
    assert result.status == "partial" and result.metric.cases
    assert result.sandbox is None and result.judge is None
    assert "secret" not in result.model_dump_json()


@pytest.mark.asyncio
async def test_general_policy_runs_sandbox_and_advice_without_inventing_passes():
    policy = SAMPLE_POLICY.model_copy(
        update={"description": "Improve late-night public transport."}
    )
    result = await WorkflowOrchestrator().run(WorkflowRequest(policy=policy))
    assert result.status == "partial"
    assert result.metric.status == "partial" and result.metric.pass_rate is None
    assert result.sandbox and result.judge.status == "partial"
    assert result.judge.recommendation == "insufficient_evidence"


@pytest.mark.asyncio
async def test_prose_conditions_reach_real_judge_adapter_with_partial_coverage():
    from backend.tests.v2.judge.test_service import APPROVED

    from app.v2.judge.prompts import EDITORIAL_FIELDS
    from app.v2.judge.service import JudgeAgentService
    from app.v2.judge_contracts import JudgeRequest
    from app.v2.workflow_fixture import FixtureWorkflowJudge

    class Model:
        execution_mode = "fixture"
        calls = 0
        citation_calls = 0

        async def complete(self, *, system_prompt, payload, response_schema):
            if "citation_check" in payload:
                self.citation_calls += 1
                return json.dumps({"supported": True, "problem": ""})
            self.calls += 1
            if "draft" in payload:
                return json.dumps(APPROVED)
            assert payload["pilot_recommendation_allowed"] is False
            assert payload["qualitative_only"] is True
            request = JudgeRequest.model_validate(payload["request"])
            assert request.metric.passed == 2 and request.metric.unscored == 1
            assert "policy correctness" in " ".join(payload["mandatory_limitations"])
            report = await FixtureWorkflowJudge().run(request)
            report = report.model_copy(
                update={
                    "pros": (),
                    "cons": (),
                    "recommendation": "insufficient_evidence",
                    "summary": "Missing-provision-sentinel: the model claims unsupported policy omissions.",
                }
            )
            return report.model_dump_json(include=set(EDITORIAL_FIELDS))

    seen = []

    class Sandbox:
        async def run(self, request):
            seen.append(request)
            return await FixtureSandboxService().run(request)

    model = Model()
    policy = SAMPLE_POLICY.model_copy(
        update={
            "description": "Applicants aged 23 and above. Annual income <= $31,700."
        }
    )
    result = await WorkflowOrchestrator(
        sandbox_factory=lambda _: Sandbox(),
        judge_factory=lambda _: JudgeAgentService(model),
    ).run(WorkflowRequest(policy=policy))
    assert model.calls == 2
    assert model.citation_calls > 0
    assert "Missing-provision-sentinel" not in result.judge.summary
    assert "2 passed, 0 failed, 1 unscored" in result.judge.summary
    assert not result.judge.pros and not result.judge.cons
    assert result.metric.status == result.judge.status == result.status == "partial"
    assert result.sandbox.status == "completed" and not result.judge.errors
    assert result.judge.recommendation != "consider_limited_pilot"
    seeds = json.dumps([s.model_dump() for s in seen[0].scenario_setups]).lower()
    for word in ("unscored", "passed", "expected", "verdict", "failed"):
        assert word not in seeds


@pytest.mark.asyncio
async def test_partial_translation_stays_partial_through_judge():
    result = await WorkflowOrchestrator().run(
        WorkflowRequest(
            policy=SAMPLE_POLICY, fixture_name="partial_translation_unavailable"
        )
    )
    assert result.status == result.sandbox.status == result.judge.status == "partial"


@pytest.mark.asyncio
async def test_unconfigured_live_never_falls_back_to_fixture():
    with pytest.raises(WorkflowUnavailable):
        await WorkflowOrchestrator().run(
            WorkflowRequest(policy=SAMPLE_POLICY, mode="live")
        )


@pytest.mark.asyncio
async def test_task_cancellation_propagates():
    class Cancelled:
        async def run(self, request):
            raise asyncio.CancelledError()

    with pytest.raises(asyncio.CancelledError):
        await WorkflowOrchestrator(sandbox_factory=lambda request: Cancelled()).run(
            WorkflowRequest(policy=SAMPLE_POLICY)
        )


@pytest.mark.asyncio
async def test_real_adapter_classes_assemble_with_fixture_transports():
    from backend.tests.v2.judge.test_service import APPROVED
    from backend.tests.v2.sandbox.test_service import FakeLanguage, FakeMiroFish

    from app.v2.judge.prompts import EDITORIAL_FIELDS
    from app.v2.judge.service import JudgeAgentService
    from app.v2.judge_contracts import JudgeRequest
    from app.v2.sandbox.service import MiroFishSandboxService
    from app.v2.workflow_fixture import FixtureWorkflowJudge

    transport, language = FakeMiroFish(), FakeLanguage()
    native = MiroFishSandboxService(transport, language, poll_seconds=0.001)

    class FixtureTransportSandbox:
        async def run(self, request):
            result = await native.run(request)
            return result.model_copy(update={"execution_mode": ExecutionMode.FIXTURE})

    class ModelFixture:
        execution_mode = "fixture"
        calls = 0
        citation_calls = 0

        async def complete(self, *, system_prompt, payload, response_schema):
            if "citation_check" in payload:
                self.citation_calls += 1
                return json.dumps({"supported": True, "problem": ""})
            self.calls += 1
            if "draft" in payload:
                return json.dumps(APPROVED)
            assert "original_records" not in json.dumps(payload)
            evidence = JudgeRequest.model_validate(payload["request"])
            report = await FixtureWorkflowJudge().run(evidence)
            return report.model_dump_json(include=set(EDITORIAL_FIELDS))

    model = ModelFixture()
    result = await WorkflowOrchestrator(
        sandbox_factory=lambda request: FixtureTransportSandbox(),
        judge_factory=lambda mode: JudgeAgentService(model),
    ).run(WorkflowRequest(policy=SAMPLE_POLICY.model_copy(update={"agent_count": 3})))
    assert result.status == "completed"
    assert model.calls == 2 and transport.prepares == transport.starts == 1
    assert model.citation_calls > 0
    assert result.judge.key_interactions
    assert result.sandbox.observed_stakeholder_count == 3


@pytest.mark.asyncio
async def test_invalid_judge_citations_are_discarded_without_losing_other_evidence():
    from app.v2.workflow_fixture import FixtureWorkflowJudge

    class InvalidJudge:
        async def run(self, request):
            result = await FixtureWorkflowJudge().run(request)
            finding = result.cons[0]
            bad = finding.model_copy(
                update={
                    "citations": (
                        finding.citations[0].model_copy(update={"id": "foreign"}),
                    )
                }
            )
            return result.model_copy(update={"cons": (bad,)})

    result = await WorkflowOrchestrator(judge_factory=lambda mode: InvalidJudge()).run(
        WorkflowRequest(policy=SAMPLE_POLICY)
    )
    assert result.status == "partial" and result.judge is None
    assert result.metric.cases and result.sandbox


@pytest.mark.asyncio
async def test_runtime_supports_mirofish_env_aliases_and_does_not_expose_configuration(
    tmp_path,
):
    from app.v2.runtime import V2Settings, WorkflowRuntime

    path = tmp_path / "config.env"
    path.write_text("LLM_API_KEY=fixture-secret\nLLM_MODEL_NAME=fixture-model\n")
    settings = V2Settings(_env_file=path)
    assert settings.live_available and settings.llm_model == "fixture-model"
    runtime = WorkflowRuntime(settings)
    await runtime.run(WorkflowRequest(policy=SAMPLE_POLICY))
    assert runtime._sandbox is runtime._judge is None
    await runtime.close()
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=create_app(settings=settings)),
        base_url="http://test",
    ) as client:
        response = await client.get("/api/v2/workflows/capabilities")
    assert response.json()["live_available"]
    assert (
        "fixture-secret" not in response.text and "fixture-model" not in response.text
    )


@pytest.mark.asyncio
@pytest.mark.parametrize("engine_ok", [True, False])
async def test_workflow_health_checks_engine_without_model_calls(
    monkeypatch, engine_ok
):
    from app.v2.runtime import V2Settings, WorkflowRuntime

    settings = V2Settings(
        _env_file=None, LLM_MODEL="fake-model", LLM_API_KEY="fake-secret"
    )
    runtime = WorkflowRuntime(settings)
    requests = []

    def reply(request):
        requests.append(str(request.url))
        if not engine_ok:
            raise httpx.ConnectError("private provider diagnostic")
        return httpx.Response(
            200,
            json={
                "success": True,
                "data": {"service": "policyfuzz_v2", "status": "ok"},
            },
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(reply)) as client:
        health = await runtime.health(client=client)
    assert health.status == "ok" and health.live_configured
    assert health.mirofish == ("reachable" if engine_ok else "unavailable")
    assert health.provider == "configured_not_checked"
    assert runtime._sandbox is None and runtime._judge is None
    assert len(requests) == 1 and requests[0].endswith("/api/policyfuzz/v2/health")
    assert (
        "secret" not in health.model_dump_json()
        and "diagnostic" not in health.model_dump_json()
    )
    await runtime.close()


@pytest.mark.asyncio
async def test_workflow_health_route_is_distinct_from_legacy_fixture_health():
    from app.v2.runtime import V2Settings

    settings = V2Settings(
        _env_file=None,
        LLM_MODEL=None,
        LLM_MODEL_NAME=None,
        LLM_API_KEY=None,
        OPENAI_API_KEY=None,
    )
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=create_app(settings=settings)),
        base_url="http://test",
    ) as client:
        response = await client.get("/api/v2/workflows/health")
    assert response.status_code == 200
    assert response.json()["mirofish"] == "not_checked"
    assert not response.json()["live_configured"]
