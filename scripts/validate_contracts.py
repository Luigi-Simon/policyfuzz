#!/usr/bin/env python3
"""Regenerate contracts in temporary storage and detect exact committed drift."""

from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT / "backend") not in sys.path:
    sys.path.insert(0, str(ROOT / "backend"))

from app.domain import contract_fixtures, export_schemas
from app.domain.models import RunRecord, RunView


class ContractDriftError(ValueError):
    """Committed contracts or fixtures differ from authoritative models."""


def validate_contracts(root: Path = ROOT) -> int:
    with tempfile.TemporaryDirectory(prefix="policyfuzz-contracts-") as name:
        generated = Path(name)
        export_schemas.main(
            [
                "--output",
                str(generated / "jsonschema"),
                "--openapi",
                str(generated / "openapi.json"),
            ]
        )
        contract_fixtures.main(
            ["--output", str(generated / "fixtures/run-view.completed.json")]
        )
        expected = {
            p.relative_to(generated): p.read_bytes() for p in generated.rglob("*.json")
        }
        actual_schema_names = {
            p.name for p in (root / "contracts/jsonschema").glob("*.schema.json")
        }
        expected_schema_names = {
            p.name for p in (generated / "jsonschema").glob("*.schema.json")
        }
        if actual_schema_names != expected_schema_names:
            raise ContractDriftError("Schema registry membership differs.")
        for relative, content in expected.items():
            destination = root / "contracts" / relative
            if (
                not destination.is_file()
                or destination.is_symlink()
                or destination.read_bytes() != content
            ):
                raise ContractDriftError("Generated contract or fixture differs.")
        RunView.model_validate_json(
            (root / "contracts/fixtures/run-view.completed.json").read_bytes()
        )
        cached = root / "samples/cached-demo/run-record.json"
        if cached.is_file():
            RunRecord.model_validate_json(cached.read_bytes())
        return len(expected_schema_names)


def main() -> int:
    try:
        count = validate_contracts()
    except (OSError, ValueError):
        print("Contract or fixture validation failed.", file=sys.stderr)
        return 1
    print(json.dumps({"status": "passed", "schemas": count}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
