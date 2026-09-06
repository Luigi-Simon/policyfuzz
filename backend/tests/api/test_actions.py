from tests.api.conftest import api_harness
from tests.workflow.coordinator_fixtures import confirm, request


async def test_wrong_state_and_stale_hash():
    async with api_harness() as (client, coordinator, _, runner, _):
        await client.post("/api/v1/runs", json=request().model_dump(mode="json"))
        await runner.drain("run")
        response = await client.post(
            "/api/v1/runs/run/confirm-revision",
            json={"decision": "confirm", "proposal_id": "proposal"},
        )
        assert response.status_code == 409
        assert response.json()["error"]["code"] == "INVALID_STATE"
        view = await coordinator.get_run("run")
        command = confirm(view).model_dump(mode="json")
        command["baseline_policy_sha256"] = "0" * 64
        response = await client.post("/api/v1/runs/run/confirm-contract", json=command)
        assert response.status_code == 409
        assert response.json()["error"]["code"] == "HASH_MISMATCH"
        assert (await client.get("/api/v1/runs/run")).json()[
            "stage"
        ] == "awaiting_contract"


async def test_contract_confirmation_returns_frozen_run_view():
    async with api_harness() as (client, coordinator, _, runner, _):
        await client.post("/api/v1/runs", json=request().model_dump(mode="json"))
        await runner.drain("run")
        command = confirm(await coordinator.get_run("run"))
        response = await client.post(
            "/api/v1/runs/run/confirm-contract", json=command.model_dump(mode="json")
        )
        assert response.status_code == 200
        assert response.json()["stage"] == "generating_initial_tests"
        await runner.drain("run")
        assert (await client.get("/api/v1/runs/run")).json()[
            "stage"
        ] == "completed_no_findings"


async def test_complete_revision_through_all_http_actions():
    from app.workflow.fake_stages import (
        FakeFindingAnalyzer,
        FakeRegressionAnalyzer,
        FakeRevisionApplier,
        FakeRevisionPlanner,
    )
    from tests.workflow.coordinator_fixtures import (
        apply,
        compare,
        findings,
        one_finding,
        proposal,
        selection,
    )

    async with api_harness(
        finding_analyzer=FakeFindingAnalyzer([one_finding, findings]),
        revision_planner=FakeRevisionPlanner([proposal]),
        revision_applier=FakeRevisionApplier([apply]),
        regression_analyzer=FakeRegressionAnalyzer([compare]),
    ) as (client, coordinator, _, runner, _):
        await client.post("/api/v1/runs", json=request().model_dump(mode="json"))
        await runner.drain("run")
        command = confirm(await coordinator.get_run("run"))
        response = await client.post(
            "/api/v1/runs/run/confirm-contract", json=command.model_dump(mode="json")
        )
        assert response.status_code == 200
        assert response.json()["stage"] == "generating_initial_tests"
        await runner.drain("run")
        assert (await client.get("/api/v1/runs/run")).json()[
            "stage"
        ] == "awaiting_finding_review"
        response = await client.post(
            "/api/v1/runs/run/select-findings", json=selection().model_dump(mode="json")
        )
        assert response.status_code == 200
        assert response.json()["stage"] == "drafting_revision"
        await runner.drain("run")
        assert (await client.get("/api/v1/runs/run")).json()[
            "stage"
        ] == "awaiting_revision_confirmation"
        response = await client.post(
            "/api/v1/runs/run/confirm-revision",
            json={"decision": "confirm", "proposal_id": "proposal"},
        )
        assert response.status_code == 200
        assert response.json()["stage"] == "complete"
