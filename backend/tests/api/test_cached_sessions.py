"""Each cached replay is an independent public session with valid anchors."""

import asyncio

from app.core.config import Settings
from app.core.fakes import ScriptedLLMClient
from app.domain.models import RunRecord
from app.workflow.validation import validate_cached_record
from tests.api.test_container import bundled, client_for
from tests.workflow.coordinator_fixtures import Clock, cached_record


def public_record(stored):
    return RunRecord.model_validate_json(
        stored.model_dump_json(
            exclude={"version", "source_request", "pending_confirmation"}
        )
    )


async def test_repeated_concurrent_delete_and_expired_cached_sessions_are_fresh():
    from app.container import build_container

    source = cached_record()
    original = source.model_dump_json()
    clock = Clock()
    llm = ScriptedLLMClient([])
    container = build_container(
        Settings(app_mode="cached", run_ttl_seconds=1),
        cached_loader=lambda _: source,
        clock=clock,
        llm=llm,
    )
    async with client_for(container) as client:

        async def create():
            response = await client.post(
                "/api/v1/runs", json=bundled().model_dump(mode="json")
            )
            assert response.status_code == 202
            run_id = response.json()["run_id"]
            assert run_id != source.run_id
            stored = public_record(await container.coordinator.store.get(run_id))
            assert validate_cached_record(stored) == stored
            assert (await client.get("/api/v1/runs/" + run_id)).json()[
                "mode"
            ] == "cached"
            return run_id

        first, second = await asyncio.gather(create(), create())
        assert first != second
        assert (await client.delete("/api/v1/runs/" + first)).status_code == 200
        third = await create()
        assert third not in {first, second}
        assert (await client.get("/api/v1/runs/" + first)).status_code == 404
        clock.tick = 2
        assert (await client.get("/api/v1/runs/" + second)).status_code == 404
        assert (await client.get("/api/v1/runs/" + third)).status_code == 404
        fourth = await create()
        assert fourth not in {first, second, third}
        for old in (first, second, third):
            assert (await client.get("/api/v1/runs/" + old)).status_code == 404
        assert source.model_dump_json() == original
        assert llm.requests == []
