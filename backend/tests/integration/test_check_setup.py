"""Offline setup diagnostics stay bounded and avoid provider calls."""

from __future__ import annotations

import importlib.util
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[3]


def load_checker():
    path = ROOT / "scripts/check_setup.py"
    spec = importlib.util.spec_from_file_location("check_setup", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def ready_tree(tmp_path: Path) -> None:
    (tmp_path / "frontend/node_modules").mkdir(parents=True, exist_ok=True)
    (tmp_path / "frontend/package.json").write_text("{}", encoding="utf-8")
    cache = tmp_path / "samples/cached-demo"
    cache.mkdir(parents=True, exist_ok=True)
    for name in ("run-record.json", "model-responses.json", "summary.json"):
        (cache / name).write_text("{}", encoding="utf-8")
    policies = tmp_path / "samples/policies"
    policies.mkdir(parents=True, exist_ok=True)
    (policies / "development-policy.txt").write_text("synthetic", encoding="utf-8")


def environment(checker, tmp_path, *, settings_factory=None, run=None, **overrides):
    ready_tree(tmp_path)

    def default_run(command, **kwargs):
        version = "v20.11.0" if Path(command[0]).name == "node" else "10.2.0"
        return subprocess.CompletedProcess(command, 0, version, "")

    values = {
        "root": tmp_path,
        "python_version": (3, 12, 1),
        "which": lambda name: f"/tools/{name}",
        "run": run or default_run,
        "find_spec": lambda name: object(),
        "environ": {},
        "settings_factory": settings_factory
        or (lambda **kwargs: SimpleNamespace(**kwargs)),
    }
    values.update(overrides)
    return checker.CheckEnvironment(**values)


def test_cached_and_mock_are_ready_without_credentials(tmp_path, capsys):
    checker = load_checker()
    env = environment(checker, tmp_path)

    assert checker.main(["--mode", "cached"], env=env) == 0
    assert checker.main(["--mode", "mock"], env=env) == 0

    output = capsys.readouterr().out
    assert "offline configuration only" in output.lower()
    assert "provider" in output.lower() and "browser" in output.lower()
    assert ".env" in output and "not loaded" in output.lower()


def test_mock_skips_all_backend_specific_checks(tmp_path, capsys):
    checker = load_checker()

    def backend_settings_must_not_load(**kwargs):
        raise AssertionError(f"unexpected Settings load: {kwargs}")

    env = environment(
        checker,
        tmp_path,
        python_version=(3, 8),
        find_spec=lambda name: None,
        settings_factory=backend_settings_must_not_load,
        environ={"APP_MODE": "broken", "RUN_TTL_SECONDS": "invalid"},
    )
    assert checker.main(["--mode", "mock"], env=env) == 0
    assert "backend" not in capsys.readouterr().out.lower()


def test_cached_cli_without_site_packages_reports_dependencies_not_traceback():
    result = subprocess.run(
        [
            sys.executable,
            "-S",
            str(ROOT / "scripts/check_setup.py"),
            "--mode",
            "cached",
        ],
        capture_output=True,
        text=True,
        timeout=10,
        check=False,
    )

    assert result.returncode == 1
    assert "install backend dependencies" in result.stdout.lower()
    assert "traceback" not in result.stdout.lower()
    assert "traceback" not in result.stderr.lower()


def test_live_requires_nonblank_key_and_model(tmp_path, capsys):
    checker = load_checker()
    for values in (
        {},
        {"OPENAI_API_KEY": "   ", "LLM_MODEL": "model"},
        {"OPENAI_API_KEY": "key", "LLM_MODEL": "   "},
    ):
        env = environment(checker, tmp_path, environ=values)
        assert checker.main(["--mode", "live"], env=env) == 1

    output = capsys.readouterr().out.lower()
    assert "openai_api_key" in output
    assert "llm_model" in output


def test_secret_is_redacted_when_settings_validation_fails(tmp_path, capsys):
    checker = load_checker()
    sentinel = "sentinel-super-secret-value"

    def invalid_settings(**kwargs):
        raise ValueError(f"bad configuration contained {sentinel}: {kwargs!r}")

    env = environment(
        checker,
        tmp_path,
        settings_factory=invalid_settings,
        environ={"OPENAI_API_KEY": sentinel, "LLM_MODEL": "synthetic-model"},
    )
    assert checker.main(["--mode", "live"], env=env) == 1

    captured = capsys.readouterr()
    assert sentinel not in captured.out
    assert sentinel not in captured.err
    assert "settings" in captured.out.lower()


def test_requested_mode_overrides_app_mode_without_mutating_environment(tmp_path):
    checker = load_checker()
    supplied = []
    process_environment = {"APP_MODE": "live"}

    def settings_factory(**kwargs):
        supplied.append(kwargs)
        return SimpleNamespace(**kwargs)

    env = environment(
        checker,
        tmp_path,
        settings_factory=settings_factory,
        environ=process_environment,
    )
    assert checker.main(["--mode", "cached"], env=env) == 0
    assert supplied == [{"app_mode": "cached"}]
    assert process_environment == {"APP_MODE": "live"}


def test_missing_or_old_node_and_timeout_are_actionable(tmp_path, capsys):
    checker = load_checker()
    missing = environment(
        checker, tmp_path, which=lambda name: None if name == "node" else "/tools/npm"
    )
    assert checker.main(["--mode", "mock"], env=missing) == 1
    assert "install node.js 20" in capsys.readouterr().out.lower()

    def old_node(command, **kwargs):
        return subprocess.CompletedProcess(command, 0, "v18.20.0", "")

    assert (
        checker.main(
            ["--mode", "mock"], env=environment(checker, tmp_path, run=old_node)
        )
        == 1
    )
    assert "node.js 20" in capsys.readouterr().out.lower()

    def timeout(command, **kwargs):
        raise subprocess.TimeoutExpired(command, kwargs["timeout"])

    assert (
        checker.main(
            ["--mode", "mock"], env=environment(checker, tmp_path, run=timeout)
        )
        == 1
    )
    assert "timed out" in capsys.readouterr().out.lower()


def test_windows_npm_cmd_is_invoked_directly_without_shell(tmp_path):
    checker = load_checker()
    commands = []

    def windows_tools(name):
        return r"C:\Program Files\nodejs\npm.cmd" if name == "npm" else "node.exe"

    def record_run(command, **kwargs):
        commands.append((command, kwargs))
        version = "10.2.0" if command[0].endswith("npm.cmd") else "v20.11.0"
        return subprocess.CompletedProcess(command, 0, version, "")

    env = environment(checker, tmp_path, which=windows_tools, run=record_run)
    assert checker.main(["--mode", "mock"], env=env) == 0
    npm_call = next(call for call in commands if call[0][0].endswith("npm.cmd"))
    assert npm_call[0] == [r"C:\Program Files\nodejs\npm.cmd", "--version"]
    assert npm_call[1]["shell"] is False


def test_missing_backend_package_and_invalid_settings_block(tmp_path, capsys):
    checker = load_checker()
    missing = environment(
        checker,
        tmp_path,
        find_spec=lambda name: None if name == "fastapi" else object(),
    )
    assert checker.main(["--mode", "cached"], env=missing) == 1
    assert "backend dependencies" in capsys.readouterr().out.lower()

    def invalid_settings(**kwargs):
        raise ValueError("RUN_TTL_SECONDS is invalid")

    invalid = environment(checker, tmp_path, settings_factory=invalid_settings)
    assert checker.main(["--mode", "cached"], env=invalid) == 1
    output = capsys.readouterr().out.lower()
    assert "settings" in output and "configuration" in output


def test_missing_frontend_and_cached_files_block_with_remediation(tmp_path, capsys):
    checker = load_checker()
    env = environment(checker, tmp_path)
    (tmp_path / "frontend/package.json").unlink()
    (tmp_path / "samples/policies/development-policy.txt").unlink()

    assert checker.main(["--mode", "cached"], env=env) == 1
    output = capsys.readouterr().out.lower()
    assert "frontend" in output and "repository" in output
    assert "development policy" in output
    assert "npm ci" in output
