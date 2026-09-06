from contextlib import asynccontextmanager

from httpx import ASGITransport, AsyncClient

from app.core.config import Settings
from tests.workflow.coordinator_fixtures import harness


@asynccontextmanager
async def api_harness(**overrides):
    from app.container import AppContainer
    from app.main import create_app
    from app.workflow.task_runner import AsyncTaskRunner

    coordinator, parts = harness(**overrides)
    runner = AsyncTaskRunner(parts.store, parts.clock)
    container = AppContainer(
        coordinator=coordinator,
        task_runner=runner,
        settings=Settings(app_mode="cached"),
        engine_version="1.0",
    )
    app = create_app(container=container)
    async with (
        app.router.lifespan_context(app),
        AsyncClient(
            transport=ASGITransport(app=app, raise_app_exceptions=False),
            base_url="http://test",
        ) as client,
    ):
        yield client, coordinator, parts, runner, app
