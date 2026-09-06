from tests.api.conftest import api_harness
from tests.workflow.coordinator_fixtures import request


async def test_create_get_delete_safe_run():
    async with api_harness() as (client, _, _, runner, _):
        response = await client.post(
            "/api/v1/runs", json=request().model_dump(mode="json")
        )
        assert response.status_code == 202
        assert response.json() == {"schema_version": "1.0", "run_id": "run"}
        await runner.drain("run")
        response = await client.get("/api/v1/runs/run")
        assert response.status_code == 200
        assert response.json()["stage"] == "awaiting_contract"
        assert (await client.get("/api/v1/runs/run")).json() == response.json()
        assert "source_request" not in response.text
        deleted = await client.delete("/api/v1/runs/run")
        assert deleted.status_code == 200
        assert deleted.json() == {
            "schema_version": "1.0",
            "run_id": "run",
            "deleted": True,
        }
        assert (await client.get("/api/v1/runs/run")).status_code == 404


async def test_unknown_and_expired_run():
    async with api_harness() as (client, _, parts, runner, _):
        assert (await client.get("/api/v1/runs/unknown")).status_code == 404
        await client.post("/api/v1/runs", json=request().model_dump(mode="json"))
        await runner.drain("run")
        parts.clock.tick = 3601
        assert (await client.get("/api/v1/runs/run")).status_code == 404
