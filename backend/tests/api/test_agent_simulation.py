"""Exploratory sidecar work must not stall the core API or leak its errors."""

import asyncio
import threading
from types import SimpleNamespace

import httpx
import pytest

from app.api import routes
from tests.api.conftest import api_harness
from tests.workflow.coordinator_fixtures import confirm, request

COMMAND = {
    "title": "Synthetic test policy",
    "policy_text": "Receipts are required for meals.",
    "seed_text": "Employees submitting meals",
    "population_size": 3,
    "groups": ["employees"],
    "non_confidential_confirmed": True,
}


def install_client(monkeypatch, *, failure=None, entered=None, release=None):
    clients = []

    class Client:
        def __init__(self, **kwargs):
            self.closed = False
            clients.append(self)

        def create_rehearsal(self, request):
            return SimpleNamespace(engine_run_id="engine-one", error=None)

        def rehearse(self, run_id, *, swarm):
            if entered is not None:
                entered.set()
                # Bound a broken baseline so a failed test cannot hang the suite.
                release.wait(2)
            if failure:
                raise failure
            return SimpleNamespace(raw={"run_id": run_id, "status": "completed"})

        def close(self):
            self.closed = True

    monkeypatch.setattr(routes, "HttpPolicyEngineClient", Client)
    return clients


async def test_long_simulation_keeps_core_health_responsive(monkeypatch):
    entered, release = threading.Event(), threading.Event()
    clients = install_client(monkeypatch, entered=entered, release=release)
    async with api_harness() as (client, *_):
        task = asyncio.create_task(
            client.post("/api/v1/custom-agent-simulation", json=COMMAND)
        )
        try:
            assert await asyncio.to_thread(entered.wait, 3)
            response = await asyncio.wait_for(client.get("/api/v1/health"), 1)
            assert response.status_code == 200
            assert not task.done(), (
                "Simulation blocked the event loop until it completed"
            )
        finally:
            release.set()
            await task
    assert clients[0].closed


@pytest.mark.parametrize(
    "failure",
    [
        httpx.ConnectError("PRIVATE provider detail"),
        httpx.ReadTimeout("PRIVATE timeout"),
    ],
)
async def test_simulation_transport_failure_has_actionable_safe_error(
    monkeypatch, failure
):
    clients = install_client(monkeypatch, failure=failure)
    async with api_harness() as (client, *_):
        response = await client.post("/api/v1/custom-agent-simulation", json=COMMAND)
    assert response.status_code == 503
    assert response.json()["error"]["code"] == "PROVIDER_UNAVAILABLE"
    assert "simulation" in response.json()["error"]["message"].lower()
    assert "PRIVATE" not in response.text
    assert clients[0].closed


async def test_simulation_result_declares_independent_exploratory_scope(monkeypatch):
    install_client(monkeypatch)
    async with api_harness() as (client, *_):
        response = await client.post("/api/v1/custom-agent-simulation", json=COMMAND)
    assert response.status_code == 200
    payload = response.json()
    assert payload["evidence_scope"] == "independent_exploratory_simulation"
    assert payload["frozen_suite_reused"] is False


async def test_unacknowledged_policy_never_reaches_sidecar(monkeypatch):
    clients = install_client(monkeypatch)
    async with api_harness() as (client, *_):
        response = await client.post(
            "/api/v1/custom-agent-simulation",
            json={**COMMAND, "non_confidential_confirmed": False},
        )
    assert response.status_code == 422
    assert clients == []


@pytest.mark.parametrize(
    "path", ["/api/v1/custom-agent-simulation", "/api/v1/agent-simulation/engine-one"]
)
async def test_client_configuration_failure_is_safe_and_actionable(monkeypatch, path):
    def broken_client(**kwargs):
        raise ValueError("PRIVATE malformed simulation URL")

    monkeypatch.setattr(routes, "HttpPolicyEngineClient", broken_client)
    async with api_harness() as (client, *_):
        response = (
            await client.post(path, json=COMMAND)
            if path.endswith("custom-agent-simulation")
            else await client.get(path)
        )
    assert response.status_code == 503
    assert "simulation" in response.json()["error"]["message"].lower()
    assert "PRIVATE" not in response.text


async def test_close_failure_does_not_replace_the_original_transport_error(monkeypatch):
    class Client:
        def __init__(self, **kwargs):
            pass

        def create_rehearsal(self, request):
            raise httpx.ConnectError("PRIVATE connection detail")

        def close(self):
            raise RuntimeError("PRIVATE cleanup detail")

    monkeypatch.setattr(routes, "HttpPolicyEngineClient", Client)
    async with api_harness() as (client, *_):
        response = await client.post("/api/v1/custom-agent-simulation", json=COMMAND)
    assert response.status_code == 503
    assert "PRIVATE" not in response.text


@pytest.mark.parametrize("stale", [False, True])
async def test_confirmed_launch_checks_anchors_but_does_not_claim_frozen_suite_reuse(
    monkeypatch, stale
):
    clients = install_client(monkeypatch)
    async with api_harness() as (client, coordinator, parts, *_):
        await coordinator.create_run(request())
        await coordinator.start("run")
        await coordinator.confirm_contract(
            "run", confirm(await coordinator.get_run("run"))
        )
        record = await parts.store.get("run")
        hashes = {
            artifact.artifact_type: artifact.artifact_sha256
            for artifact in record.artifacts
        }
        command = {
            "confirmation": "confirmed",
            "policy_ir_sha256": hashes["policy_ir"],
            "policy_contract_sha256": hashes["policy_contract"],
            "scenario_suite_sha256": "0" * 64 if stale else hashes["scenario_suite"],
        }
        response = await client.post("/api/v1/runs/run/agent-simulation", json=command)
    if stale:
        assert response.status_code == 409
        assert response.json()["error"]["code"] == "HASH_MISMATCH"
        assert clients == []
    else:
        assert response.status_code == 200
        assert response.json()["source_policyfuzz_run_id"] == "run"
        assert response.json()["evidence_scope"] == "independent_exploratory_simulation"
        assert response.json()["frozen_suite_reused"] is False
        assert (
            response.json()["source_artifact_hashes"]["scenario_suite"]
            == hashes["scenario_suite"]
        )
