"""Generate or check deterministic public contracts for the v2 API."""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Sequence
from pathlib import Path
from typing import Any

from .main import app
from .metric_contracts import MetricReview, MetricRunResult
from .run_models import PublicSandboxResult

DEFAULT_OUTPUT = Path(__file__).resolve().parents[3] / "contracts" / "v2-app"


def _json_bytes(value: Any) -> bytes:
    rendered = json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True)
    return f"{rendered}\n".encode()


def _rendered_contracts() -> dict[str, bytes]:
    return {
        "openapi.json": _json_bytes(app.openapi()),
        "public-sandbox-result.schema.json": _json_bytes(
            PublicSandboxResult.model_json_schema()
        ),
        "metric-review.schema.json": _json_bytes(MetricReview.model_json_schema()),
        "metric-run-result.schema.json": _json_bytes(
            MetricRunResult.model_json_schema()
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
    rendered = _rendered_contracts()
    if args.check:
        return _check(args.output, rendered)
    for relative, content in rendered.items():
        path = args.output / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
