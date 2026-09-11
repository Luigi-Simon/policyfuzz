"""Tests for the standalone, fixture-only v2 first-run API."""

from __future__ import annotations

import asyncio
import hashlib
import json
from collections.abc import Callable
from typing import Any
from uuid import UUID

import httpx
import pytest

from app.v2.contracts import (
    ExecutionMode,
    SandboxRequest,
    SandboxResult,
    SandboxStatus,
    request_fingerprint,
)
from app.v2.fixtures import FixtureName, FixtureSandboxService
from app.v2.main import create_app
from app.v2.orchestrator import (
    AdapterExecutionError,
    Orchestrator,
)
from app.v2.run_models import CreateRunRequest, PublicError, PublicSandboxResult

POLICY = {
    "title": "Synthetic overnight transit policy",
    "description": "  Preserve this exact policy text.\n",
    "agent_seed": "Represent riders, operators, and accessibility advocates.",
    "agent_count": 3,
}


class CapturingFixtureService:
    def __init__(
        self,
        fixture_name: FixtureName,
        mutate: Callable[[SandboxResult], SandboxResult] | None = None,
    ) -> None:
        self.fixture_name = fixture_name
        self.mutate = mutate
        self.request: SandboxRequest | None = None

    async def run(self, request: SandboxRequest) -> SandboxResult:
        self.request = request
        result = await FixtureSandboxService(self.fixture_name).run(request)
        return self.mutate(result) if self.mutate else result


class RaisingService:
    async def run(self, request: SandboxRequest) -> SandboxResult:
        del request
        raise RuntimeError("private adapter detail")


class SlowService:
    async def run(self, request: SandboxRequest) -> SandboxResult:
        del request
        await asyncio.sleep(1)
        raise AssertionError("sleep should have been cancelled")


def run_request(*, agent_count: int = 3) -> CreateRunRequest:
    return CreateRunRequest.model_validate(
        {"policy": {**POLICY, "agent_count": agent_count}}
    )


@pytest.mark.parametrize(
    ("fixture_name", "expected_status", "expected_placeholder"),
    [
        ("completed", "completed", False),
        ("partial_translation_unavailable", "partial", True),
    ],
)
def test_run_returns_typed_public_fixture_result(
    fixture_name: FixtureName,
    expected_status: str,
    expected_placeholder: bool,
) -> None:
    app = create_app()
    payload = {"policy": POLICY, "fixture_name": fixture_name}

    response = asyncio.run(_request(app, "POST", "/api/v2/runs", json=payload))

    assert response.status_code == 200
    body = response.json()
    assert PublicSandboxResult.model_validate(body).status == expected_status
    assert body["execution_mode"] == "fixture"
    assert body["requested_stakeholder_count"] == 3
    assert body["configured_stakeholder_count"] == 3
    assert body["observed_stakeholder_count"] == 3
    assert (
        "[English translation unavailable for this record.]" in json.dumps(body)
    ) is expected_placeholder
    assert "original_records" not in body
    assert "乘客" not in json.dumps(body)


@pytest.mark.parametrize("agent_count", [1, 100])
def test_orchestrator_preserves_boundary_counts_and_exact_policy_binding(
    agent_count: int,
) -> None:
    services: list[CapturingFixtureService] = []

    def factory(fixture_name: FixtureName) -> CapturingFixtureService:
        service = CapturingFixtureService(fixture_name)
        services.append(service)
        return service

    result = asyncio.run(
        Orchestrator(service_factory=factory).run(run_request(agent_count=agent_count))
    )

    request = services[0].request
    assert request is not None
    assert UUID(request.request_id)
    assert UUID(request.run_id)
    assert request.request_id != request.run_id
    assert request.policy_version == "1"
    assert request.policy_title == POLICY["title"]
    assert request.policy_text == POLICY["description"]
    assert (
        request.policy_text_sha256
        == hashlib.sha256(POLICY["description"].encode("utf-8")).hexdigest()
    )
    assert request.personality_seed == POLICY["agent_seed"]
    assert request.stakeholder_count == agent_count
    assert request.context == ()
    assert request.scenario_setups == ()
    assert request.test_budget == 8
    assert result.request_id == request.request_id
    assert result.run_id == request.run_id
    assert result.request_fingerprint == request_fingerprint(request)
    assert result.requested_stakeholder_count == agent_count
    assert result.configured_stakeholder_count == agent_count
    assert result.observed_stakeholder_count == agent_count


def test_each_run_gets_fresh_request_and_run_ids() -> None:
    orchestrator = Orchestrator()

    first = asyncio.run(orchestrator.run(run_request()))
    second = asyncio.run(orchestrator.run(run_request()))

    assert first.request_id != second.request_id
    assert first.run_id != second.run_id


@pytest.mark.parametrize(
    "policy_update",
    [
        {"title": ""},
        {"title": "   \n"},
        {"title": "政 策"},
        {"title": "x" * 201},
        {"description": ""},
        {"description": "\t \n"},
        {"description": "x" * 50_001},
        {"agent_seed": ""},
        {"agent_seed": "  "},
        {"agent_seed": "x" * 2_001},
        {"agent_count": 0},
        {"agent_count": 101},
        {"agent_count": True},
        {"agent_count": 3.0},
        {"agent_count": "3"},
        {"supporting_documents": [{"document_id": "d", "title": "t", "text": "x"}]},
    ],
)
def test_invalid_input_returns_one_safe_fixed_error(
    policy_update: dict[str, Any],
) -> None:
    app = create_app()
    policy = {**POLICY, **policy_update}

    response = asyncio.run(
        _request(app, "POST", "/api/v2/runs", json={"policy": policy})
    )

    assert response.status_code == 422
    assert response.json() == {"detail": "Invalid run input."}
    assert POLICY["description"] not in response.text


def test_unknown_request_fields_are_rejected_safely() -> None:
    app = create_app()

    response = asyncio.run(
        _request(
            app,
            "POST",
            "/api/v2/runs",
            json={"policy": POLICY, "unexpected": "private"},
        )
    )

    assert response.status_code == 422
    assert response.json() == {"detail": "Invalid run input."}


@pytest.mark.parametrize(
    "mutate",
    [
        lambda result: result.model_copy(update={"request_id": "foreign-request"}),
        lambda result: result.model_copy(update={"run_id": "foreign-run"}),
        lambda result: result.model_copy(update={"request_fingerprint": "0" * 64}),
        lambda result: result.model_copy(update={"execution_mode": ExecutionMode.LIVE}),
        lambda result: result.model_copy(
            update={
                "messages": (
                    result.messages[0].model_copy(update={"content": "不安全"}),
                    *result.messages[1:],
                )
            }
        ),
    ],
)
def test_invalid_or_failed_adapter_results_fail_closed(
    mutate: Callable[[SandboxResult], SandboxResult],
) -> None:
    orchestrator = Orchestrator(
        service_factory=lambda name: CapturingFixtureService(name, mutate)
    )

    with pytest.raises(AdapterExecutionError, match="Sandbox execution failed"):
        asyncio.run(orchestrator.run(run_request()))


@pytest.mark.parametrize("status", [SandboxStatus.FAILED, SandboxStatus.CANCELLED])
def test_contract_valid_incomplete_status_remains_public(
    status: SandboxStatus,
) -> None:
    def mutate(result: SandboxResult) -> SandboxResult:
        updates: dict[str, Any] = {"status": status}
        if status is SandboxStatus.FAILED:
            updates["errors"] = ("The fixture adapter reported a safe failure.",)
        return result.model_copy(update=updates)

    result = asyncio.run(
        Orchestrator(
            service_factory=lambda name: CapturingFixtureService(name, mutate)
        ).run(run_request())
    )

    assert result.status is status
    assert "original_records" not in result.model_dump()


def test_adapter_exception_is_replaced_with_safe_502() -> None:
    app = create_app(
        Orchestrator(service_factory=lambda fixture_name: RaisingService())
    )

    response = asyncio.run(
        _request(app, "POST", "/api/v2/runs", json={"policy": POLICY})
    )

    assert response.status_code == 502
    assert response.json() == {"detail": "Sandbox execution failed."}
    assert "private adapter detail" not in response.text


def test_adapter_timeout_is_replaced_with_safe_504() -> None:
    app = create_app(
        Orchestrator(
            service_factory=lambda fixture_name: SlowService(), timeout_seconds=0.001
        )
    )

    response = asyncio.run(
        _request(app, "POST", "/api/v2/runs", json={"policy": POLICY})
    )

    assert response.status_code == 504
    assert response.json() == {"detail": "Sandbox execution timed out."}


def test_health_reports_fixture_mode() -> None:
    response = asyncio.run(_request(create_app(), "GET", "/api/v2/health"))

    assert response.status_code == 200
    assert response.json() == {"status": "ok", "execution_mode": "fixture"}


def test_public_model_and_schema_exclude_original_records() -> None:
    fields = set(PublicSandboxResult.model_fields)
    schema = PublicSandboxResult.model_json_schema()

    assert "original_records" not in fields
    assert "original_records" not in json.dumps(schema)
    with pytest.raises(ValueError):
        PublicSandboxResult.model_validate(
            {
                "schema_version": "2.0",
                "request_id": "request",
                "run_id": "run",
                "policy_version": "1",
                "policy_title": "Title",
                "policy_text_sha256": "0" * 64,
                "request_fingerprint": "1" * 64,
                "execution_mode": "fixture",
                "status": "cancelled",
                "requested_stakeholder_count": 1,
                "configured_stakeholder_count": 0,
                "observed_stakeholder_count": 0,
                "personas": [],
                "messages": [],
                "sources": [],
                "limitations": ["Cancelled."],
                "errors": [],
                "original_records": [],
            }
        )


def test_export_is_deterministic_and_check_detects_drift(tmp_path: Any) -> None:
    from app.v2 import export_api

    output = tmp_path / "v2-app"
    assert export_api.main(["--output", str(output)]) == 0
    first = {
        path.relative_to(output).as_posix(): path.read_bytes()
        for path in output.rglob("*")
        if path.is_file()
    }
    assert set(first) == {
        "openapi.json",
        "public-sandbox-result.schema.json",
        "workflow-result.schema.json",
    }
    assert export_api.main(["--output", str(output), "--check"]) == 0

    openapi = json.loads(first["openapi.json"])
    public_schema = json.loads(first["public-sandbox-result.schema.json"])
    assert "/api/v2/runs" in openapi["paths"]
    assert "original_records" not in json.dumps(openapi)
    assert "original_records" not in json.dumps(public_schema)
    for status_code in ("422", "502", "504"):
        schema_ref = openapi["paths"]["/api/v2/runs"]["post"]["responses"][status_code][
            "content"
        ]["application/json"]["schema"]["$ref"]
        assert schema_ref == "#/components/schemas/PublicError"
    assert PublicError.model_validate({"detail": "Safe message."}).detail == (
        "Safe message."
    )

    (output / "openapi.json").write_text("{}\n", encoding="utf-8")
    assert export_api.main(["--output", str(output), "--check"]) == 1


def test_fixture_name_defaults_to_completed() -> None:
    request = run_request()

    assert request.fixture_name == "completed"
    assert request.policy.model_dump() == POLICY


async def _request(app: Any, method: str, path: str, **kwargs: Any) -> httpx.Response:
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        return await client.request(method, path, **kwargs)
