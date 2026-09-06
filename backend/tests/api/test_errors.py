import pytest

from app.core.errors import LLMTransportError
from app.domain.models import LLMError
from app.workflow.fake_stages import FakePolicyCompiler
from tests.api.conftest import api_harness
from tests.workflow.coordinator_fixtures import request


@pytest.mark.parametrize(
    "changes",
    [
        {"text": ""},
        {"text": " "},
        {"text": "SECRET" * 9000},
        {"non_confidential_confirmed": False},
        {"source_type": "pdf"},
        {"SECRET_FIELD": "SECRET_VALUE"},
        {"title": {"SECRET_FIELD": "SECRET_VALUE"}},
    ],
)
async def test_422_never_contains_pydantic_input(changes):
    async with api_harness() as (client, *_):
        body = request().model_dump(mode="json") | changes
        response = await client.post("/api/v1/runs", json=body)
        assert response.status_code == 422
        assert response.json()["error"]["code"] == "INVALID_INPUT"
        assert "SECRET" not in response.text
        assert "input" not in response.json()


async def test_malformed_json_is_safe():
    async with api_harness() as (client, *_):
        response = await client.post(
            "/api/v1/runs",
            content='{"SECRET":',
            headers={"content-type": "application/json"},
        )
        assert response.status_code == 422
        assert "SECRET" not in response.text


async def test_provider_failure_is_safe_run_error():
    failure = LLMTransportError(LLMError(code="timeout", operation="policy_extraction"))
    async with api_harness(policy_compiler=FakePolicyCompiler([failure])) as (
        client,
        _,
        _,
        runner,
        _,
    ):
        assert (
            await client.post("/api/v1/runs", json=request().model_dump(mode="json"))
        ).status_code == 202
        await runner.drain("run")
        view = (await client.get("/api/v1/runs/run")).json()
        assert view["stage"] == "failed"
        assert view["error"]["code"] == "PROVIDER_UNAVAILABLE"


async def test_synchronous_internal_error_is_redacted_and_readable_by_local_client():
    def failed_manifest(run_id, mode):
        raise RuntimeError("SECRET-input-and-credentials")

    async with api_harness(manifest_factory=failed_manifest) as (client, *_):
        response = await client.post(
            "/api/v1/runs",
            json=request().model_dump(mode="json"),
            headers={"Origin": "http://localhost:5173"},
        )
        assert response.status_code == 500
        assert response.json()["error"]["code"] == "INTERNAL_ERROR"
        assert "SECRET" not in response.text
        assert (
            response.headers["access-control-allow-origin"] == "http://localhost:5173"
        )


async def test_corrupt_cache_uses_documented_create_error_status():
    async with api_harness(
        mode="cached", cached_loader=lambda command: {"SECRET": "INVALID_CACHE"}
    ) as (client, *_):
        response = await client.post(
            "/api/v1/runs",
            json={
                "source_type": "bundled_sample",
                "sample_id": "development-policy",
                "title": "Synthetic",
            },
        )
        assert response.status_code == 500
        assert response.json()["error"]["code"] == "HASH_MISMATCH"
        assert "SECRET" not in response.text


@pytest.mark.parametrize(
    "path", ["/api/v1/runs", "/api/v1/runs/unknown/confirm-contract"]
)
@pytest.mark.parametrize(
    "media,body",
    [
        ("text/plain", b"synthetic body"),
        ("application/octet-stream", b"body"),
        ("application/json", b"\xff"),
    ],
)
async def test_invalid_body_media_and_utf8_use_public_422(path, media, body):
    async with api_harness() as (client, _, parts, _, _):
        response = await client.post(
            path,
            content=body,
            headers={"Content-Type": media, "Origin": "http://localhost:5173"},
        )
        assert response.status_code == 422
        assert response.json()["error"]["code"] == "INVALID_INPUT"
        assert "detail" not in response.json()
        assert (
            response.headers["access-control-allow-origin"] == "http://localhost:5173"
        )
        assert parts.policy_compiler.calls == 0
