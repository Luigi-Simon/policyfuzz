from contextlib import asynccontextmanager

from httpx import ASGITransport, AsyncClient

from app.core.config import Settings
from app.core.fakes import ScriptedLLMClient
from app.domain.models import CreateRunRequest
from tests.workflow.coordinator_fixtures import cached_record


@asynccontextmanager
async def client_for(container):
    from app.main import create_app

    app = create_app(container=container)
    async with (
        app.router.lifespan_context(app),
        AsyncClient(
            transport=ASGITransport(app=app, raise_app_exceptions=False),
            base_url="http://test",
        ) as client,
    ):
        yield client


def bundled():
    return CreateRunRequest(
        source_type="bundled_sample",
        sample_id="development-policy",
        title="Synthetic policy",
    )


async def test_cached_graph_creates_fresh_session_and_never_calls_provider():
    from app.container import build_container

    llm = ScriptedLLMClient([])
    container = build_container(
        Settings(app_mode="cached"),
        llm=llm,
        cached_loader=lambda command: cached_record(),
    )
    async with client_for(container) as client:
        response = await client.post(
            "/api/v1/runs", json=bundled().model_dump(mode="json")
        )
        assert response.status_code == 202
        run_id = response.json()["run_id"]
        assert run_id != "recorded"
        view = (await client.get(f"/api/v1/runs/{run_id}")).json()
        assert view["mode"] == "cached"
        assert view["allowed_actions"] == ["delete_run"]
        assert (
            await client.post(
                f"/api/v1/runs/{run_id}/confirm-contract", json={"decision": "reject"}
            )
        ).status_code == 409
        assert llm.requests == []


async def test_production_graph_uses_concrete_frozen_specialists():
    from app.container import build_container
    from app.domain.protocols import (
        EvaluationEngine,
        FindingAnalyzer,
        PolicyCompiler,
        RegressionAnalyzer,
        RevisionApplier,
        RevisionPlanner,
        ScenarioPlanner,
    )

    container = build_container(Settings(app_mode="live"), llm=ScriptedLLMClient([]))
    coordinator = container.coordinator
    for value, interface in [
        (coordinator.policy_compiler, PolicyCompiler),
        (coordinator.scenario_planner, ScenarioPlanner),
        (coordinator.evaluation_engine, EvaluationEngine),
        (coordinator.finding_analyzer, FindingAnalyzer),
        (coordinator.revision_planner, RevisionPlanner),
        (coordinator.revision_applier, RevisionApplier),
        (coordinator.regression_analyzer, RegressionAnalyzer),
    ]:
        assert isinstance(value, interface)
        assert "fake" not in type(value).__module__
    await container.aclose()


async def test_unknown_bundled_sample_is_422_without_path_echo():
    from app.container import build_container

    container = build_container(Settings(app_mode="live"), llm=ScriptedLLMClient([]))
    async with client_for(container) as client:
        response = await client.post(
            "/api/v1/runs",
            json=bundled()
            .model_copy(update={"sample_id": "SECRET-path"})
            .model_dump(mode="json"),
        )
        assert response.status_code == 422
        assert "SECRET" not in response.text


async def test_provider_close_after_owned_jobs_are_drained():
    from app.container import build_container

    container = build_container(
        Settings(app_mode="cached"), cached_loader=lambda command: cached_record()
    )
    closed = []

    async def close():
        closed.append(container.task_runner.pending_count)

    container.close_provider = close
    await container.aclose()
    assert closed == [0]


async def test_unconfigured_live_graph_starts_with_safe_health_and_create_failure():
    from app.container import build_container

    container = build_container(
        Settings(app_mode="live", llm_model=None, openai_api_key=None)
    )
    async with client_for(container) as client:
        response = await client.get("/api/v1/health")
        assert response.status_code == 200
        assert response.json()["status"] == "degraded"
        assert response.json()["provider_configured"] is False
        response = await client.post(
            "/api/v1/runs", json=bundled().model_dump(mode="json")
        )
        assert response.status_code == 503
        assert response.json()["error"]["code"] == "PROVIDER_UNAVAILABLE"


async def test_missing_and_corrupt_recorded_cache_are_safe(tmp_path):
    from app.container import build_container

    path = tmp_path / "run-record.json"
    container = build_container(Settings(app_mode="cached"), cache_path=path)
    async with client_for(container) as client:
        response = await client.post(
            "/api/v1/runs", json=bundled().model_dump(mode="json")
        )
        assert response.status_code == 503
        assert response.json()["error"]["code"] == "PROVIDER_UNAVAILABLE"
    path.write_text('{"SECRET":"not a valid record"}')
    container = build_container(Settings(app_mode="cached"), cache_path=path)
    async with client_for(container) as client:
        response = await client.post(
            "/api/v1/runs", json=bundled().model_dump(mode="json")
        )
        assert response.status_code == 500
        assert response.json()["error"]["code"] == "HASH_MISMATCH"
        assert "SECRET" not in response.text


async def test_http_create_runs_concrete_policy_compiler_with_scripted_transport(
    monkeypatch,
):
    import asyncio

    from app.container import build_container
    from app.domain.models import (
        CompilePolicyRequest,
        InvariantSuggestions,
        LLMResponse,
        PolicyExtraction,
        RuleDraft,
    )
    from tests.workflow.coordinator_fixtures import compilation, document, request

    source = request()
    compiled = compilation(CompilePolicyRequest(document=document(source)))
    rule = compiled.policy.rules[0]
    extraction = PolicyExtraction(
        document_sha256=compiled.policy.document_sha256,
        rules=(
            RuleDraft(
                description=rule.description,
                when=rule.when,
                effects=rule.effects,
                provenance=rule.provenance,
            ),
        ),
    )
    suggestions = InvariantSuggestions(invariant_drafts=compiled.invariant_drafts)
    llm = ScriptedLLMClient(
        [
            LLMResponse(output=extraction.model_dump(mode="json")),
            LLMResponse(output=suggestions.model_dump(mode="json")),
        ]
    )
    container = build_container(Settings(app_mode="live"), llm=llm)
    async with client_for(container) as client:
        response = await client.post(
            "/api/v1/runs", json=source.model_dump(mode="json")
        )
        assert response.status_code == 202
        run_id = response.json()["run_id"]
        await container.task_runner.drain(run_id)
        response = await client.get("/api/v1/runs/" + run_id)
        assert response.status_code == 200
        view = response.json()
        assert view["stage"] == "awaiting_contract"
        assert len(view["pending_confirmation"]["invariants"]) == 3
        assert [item.operation for item in llm.requests] == [
            "policy_extraction",
            "invariant_suggestion",
        ]
        from tests.workflow.coordinator_fixtures import confirm

        entered, release = asyncio.Event(), asyncio.Event()
        original_complete = llm.complete_json

        async def blocked_scenarios(command):
            if command.operation == "scenario_generation":
                entered.set()
                await release.wait()
            return await original_complete(command)

        monkeypatch.setattr(llm, "complete_json", blocked_scenarios)
        llm.queue(LLMResponse(output={"scenarios": []}))
        llm.queue(LLMResponse(output={"scenarios": []}))
        scoped_planner = container.scenario_scope._instances[run_id]
        command = confirm(await container.coordinator.get_run(run_id))
        response = await asyncio.wait_for(
            client.post(
                "/api/v1/runs/" + run_id + "/confirm-contract",
                json=command.model_dump(mode="json"),
            ),
            1,
        )
        assert response.status_code == 200
        assert response.json()["stage"] == "generating_initial_tests"
        await asyncio.wait_for(entered.wait(), 1)
        assert (await client.get("/api/v1/runs/" + run_id)).json()[
            "stage"
        ] == "generating_initial_tests"
        release.set()
        await container.task_runner.drain(run_id)
        assert (await client.get("/api/v1/runs/" + run_id)).json()[
            "stage"
        ] == "completed_no_findings"
        assert container.scenario_scope._instances[run_id] is scoped_planner
        assert (await client.delete("/api/v1/runs/" + run_id)).status_code == 200
        assert run_id not in container.scenario_scope._instances


def test_manifest_uses_the_exact_exploratory_schema_and_prompt_commitment():
    from app.container import make_manifest_factory
    from app.features.fuzzing import exploratory_prompt_commitment
    from tests.workflow.coordinator_fixtures import Clock

    manifest = make_manifest_factory(Settings(app_mode="live"), Clock())("run", "live")
    commitment = exploratory_prompt_commitment()
    assert commitment in manifest.prompt_hashes
    assert (
        sum(
            item.prompt_name == commitment.prompt_name
            for item in manifest.prompt_hashes
        )
        == 1
    )
