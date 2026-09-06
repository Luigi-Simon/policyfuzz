import asyncio

import pytest

from app.workflow.errors import RunNotFoundError
from app.workflow.fake_stages import FakePolicyCompiler
from tests.api.conftest import api_harness
from tests.workflow.coordinator_fixtures import request


@pytest.mark.parametrize("reason", ["delete", "expiry", "shutdown"])
async def test_lifecycle_cancels_and_drains_blocked_stage(reason):
    entered, cleaned = asyncio.Event(), asyncio.Event()

    async def blocked(command):
        entered.set()
        try:
            await asyncio.Event().wait()
        finally:
            cleaned.set()

    async with api_harness(policy_compiler=FakePolicyCompiler([blocked])) as (
        client,
        _,
        parts,
        runner,
        _,
    ):
        await client.post("/api/v1/runs", json=request().model_dump(mode="json"))
        await asyncio.wait_for(entered.wait(), 1)
        if reason == "delete":
            assert (await client.delete("/api/v1/runs/run")).status_code == 200
        elif reason == "expiry":
            parts.clock.tick = 3601
            await runner.sweep()
        else:
            await runner.aclose()
        assert cleaned.is_set()
        assert runner.pending_count == 0
        with pytest.raises(RunNotFoundError):
            await parts.store.get("run")


async def test_expiry_drains_foreground_decision_job_and_returns_404():
    from app.workflow.fake_stages import FakeScenarioPlanner
    from tests.workflow.coordinator_fixtures import confirm

    entered, cleaned = asyncio.Event(), asyncio.Event()

    async def blocked(command):
        entered.set()
        try:
            await asyncio.Event().wait()
        finally:
            cleaned.set()

    async with api_harness(scenario_planner=FakeScenarioPlanner(initial=[blocked])) as (
        client,
        coordinator,
        parts,
        runner,
        _,
    ):
        await client.post("/api/v1/runs", json=request().model_dump(mode="json"))
        await runner.drain("run")
        command = confirm(await coordinator.get_run("run")).model_dump(mode="json")
        call = asyncio.create_task(
            client.post("/api/v1/runs/run/confirm-contract", json=command)
        )
        await asyncio.wait_for(entered.wait(), 1)
        parts.clock.tick = 3601
        await runner.sweep()
        response = await asyncio.wait_for(call, 1)
        assert response.status_code == 404
        assert cleaned.is_set()


async def test_lifespan_reaper_expires_without_an_http_read():
    entered, cleaned = asyncio.Event(), asyncio.Event()

    async def blocked(command):
        entered.set()
        try:
            await asyncio.Event().wait()
        finally:
            cleaned.set()

    async with api_harness(policy_compiler=FakePolicyCompiler([blocked])) as (
        client,
        _,
        parts,
        runner,
        _,
    ):
        await client.post("/api/v1/runs", json=request().model_dump(mode="json"))
        await asyncio.wait_for(entered.wait(), 1)
        parts.clock.tick = 3601
        await asyncio.wait_for(cleaned.wait(), 1)
        assert runner.pending_count == 0


async def test_container_closes_storage_even_with_an_injected_runner():
    from app.container import AppContainer
    from app.core.config import Settings
    from tests.workflow.coordinator_fixtures import harness

    coordinator, parts = harness()
    await coordinator.create_run(request())

    class Runner:
        async def aclose(self):
            return None

    container = AppContainer(
        coordinator=coordinator,
        task_runner=Runner(),
        settings=Settings(app_mode="cached"),
        engine_version="1.0",
    )
    await container.aclose()
    with pytest.raises(RunNotFoundError):
        await parts.store.get("run")
