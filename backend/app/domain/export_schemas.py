"""Deterministic domain schema exports; no runtime API or feature imports."""

import argparse
import json
import sys
from pathlib import Path

from pydantic import BaseModel

from app.domain import models


def stable_json(value: object) -> str:
    """The byte format shared by generated contracts: sorted UTF-8 JSON + LF."""
    return json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n"


def build_schemas() -> dict[str, dict]:
    """Build one self-contained schema per concrete, publicly exported model."""
    return {
        f"{name}.schema.json": model.model_json_schema()
        for name in sorted(models.__all__)
        if isinstance(model := getattr(models, name), type)
        and issubclass(model, BaseModel)
        and model is not models.StrictModel
    }


# method, path, operation ID, request model, success status, response model, errors
_ENDPOINTS = (
    (
        "post",
        "/api/v1/runs",
        "create_run",
        models.CreateRunRequest,
        "202",
        models.CreateRunResponse,
        ("422", "500", "502", "503"),
    ),
    (
        "get",
        "/api/v1/runs/{run_id}",
        "get_run",
        None,
        "200",
        models.RunView,
        ("404", "422", "500"),
    ),
    (
        "post",
        "/api/v1/runs/{run_id}/confirm-contract",
        "confirm_contract",
        models.ConfirmContractRequest,
        "200",
        models.RunView,
        ("404", "409", "422", "500", "502", "503"),
    ),
    (
        "post",
        "/api/v1/runs/{run_id}/select-findings",
        "select_findings",
        models.SelectFindingsRequest,
        "200",
        models.RunView,
        ("404", "409", "422", "500", "502", "503"),
    ),
    (
        "post",
        "/api/v1/runs/{run_id}/confirm-revision",
        "confirm_revision",
        models.ConfirmRevisionRequest,
        "200",
        models.RunView,
        ("404", "409", "422", "500", "502", "503"),
    ),
    (
        "delete",
        "/api/v1/runs/{run_id}",
        "delete_run",
        None,
        "200",
        models.DeleteRunResponse,
        ("404", "422", "500"),
    ),
    (
        "get",
        "/api/v1/health",
        "health",
        None,
        "200",
        models.HealthResponse,
        ("500", "503"),
    ),
)


def build_openapi() -> dict:
    """Build the seven-operation OpenAPI 3.1 registry from endpoint models only."""
    components: dict[str, dict] = {}

    def model_ref(model: type[BaseModel]) -> dict:
        schema = model.model_json_schema(ref_template="#/components/schemas/{model}")
        components.update(schema.pop("$defs", {}))
        components[model.__name__] = schema
        return {"$ref": f"#/components/schemas/{model.__name__}"}

    error_schema = {
        "type": "object",
        "required": ["error"],
        "additionalProperties": False,
        "properties": {"error": model_ref(models.PublicError)},
    }
    paths: dict[str, dict] = {}
    for method, path, operation_id, request, status, response, errors in _ENDPOINTS:
        operation: dict = {
            "operationId": operation_id,
            "responses": {
                status: {
                    "description": "Accepted" if status == "202" else "Success",
                    "content": {"application/json": {"schema": model_ref(response)}},
                },
                **{
                    code: {
                        "description": "Structured public application error",
                        "content": {"application/json": {"schema": error_schema}},
                    }
                    for code in errors
                },
            },
        }
        if request is not None:
            operation["requestBody"] = {
                "required": True,
                "content": {"application/json": {"schema": model_ref(request)}},
            }
        if "{run_id}" in path:
            operation["parameters"] = [
                {
                    "name": "run_id",
                    "in": "path",
                    "required": True,
                    "schema": {"type": "string"},
                }
            ]
        paths.setdefault(path, {})[method] = operation
    return {
        "openapi": "3.1.0",
        "info": {"title": "PolicyFuzz API", "version": "1.0"},
        "paths": paths,
        "components": {"schemas": components},
    }


def check_file(path: Path, expected: str) -> bool:
    """Compare exact bytes, treating absent files as drift without creating them."""
    return path.is_file() and path.read_bytes() == expected.encode("utf-8")


def write_file(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content.encode("utf-8"))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--output", type=Path, help="Regenerate individual JSON schemas")
    mode.add_argument(
        "--check", type=Path, help="Check schemas (and --openapi) without writing"
    )
    parser.add_argument("--openapi", type=Path, help="OpenAPI registry path")
    args = parser.parse_args(argv)
    if not (args.output or args.check or args.openapi):
        parser.error("provide --output, --check, or --openapi")
    schemas = {name: stable_json(value) for name, value in build_schemas().items()}
    openapi = stable_json(build_openapi()) if args.openapi else None
    if args.check:
        present = {path.name for path in args.check.glob("*.schema.json")}
        drift = sorted(present ^ schemas.keys())
        drift.extend(
            name
            for name, expected in schemas.items()
            if name in present and not check_file(args.check / name, expected)
        )
        if args.openapi and not check_file(args.openapi, openapi):
            drift.append(str(args.openapi))
        if drift:
            print("Contract drift: " + ", ".join(drift), file=sys.stderr)
            return 1
        return 0
    if args.output:
        args.output.mkdir(parents=True, exist_ok=True)
        for stale in args.output.glob("*.schema.json"):
            if stale.name not in schemas:
                stale.unlink()
        for name, content in schemas.items():
            write_file(args.output / name, content)
    if args.openapi:
        write_file(args.openapi, openapi)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
