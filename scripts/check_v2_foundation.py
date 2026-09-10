"""Verify the v2 Sandbox boundary offline; no providers or secrets are used."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
import subprocess
import sys
import unittest


ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "backend"


async def smoke() -> None:
    from app.v2.contracts import (
        make_example_request,
        public_sandbox_result,
        validate_sandbox_result,
    )
    from app.v2.fixtures import FixtureSandboxService

    request = make_example_request()
    result = await FixtureSandboxService().run(request)
    validate_sandbox_result(request, result)
    public = public_sandbox_result(result)
    if result.execution_mode != "fixture":
        raise RuntimeError("The offline smoke must use fixture mode.")
    if "original_records" in public:
        raise RuntimeError("Internal original records reached the public result.")
    print(
        json.dumps(
            {
                "check": "v2 Sandbox boundary",
                "execution_mode": result.execution_mode,
                "status": result.status,
                "messages": len(result.messages),
                "live_provider_calls": 0,
            },
            indent=2,
        ),
        flush=True,
    )


def main() -> int:
    sys.path.insert(0, str(BACKEND))
    suite = unittest.defaultTestLoader.discover(
        str(BACKEND / "tests" / "v2"), pattern="test_*.py"
    )
    if not suite.countTestCases():
        print("No v2 tests discovered; foundation verification cannot pass.")
        return 1
    tests = unittest.TextTestRunner(verbosity=2).run(suite)
    if not tests.wasSuccessful():
        return 1
    generated = subprocess.run(
        [sys.executable, "-m", "app.v2.export_contracts", "--check"],
        cwd=BACKEND,
        check=False,
    )
    if generated.returncode:
        return generated.returncode
    asyncio.run(smoke())
    print("V2 foundation checks passed (synthetic fixtures only).", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
