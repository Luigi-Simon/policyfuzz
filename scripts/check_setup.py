#!/usr/bin/env python3
"""Run bounded, offline checks before starting PolicyFuzz."""

from __future__ import annotations

import argparse
import asyncio
import importlib.util
import os
import re
import shutil
import subprocess
import sys
from collections.abc import Callable, Mapping, Sequence
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
BACKEND_PACKAGES = ("fastapi", "pydantic", "pydantic_settings", "uvicorn", "openai")
CACHED_FILES = (
    "samples/cached-demo/run-record.json",
    "samples/cached-demo/model-responses.json",
    "samples/cached-demo/summary.json",
)
DEVELOPMENT_POLICY = "samples/policies/development-policy.txt"
COMMAND_TIMEOUT_SECONDS = 5


class CheckEnvironment:
    """Injectable local probes used to keep diagnostics deterministic in tests."""

    def __init__(
        self,
        *,
        root: Path,
        python_version: tuple[int, ...],
        which: Callable[[str], str | None],
        run: Callable[..., subprocess.CompletedProcess[str]],
        find_spec: Callable[[str], object | None],
        environ: Mapping[str, str],
        settings_factory: Callable[..., Any],
        provider_probe: Callable[[], None],
        cached_probe: Callable[[Path], None],
    ) -> None:
        self.root = root
        self.python_version = python_version
        self.which = which
        self.run = run
        self.find_spec = find_spec
        self.environ = environ
        self.settings_factory = settings_factory
        self.provider_probe = provider_probe
        self.cached_probe = cached_probe


def _probe_cached_record(path: Path) -> None:
    """Apply the same read-only evidence validation used by cached run creation."""
    from app.domain.models import RunRecord
    from app.workflow.validation import validate_cached_record

    validate_cached_record(RunRecord.model_validate_json(path.read_bytes()))


def _probe_provider_runtime() -> None:
    """Construct and close the SDK transport without a request or real credential."""
    import openai

    async def probe() -> None:
        client = openai.AsyncOpenAI(
            api_key="policyfuzz-offline-probe", max_retries=0, timeout=1.0
        )
        await client.close()

    asyncio.run(probe())


def _default_environment() -> CheckEnvironment:
    def load_settings(**kwargs: Any) -> Any:
        backend = ROOT / "backend"
        if str(backend) not in sys.path:
            sys.path.insert(0, str(backend))
        from app.core.config import Settings

        return Settings(**kwargs)

    return CheckEnvironment(
        root=ROOT,
        python_version=tuple(sys.version_info[:3]),
        which=shutil.which,
        run=subprocess.run,
        find_spec=importlib.util.find_spec,
        environ=os.environ,
        settings_factory=load_settings,
        provider_probe=_probe_provider_runtime,
        cached_probe=_probe_cached_record,
    )


def _status(ok: bool, message: str) -> str:
    return f"[{'OK' if ok else 'ERROR'}] {message}"


def _command_version(env: CheckEnvironment, name: str) -> tuple[bool, str | None, str]:
    executable = env.which(name)
    if executable is None:
        return False, None, f"{name} is not on PATH"
    try:
        result = env.run(
            [executable, "--version"],
            capture_output=True,
            text=True,
            timeout=COMMAND_TIMEOUT_SECONDS,
            check=False,
            shell=False,
        )
    except subprocess.TimeoutExpired:
        return False, None, f"{name} version check timed out"
    except OSError:
        return False, None, f"{name} could not be executed"
    if result.returncode != 0:
        return False, None, f"{name} version check failed"
    return True, result.stdout.strip(), f"{name} is available"


def run_checks(mode: str, env: CheckEnvironment) -> tuple[int, list[str]]:
    """Return an exit status and safe human-readable diagnostic lines."""
    lines = [f"PolicyFuzz setup check (mode: {mode})"]
    failures = 0
    backend_ready = False

    backend_mode = mode in ("cached", "live")
    if backend_mode:
        python_ok = env.python_version >= (3, 12)
        failures += not python_ok
        lines.append(
            _status(
                python_ok,
                "Python 3.12+ is available"
                if python_ok
                else "Python 3.12+ is required; recreate the backend virtual environment",
            )
        )

    node_ok, node_version, node_message = _command_version(env, "node")
    if node_ok:
        match = re.fullmatch(r"v?(\d+)(?:\.\d+){0,2}", node_version or "")
        node_ok = bool(match and int(match.group(1)) >= 20)
        node_message = (
            "Node.js 20+ is available"
            if node_ok
            else "Install Node.js 20 or newer and place it on PATH"
        )
    elif "timed out" not in node_message:
        node_message = "Install Node.js 20 or newer and place it on PATH"
    failures += not node_ok
    lines.append(_status(node_ok, node_message))

    npm_ok, _, npm_message = _command_version(env, "npm")
    if not npm_ok and "timed out" not in npm_message:
        npm_message = "Install npm and place it on PATH"
    failures += not npm_ok
    lines.append(_status(npm_ok, npm_message))

    package_ok = (env.root / "frontend/package.json").is_file()
    modules_ok = (env.root / "frontend/node_modules").is_dir()
    frontend_ok = package_ok and modules_ok
    failures += not frontend_ok
    lines.append(
        _status(
            frontend_ok,
            "Frontend package and installed modules are present"
            if frontend_ok
            else "Restore the frontend package from the repository and run npm ci in frontend",
        )
    )

    if backend_mode:
        missing_packages = [
            name for name in BACKEND_PACKAGES if env.find_spec(name) is None
        ]
        packages_ok = not missing_packages
        failures += not packages_ok
        lines.append(
            _status(
                packages_ok,
                "Backend runtime dependencies are importable"
                if packages_ok
                else "Install backend dependencies with the backend virtual environment",
            )
        )

        if packages_ok:
            try:
                env.settings_factory(app_mode=mode)
            except Exception:  # noqa: BLE001 - never print validation details or secrets
                failures += 1
                lines.append(
                    _status(
                        False,
                        "Backend Settings configuration is invalid; review documented environment values",
                    )
                )
            else:
                backend_ready = True
                lines.append(
                    _status(
                        True, f"Backend Settings validate for requested {mode} mode"
                    )
                )
                if mode == "live":
                    try:
                        env.provider_probe()
                    except Exception:  # noqa: BLE001 - proxy errors may contain secrets
                        failures += 1
                        lines.append(
                            _status(
                                False,
                                "OpenAI client could not initialize locally; check backend "
                                "dependencies and proxy settings. A SOCKS proxy requires "
                                "socksio in the backend virtual environment",
                            )
                        )
                    else:
                        lines.append(
                            _status(
                                True,
                                "OpenAI client initialized and closed with a dummy key; "
                                "no API request was made",
                            )
                        )

    if mode == "cached":
        cache_ok = all((env.root / relative).is_file() for relative in CACHED_FILES)
        failures += not cache_ok
        lines.append(
            _status(
                cache_ok,
                "Bundled cached demo files are present"
                if cache_ok
                else "Restore the bundled cached demo files from the repository",
            )
        )
        if cache_ok and backend_ready:
            try:
                env.cached_probe(env.root / "samples/cached-demo/run-record.json")
            except Exception:  # noqa: BLE001 - never expose malformed artifact contents
                failures += 1
                lines.append(
                    _status(
                        False,
                        "Cached demo record is invalid; restore the bundled cache from "
                        "the same repository version and run scripts/replay_check.py",
                    )
                )
            else:
                lines.append(
                    _status(True, "Cached demo record and evidence links validate")
                )
        policy_ok = (env.root / DEVELOPMENT_POLICY).is_file()
        failures += not policy_ok
        lines.append(
            _status(
                policy_ok,
                "Bundled development policy is present"
                if policy_ok
                else "Restore the bundled development policy from the repository",
            )
        )

    if mode == "live":
        key_ok = bool(env.environ.get("OPENAI_API_KEY", "").strip())
        model_ok = bool(env.environ.get("LLM_MODEL", "").strip())
        failures += not key_ok
        failures += not model_ok
        lines.append(
            _status(
                key_ok,
                "OPENAI_API_KEY is set"
                if key_ok
                else "Set OPENAI_API_KEY for live mode",
            )
        )
        lines.append(
            _status(
                model_ok,
                "LLM_MODEL is set" if model_ok else "Set LLM_MODEL for live mode",
            )
        )

    lines.append("Note: .env files are not loaded by existing configuration.")
    if failures:
        lines.append(f"Summary: not ready ({failures} blocking check(s)).")
        return 1, lines
    lines.append(
        "Summary: ready for offline configuration only; provider identity, model version, "
        "account availability, and browser behavior were not verified."
    )
    return 0, lines


def main(
    argv: Sequence[str] | None = None, *, env: CheckEnvironment | None = None
) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mode", choices=("mock", "cached", "live"), default="cached")
    args = parser.parse_args(argv)
    status, lines = run_checks(args.mode, env or _default_environment())
    print("\n".join(lines))
    return status


if __name__ == "__main__":
    raise SystemExit(main())
