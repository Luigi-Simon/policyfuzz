from app.domain.export_schemas import build_openapi
from tests.api.conftest import api_harness


async def test_safe_health_and_cors():
    async with api_harness() as (client, _, _, _, _):
        response = await client.get("/api/v1/health")
        assert response.status_code == 200
        assert response.json() == {
            "schema_version": "1.0",
            "status": "ok",
            "provider_configured": False,
            "engine_version": "1.0",
        }
        for origin, permitted in [
            ("http://localhost:5173", True),
            ("https://evil.example", False),
        ]:
            response = await client.options(
                "/api/v1/runs",
                headers={"Origin": origin, "Access-Control-Request-Method": "POST"},
            )
            assert ("access-control-allow-origin" in response.headers) is permitted


async def test_openapi_matches_frozen_paths_models_and_statuses():
    async with api_harness() as (_, _, _, _, app):
        actual, frozen = app.openapi(), build_openapi()
        assert actual["paths"].keys() == frozen["paths"].keys()
        for path, methods in frozen["paths"].items():
            assert actual["paths"][path].keys() == methods.keys()
            for method, expected in methods.items():
                operation = actual["paths"][path][method]
                assert operation["operationId"] == expected["operationId"]
                assert operation.get("requestBody") == expected.get("requestBody")
                assert operation["responses"].keys() == expected["responses"].keys()
                for status, response in expected["responses"].items():
                    assert (
                        operation["responses"][status]["content"] == response["content"]
                    )


async def test_configured_health_redacts_credentials_and_model_identifier():
    from app.core.config import Settings

    async with api_harness() as (client, _, _, _, app):
        app.state.container.settings = Settings(
            app_mode="live", llm_model="SECRET-model", openai_api_key="SECRET-key"
        )
        response = await client.get("/api/v1/health")
        assert response.status_code == 200
        assert response.json()["provider_configured"] is True
        assert "SECRET" not in response.text


def test_invalid_local_origin_has_fixed_diagnostic():
    import pytest

    from app.main import create_app

    for origin in [
        "",
        "https://evil.example",
        "*",
        "http://localhost/path",
        "http://[SECRET",
        "http://localhost:SECRET",
    ]:
        with pytest.raises(
            ValueError, match="^A single local HTTP origin is required.$"
        ):
            create_app(allowed_origin=origin)


def test_generated_component_schemas_match_domain_contract():
    from app.main import create_app

    def omit_null_defaults(value):
        if isinstance(value, dict):
            return {
                key: omit_null_defaults(item)
                for key, item in value.items()
                if not (key == "default" and item is None)
            }
        if isinstance(value, list):
            return [omit_null_defaults(item) for item in value]
        return value

    # FastAPI omits null defaults when serializing its OpenAPI metadata.
    actual = create_app().openapi()["components"]["schemas"]
    expected = build_openapi()["components"]["schemas"]
    for name, schema in expected.items():
        assert omit_null_defaults(actual[name]) == omit_null_defaults(schema), name
