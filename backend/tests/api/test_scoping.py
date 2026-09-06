import asyncio

from app.container import ScopedScenarioPlanner
from app.workflow.fake_stages import FakeScenarioPlanner
from tests.workflow.coordinator_fixtures import (
    assemble,
    batch,
    confirm,
    harness,
    request,
)


async def test_concurrent_runs_get_independent_planner_budgets_and_cleanup():
    instances = []

    def factory(manifest):
        planner = FakeScenarioPlanner(initial=[batch], suites=[assemble])
        instances.append((manifest.run_id, planner))
        return planner

    scope = ScopedScenarioPlanner(factory)

    async def run(run_id):
        coordinator, parts = harness(
            scenario_planner=scope, run_id_factory=lambda: run_id
        )
        await coordinator.create_run(request())
        await coordinator.start(run_id)
        command = confirm(await coordinator.get_run(run_id))
        manifest = (await parts.store.get(run_id)).manifest
        view = await scope.execute(
            manifest, lambda: coordinator.confirm_contract(run_id, command)
        )
        assert view.stage == "completed_no_findings"
        return manifest

    first, second = await asyncio.gather(run("first"), run("second"))
    assert {run_id for run_id, _ in instances} == {"first", "second"}
    assert instances[0][1] is not instances[1][1]
    scope.discard(first.run_id)

    async def no_work():
        return None

    await scope.execute(first, no_work)
    await scope.execute(second, no_work)
    assert [run_id for run_id, _ in instances].count("first") == 2
    assert [run_id for run_id, _ in instances].count("second") == 1


async def test_container_shutdown_releases_directly_scoped_planners():
    import weakref

    from app.container import AppContainer
    from app.core.config import Settings
    from app.workflow.task_runner import AsyncTaskRunner

    references = []

    def factory(manifest):
        planner = FakeScenarioPlanner()
        references.append(weakref.ref(planner))
        return planner

    scope = ScopedScenarioPlanner(factory)
    coordinator, parts = harness()
    await coordinator.create_run(request())
    container = AppContainer(
        coordinator=coordinator,
        task_runner=AsyncTaskRunner(parts.store, parts.clock),
        settings=Settings(app_mode="cached"),
        engine_version="1.0",
        scenario_scope=scope,
    )

    async def no_work():
        return None

    await container.execute("run", no_work)
    assert references[0]() is not None
    await container.aclose()
    assert references[0]() is None
