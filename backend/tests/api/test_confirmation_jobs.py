"""HTTP decisions commit promptly while owned model continuations remain blocked."""

import asyncio
from contextlib import asynccontextmanager

import pytest
from httpx import ASGITransport, AsyncClient

from app.domain.models import RunView
from app.workflow.errors import RunNotFoundError
from app.workflow.fake_stages import (
    FakeFindingAnalyzer,
    FakeRevisionPlanner,
    FakeScenarioPlanner,
)
from tests.api.conftest import api_harness
from tests.workflow.coordinator_fixtures import (
    assemble,
    batch,
    confirm,
    one_finding,
    proposal,
    request,
    selection,
)


@asynccontextmanager
async def decision_harness(action, *, failure=None):
    entered, release, cleaned = asyncio.Event(), asyncio.Event(), asyncio.Event()
    calls = []

    async def blocked(command):
        calls.append(command)
        entered.set()
        try:
            await release.wait()
            if failure is not None:
                raise failure
            return batch(command) if action == "confirm-contract" else proposal(command)
        finally:
            cleaned.set()

    overrides = {"finding_analyzer": FakeFindingAnalyzer([one_finding])}
    if action == "confirm-contract":
        overrides["scenario_planner"] = FakeScenarioPlanner(
            initial=[blocked], suites=[assemble]
        )
    else:
        overrides["revision_planner"] = FakeRevisionPlanner([blocked])
    async with api_harness(**overrides) as context:
        client, coordinator, parts, runner, app = context
        await coordinator.create_run(request())
        await coordinator.start("run")
        command = confirm(await coordinator.get_run("run"))
        if action == "select-findings":
            await coordinator.confirm_contract("run", command)
            command = selection()
        try:
            yield (
                client,
                coordinator,
                parts,
                runner,
                app,
                command.model_dump(mode="json"),
                entered,
                release,
                cleaned,
                calls,
            )
        finally:
            release.set()


@pytest.mark.parametrize(
    ("action", "active", "next_stage"),
    [
        ("confirm-contract", "generating_initial_tests", "awaiting_finding_review"),
        ("select-findings", "drafting_revision", "awaiting_revision_confirmation"),
    ],
)
async def test_confirmation_returns_persisted_active_view_before_model_finishes(
    action, active, next_stage
):
    async with decision_harness(action) as context:
        client, _, parts, runner, _, command, entered, release, _, calls = context
        call = asyncio.create_task(
            client.post(f"/api/v1/runs/run/{action}", json=command)
        )
        await asyncio.wait_for(entered.wait(), 1)
        try:
            # Only a deadlock guard: the fake stays blocked until after the response.
            response = await asyncio.wait_for(asyncio.shield(call), 1)
            assert response.status_code == 200
            view = RunView.model_validate_json(response.content)
            assert view.stage == active
            assert view.pending_confirmation is None
            assert (await parts.store.get("run")).stage == active
            assert (await client.get("/api/v1/runs/run")).json()["stage"] == active
            assert runner.pending_count == 1
            assert len(calls) == 1
            release.set()
            await runner.drain("run")
            assert (await client.get("/api/v1/runs/run")).json()["stage"] == next_stage
        finally:
            release.set()
            await call


@pytest.mark.parametrize("action", ["confirm-contract", "select-findings"])
async def test_invalid_decisions_do_not_mutate_or_submit_jobs(action, monkeypatch):
    async with decision_harness(action) as context:
        client, _, parts, runner, _, command, _, _, _, calls = context
        submitted = []
        original_submit = runner.submit

        def submit(run_id, work):
            submitted.append(run_id)
            return original_submit(run_id, work)

        monkeypatch.setattr(runner, "submit", submit)
        before = await parts.store.get("run")
        if action == "confirm-contract":
            command["baseline_policy_sha256"] = "0" * 64
            expected_status, expected_code = 409, "HASH_MISMATCH"
        else:
            command["decisions"][0]["reviewer_severity"] = None
            expected_status, expected_code = 422, "INVALID_INPUT"
        response = await client.post(f"/api/v1/runs/run/{action}", json=command)
        assert response.status_code == expected_status
        assert response.json()["error"]["code"] == expected_code
        assert await parts.store.get("run") == before
        assert submitted == []
        assert calls == []


@pytest.mark.parametrize("action", ["confirm-contract", "select-findings"])
async def test_duplicate_decisions_start_exactly_one_continuation(action, monkeypatch):
    async with decision_harness(action) as context:
        client, coordinator, parts, runner, _, command, entered, release, _, calls = (
            context
        )
        original_at = coordinator._at
        both_read = asyncio.Event()
        reads = []

        async def same_version(run_id, stage):
            record = await original_at(run_id, stage)
            reads.append(record.version)
            if len(reads) == 2:
                both_read.set()
            await both_read.wait()
            return record

        monkeypatch.setattr(coordinator, "_at", same_version)
        responses = await asyncio.wait_for(
            asyncio.gather(
                client.post(f"/api/v1/runs/run/{action}", json=command),
                client.post(f"/api/v1/runs/run/{action}", json=command),
            ),
            1,
        )
        assert sorted(response.status_code for response in responses) == [200, 409]
        rejected = next(
            response for response in responses if response.status_code == 409
        )
        assert rejected.json()["error"]["code"] == "INVALID_STATE"
        assert len(set(reads)) == 1
        await asyncio.wait_for(entered.wait(), 1)
        assert len(calls) == 1
        assert runner.pending_count == 1
        record = await parts.store.get("run")
        assert sum(event.stage == record.stage for event in record.events) == 1
        release.set()
        await runner.drain("run")
        assert len(calls) == 1


@pytest.mark.parametrize("action", ["confirm-contract", "select-findings"])
@pytest.mark.parametrize("reason", ["delete", "expiry", "shutdown"])
async def test_lifecycle_drains_accepted_continuation_without_resurrection(
    action, reason
):
    async with decision_harness(action) as context:
        client, _, parts, runner, _, command, entered, release, cleaned, _ = context
        response = await asyncio.wait_for(
            client.post(f"/api/v1/runs/run/{action}", json=command), 1
        )
        assert response.status_code == 200
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
        release.set()
        await runner.drain("run")
        with pytest.raises(RunNotFoundError):
            await parts.store.get("run")
        assert (await client.get("/api/v1/runs/run")).status_code == 404


@pytest.mark.parametrize("action", ["confirm-contract", "select-findings"])
async def test_cancelled_http_response_keeps_accepted_continuation(action):
    async with decision_harness(action) as context:
        _, coordinator, _, runner, app, command, entered, release, cleaned, _ = context
        responding = asyncio.Event()

        async def hold_response(scope, receive, send):
            async def gated_send(message):
                if message["type"] == "http.response.start":
                    responding.set()
                    await asyncio.Event().wait()
                await send(message)

            await app(scope, receive, gated_send)

        async with AsyncClient(
            transport=ASGITransport(app=hold_response), base_url="http://test"
        ) as client:
            call = asyncio.create_task(
                client.post(f"/api/v1/runs/run/{action}", json=command)
            )
            await asyncio.wait_for(responding.wait(), 1)
            await asyncio.wait_for(entered.wait(), 1)
            call.cancel()
            with pytest.raises(asyncio.CancelledError):
                await call
            assert not cleaned.is_set()
            assert runner.pending_count == 1
            release.set()
            await runner.drain("run")
            view = await coordinator.get_run("run")
            assert view.stage == (
                "awaiting_finding_review"
                if action == "confirm-contract"
                else "awaiting_revision_confirmation"
            )


@pytest.mark.parametrize("action", ["confirm-contract", "select-findings"])
async def test_rejected_decisions_are_immediate_terminal_results(action):
    async with decision_harness(action) as context:
        client, _, _, runner, _, _, _, _, _, calls = context
        command = (
            {"decision": "reject"}
            if action == "confirm-contract"
            else selection(None, "reject").model_dump(mode="json")
        )
        response = await client.post(f"/api/v1/runs/run/{action}", json=command)
        assert response.status_code == 200
        assert response.json()["stage"] == (
            "contract_rejected"
            if action == "confirm-contract"
            else "completed_no_revision"
        )
        assert runner.pending_count == 0
        assert calls == []


@pytest.mark.parametrize("action", ["confirm-contract", "select-findings"])
async def test_continuation_failure_is_safely_visible_to_polling(action):
    async with decision_harness(
        action, failure=RuntimeError("SECRET provider data")
    ) as context:
        client, _, _, runner, _, command, entered, release, _, _ = context
        response = await client.post(f"/api/v1/runs/run/{action}", json=command)
        assert response.status_code == 200
        await asyncio.wait_for(entered.wait(), 1)
        release.set()
        await runner.drain("run")
        response = await client.get("/api/v1/runs/run")
        assert response.json()["stage"] == "failed"
        assert "SECRET" not in response.text
        assert runner.pending_count == 0
