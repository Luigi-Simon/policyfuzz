"""Generate or check deterministic v2 schemas and synthetic fixtures."""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path
from typing import Any, Sequence

from .contracts import (
    AgentRole,
    PolicyInput,
    SandboxRequest,
    SandboxResult,
    make_example_request,
    public_sandbox_result,
)
from .fixtures import FixtureSandboxService

DEFAULT_OUTPUT = Path(__file__).resolve().parents[3] / "contracts" / "v2"


def _json_bytes(value: Any) -> bytes:
    text = json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True)
    return f"{text}\n".encode()


async def _rendered_contracts() -> dict[str, bytes]:
    request = make_example_request()
    completed = await FixtureSandboxService().run(request)
    partial = await FixtureSandboxService("partial_translation_unavailable").run(
        request
    )
    return {
        "policy-input.schema.json": _json_bytes(PolicyInput.model_json_schema()),
        "sandbox-request.schema.json": _json_bytes(SandboxRequest.model_json_schema()),
        "sandbox-result.schema.json": _json_bytes(SandboxResult.model_json_schema()),
        "roles.json": _json_bytes(
            {
                "roles": [role.value for role in AgentRole],
                "schema_version": "2.0",
            }
        ),
        "fixtures/example-request.json": _json_bytes(request.model_dump(mode="json")),
        "fixtures/completed-result.json": _json_bytes(
            completed.model_dump(mode="json")
        ),
        "fixtures/completed-public-result.json": _json_bytes(
            public_sandbox_result(completed)
        ),
        "fixtures/partial-translation-unavailable-result.json": _json_bytes(
            partial.model_dump(mode="json")
        ),
        "fixtures/partial-translation-unavailable-public-result.json": _json_bytes(
            public_sandbox_result(partial)
        ),
    }


def _check(output: Path, rendered: dict[str, bytes]) -> int:
    expected_paths = {output / relative for relative in rendered}
    current_paths = {path for path in output.rglob("*") if path.is_file()}
    drifted = [
        relative
        for relative, content in rendered.items()
        if not (output / relative).is_file()
        or (output / relative).read_bytes() != content
    ]
    unexpected = sorted(
        str(path.relative_to(output)) for path in current_paths - expected_paths
    )
    if drifted or unexpected:
        for relative in sorted(drifted):
            print(f"contract drift: {relative}", file=sys.stderr)
        for relative in unexpected:
            print(f"unexpected contract: {relative}", file=sys.stderr)
        return 1
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args(argv)
    rendered = asyncio.run(_rendered_contracts())
    if args.check:
        return _check(args.output, rendered)
    for relative, content in rendered.items():
        path = args.output / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
