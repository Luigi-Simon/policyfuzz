"""The generated registry is deterministic, complete, and check-only when asked."""

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest
from pydantic import BaseModel

from app.domain import models
from app.domain.export_schemas import build_openapi, build_schemas

BACKEND = Path(__file__).resolve().parents[2]


def cli(*args, seed="1"):
    return subprocess.run(
        [sys.executable, "-m", "app.domain.export_schemas", *map(str, args)],
        cwd=BACKEND,
        env={**os.environ, "PYTHONHASHSEED": seed},
        capture_output=True,
        text=True,
        check=False,
    )


def snapshot(directory):
    return {
        str(p.relative_to(directory)): p.read_bytes()
        for p in directory.rglob("*")
        if p.is_file()
    }


def assert_refs_resolve(document):
    def resolve(ref):
        assert ref.startswith("#/")
        value = document
        for part in ref[2:].split("/"):
            value = value[part.replace("~1", "/").replace("~0", "~")]
        return value

    def walk(value):
        if isinstance(value, dict):
            if "$ref" in value:
                assert isinstance(resolve(value["$ref"]), dict)
            if "discriminator" in value:
                for ref in value["discriminator"].get("mapping", {}).values():
                    resolve(ref)
            for item in value.values():
                walk(item)
        elif isinstance(value, list):
            for item in value:
                walk(item)

    walk(document)


def test_individual_schemas_cover_every_exported_concrete_model_and_resolve_refs():
    expected = {
        name
        for name in models.__all__
        if isinstance(getattr(models, name), type)
        and issubclass(getattr(models, name), BaseModel)
        and name != "StrictModel"
    }
    schemas = build_schemas()
    assert set(schemas) == {f"{name}.schema.json" for name in expected}
    for filename, schema in schemas.items():
        assert (
            schema
            == getattr(
                models, filename.removesuffix(".schema.json")
            ).model_json_schema()
        )
        assert_refs_resolve(schema)


def test_openapi_has_exact_operations_request_responses_and_safe_errors():
    document = build_openapi()
    assert document["openapi"] == "3.1.0"
    assert document["info"] == {"title": "PolicyFuzz API", "version": "1.0"}
    expected = {
        ("/api/v1/runs", "post"): ("CreateRunRequest", "202", "CreateRunResponse"),
        ("/api/v1/runs/{run_id}", "get"): (None, "200", "RunView"),
        ("/api/v1/runs/{run_id}/confirm-contract", "post"): (
            "ConfirmContractRequest",
            "200",
            "RunView",
        ),
        ("/api/v1/runs/{run_id}/select-findings", "post"): (
            "SelectFindingsRequest",
            "200",
            "RunView",
        ),
        ("/api/v1/runs/{run_id}/confirm-revision", "post"): (
            "ConfirmRevisionRequest",
            "200",
            "RunView",
        ),
        ("/api/v1/runs/{run_id}", "delete"): (None, "200", "DeleteRunResponse"),
        ("/api/v1/health", "get"): (None, "200", "HealthResponse"),
    }
    operations = {
        (path, method): op
        for path, methods in document["paths"].items()
        for method, op in methods.items()
    }
    assert operations.keys() == expected.keys()
    assert len({op["operationId"] for op in operations.values()}) == 7
    for key, (request, status, response) in expected.items():
        operation = operations[key]
        assert operation["responses"][status]["content"]["application/json"][
            "schema"
        ] == {"$ref": f"#/components/schemas/{response}"}
        if request:
            assert operation["requestBody"]["required"] is True
            assert operation["requestBody"]["content"]["application/json"][
                "schema"
            ] == {"$ref": f"#/components/schemas/{request}"}
        else:
            assert "requestBody" not in operation
        if "{run_id}" in key[0]:
            assert operation["parameters"] == [
                {
                    "name": "run_id",
                    "in": "path",
                    "required": True,
                    "schema": {"type": "string"},
                }
            ]
        for code, error in operation["responses"].items():
            if code == status:
                continue
            assert code in {"404", "409", "422", "500", "502", "503"}
            schema = error["content"]["application/json"]["schema"]
            assert schema == {
                "type": "object",
                "required": ["error"],
                "additionalProperties": False,
                "properties": {"error": {"$ref": "#/components/schemas/PublicError"}},
            }
    for action in ("confirm-contract", "select-findings", "confirm-revision"):
        assert {"404", "409", "422", "500", "502", "503"} <= operations[
            (f"/api/v1/runs/{{run_id}}/{action}", "post")
        ]["responses"].keys()
    assert_refs_resolve(document)
    # Components must be reachable from paths, with no private/scoring artifacts.
    reachable = set()

    def visit(value):
        if isinstance(value, dict):
            if "$ref" in value:
                name = value["$ref"].removeprefix("#/components/schemas/")
                if name not in reachable:
                    reachable.add(name)
                    visit(document["components"]["schemas"][name])
            for child in value.values():
                visit(child)
        elif isinstance(value, list):
            for child in value:
                visit(child)

    visit(document["paths"])
    assert reachable == document["components"]["schemas"].keys()
    assert (
        not {"StrictModel", "RunManifest", "BenchmarkManifest", "AssertionTransition"}
        & reachable
    )


def test_exports_are_byte_stable_across_processes(tmp_path):
    first, second = tmp_path / "first", tmp_path / "second"
    for directory, seed in ((first, "1"), (second, "937")):
        result = cli(
            "--output",
            directory / "schemas",
            "--openapi",
            directory / "openapi.json",
            seed=seed,
        )
        assert result.returncode == 0, result.stderr
    assert snapshot(first) == snapshot(second)
    for data in snapshot(first).values():
        assert data == (
            json.dumps(json.loads(data), ensure_ascii=False, indent=2, sort_keys=True)
            + "\n"
        ).encode("utf-8")


@pytest.mark.parametrize("drift", ["missing", "modified", "unexpected", "openapi"])
def test_check_detects_drift_without_mutation_and_generation_repairs(tmp_path, drift):
    schemas, openapi = tmp_path / "schemas", tmp_path / "openapi.json"
    assert cli("--output", schemas, "--openapi", openapi).returncode == 0
    marker = schemas / "README.md"
    marker.write_text("Preserve this non-generated file.")
    target = schemas / "RunView.schema.json"
    if drift == "missing":
        target.unlink()
    elif drift == "modified":
        target.write_text("{}\n")
    elif drift == "unexpected":
        (schemas / "Stale.schema.json").write_text("{}\n")
    else:
        openapi.write_text("{}\n")
    before = snapshot(tmp_path)
    result = cli("--check", schemas, "--openapi", openapi)
    assert result.returncode != 0
    assert "drift" in result.stderr.lower()
    assert snapshot(tmp_path) == before
    assert cli("--output", schemas, "--openapi", openapi).returncode == 0
    assert cli("--check", schemas, "--openapi", openapi).returncode == 0
    assert marker.read_text() == "Preserve this non-generated file."


def test_check_does_not_create_absent_directory_or_openapi(tmp_path):
    result = cli("--check", tmp_path / "absent", "--openapi", tmp_path / "absent.json")
    assert result.returncode != 0
    assert snapshot(tmp_path) == {}


def test_committed_schemas_and_openapi_match_builders():
    contracts = BACKEND.parent / "contracts"
    result = cli(
        "--check", contracts / "jsonschema", "--openapi", contracts / "openapi.json"
    )
    assert result.returncode == 0, result.stderr
