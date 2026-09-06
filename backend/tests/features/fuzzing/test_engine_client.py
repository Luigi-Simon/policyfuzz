"""Mocked HTTP tests for the sidecar engine client (no live network/LLM)."""

from __future__ import annotations

import json

import httpx
import pytest

from app.features.fuzzing.engine_client import EngineClientError, HttpPolicyEngineClient
from app.features.fuzzing.types import AudienceSegmentInput, RehearsalRequest


def _sample_run_payload(*, run_id: str = "run_abc", score: int = 64) -> dict:
    return {
        "run_id": run_id,
        "status": "completed",
        "ir": {
            "policy_id": "pol_1",
            "revision": 1,
            "rules": [{"id": "r1"}, {"id": "r2"}],
        },
        "suite": {"scenarios": [{"id": "s1"}, {"id": "s2"}, {"id": "s3"}]},
        "effectiveness": {
            "score": score,
            "justification": "Most scenarios held.",
            "recommended_actions": [
                {
                    "rule_ids": ["r1"],
                    "action": "clarify",
                    "summary": "Clarify phone storage.",
                }
            ],
            "swarm_used": False,
            "metrics": {"pass_rate": 0.7},
        },
        "error": None,
    }


def _handler(request: httpx.Request) -> httpx.Response:
    path = request.url.path
    if path == "/health":
        return httpx.Response(200, json={"ok": True, "service": "policy-engine"})
    if path == "/v1/runs" and request.method == "POST":
        # multipart/form or urlencoded body from httpx data=
        body = request.content.decode() if request.content else ""
        if "policy_text=" not in body and "policy_text" not in body:
            # also accept raw form fields via urlencode
            pass
        return httpx.Response(200, json=_sample_run_payload())
    if path.startswith("/v1/runs/") and path.endswith("/effectiveness"):
        return httpx.Response(
            200,
            json=_sample_run_payload()["effectiveness"],
        )
    if (
        path.startswith("/v1/runs/")
        and path.endswith("/revise")
        and request.method == "POST"
    ):
        payload = json.loads(request.content.decode())
        assert "instruction" in payload
        return httpx.Response(200, json=_sample_run_payload(run_id="run_rev", score=72))
    if path.startswith("/v1/runs/") and request.method == "GET":
        return httpx.Response(
            200, json=_sample_run_payload(run_id=path.rsplit("/", 1)[-1])
        )
    return httpx.Response(404, json={"detail": "not found"})


@pytest.fixture
def client() -> HttpPolicyEngineClient:
    transport = httpx.MockTransport(_handler)
    http = httpx.Client(base_url="http://engine.test", transport=transport)
    return HttpPolicyEngineClient(base_url="http://engine.test", client=http)


def test_health(client: HttpPolicyEngineClient) -> None:
    assert client.health()["ok"] is True


def test_create_rehearsal_maps_result(client: HttpPolicyEngineClient) -> None:
    result = client.create_rehearsal(
        RehearsalRequest(
            policy_text="Phones must be stored during class.",
            seed_text="School phone policy",
            population_size=12,
            locale="en-US",
            groups=("students", "teachers"),
            segments=(
                AudienceSegmentInput(id="students", label="Students", weight=0.6),
                AudienceSegmentInput(id="teachers", label="Teachers", weight=0.4),
            ),
        )
    )
    assert result.engine_run_id == "run_abc"
    assert result.status == "completed"
    assert result.policy_id == "pol_1"
    assert result.rule_count == 2
    assert result.scenario_count == 3
    assert result.score == 64
    assert result.effectiveness is not None
    assert result.effectiveness.recommended_actions[0].summary.startswith("Clarify")


def test_create_rejects_empty_policy(client: HttpPolicyEngineClient) -> None:
    with pytest.raises(EngineClientError) as exc:
        client.create_rehearsal(RehearsalRequest(policy_text="   "))
    assert exc.value.code == "ENGINE_EMPTY_POLICY"


def test_get_effectiveness(client: HttpPolicyEngineClient) -> None:
    view = client.get_effectiveness("run_abc")
    assert view.score == 64
    assert view.swarm_used is False


def test_revise(client: HttpPolicyEngineClient) -> None:
    result = client.revise("run_abc", "Clarify storage location.")
    assert result.engine_run_id == "run_rev"
    assert result.score == 72


def test_http_error_maps_code() -> None:
    def boom(request: httpx.Request) -> httpx.Response:
        return httpx.Response(503, json={"detail": "down"})

    http = httpx.Client(
        base_url="http://engine.test", transport=httpx.MockTransport(boom)
    )
    client = HttpPolicyEngineClient(client=http)
    with pytest.raises(EngineClientError) as exc:
        client.health()
    assert exc.value.code == "ENGINE_HEALTH_FAILED"
    assert "503" in str(exc.value)
