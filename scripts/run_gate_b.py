#!/usr/bin/env python3
"""Execute the fixed offline release gate and exclusively save its evidence."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
import tempfile
from collections.abc import Callable, Sequence
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


class GateError(ValueError):
    """A fixed, public-safe gate failure."""


def commands() -> tuple[tuple[str, ...], ...]:
    python = sys.executable
    return (
        (python, "-m", "ruff", "check", "backend/app", "backend/tests"),
        (python, "-m", "ruff", "format", "--check", "backend/app", "backend/tests"),
        (python, "-m", "pytest", "backend/tests", "-q"),
        (python, "scripts/validate_contracts.py"),
        (python, "scripts/replay_check.py"),
        (python, "scripts/offline_smoke.py"),
        (python, "scripts/verify_benchmarks.py", "--include-blind"),
        ("npm", "--prefix", "frontend", "run", "check:generated"),
        ("npm", "--prefix", "frontend", "run", "typecheck"),
        ("npm", "--prefix", "frontend", "run", "test:run"),
        ("npm", "--prefix", "frontend", "run", "build"),
    )


def _run(command: Sequence[str], cwd: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        command, cwd=cwd, capture_output=True, text=True, timeout=900, check=False
    )


def _snapshot(root: Path) -> tuple[str, str]:
    def git(*args: str) -> str:
        return subprocess.check_output(
            ("git", *args), cwd=root, text=True, stderr=subprocess.DEVNULL
        ).strip()

    return git("rev-parse", "HEAD"), git("status", "--porcelain")


def _digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _approval_path(root: Path, active: dict) -> Path:
    evidence = active.get("approval_evidence")
    if not isinstance(evidence, dict) or not isinstance(evidence.get("path"), str):
        raise GateError("Hash-bound human benchmark approval is missing.")
    path = root / evidence["path"]
    if (
        not path.resolve().is_relative_to(root.resolve())
        or any(item.is_symlink() for item in (path, *path.parents))
        or not path.is_file()
        or _digest(path) != evidence.get("sha256")
    ):
        raise GateError("Human benchmark approval evidence is invalid.")
    approval = json.loads(path.read_text())
    if (
        approval.get("reviewer_type") != "human"
        or approval.get("decision") != "approve"
        or not isinstance(approval.get("reviewer_id"), str)
        or not approval["reviewer_id"].strip()
        or type(active.get("candidate_version")) is not int
        or active["candidate_version"] < 1
        or any(
            not isinstance(active.get(key), str)
            or re.fullmatch("[0-9a-f]{64}", active[key]) is None
            for key in ("source_policy_sha256", "schema_archive_sha256")
        )
        or any(
            approval.get(key) != active[key]
            for key in (
                "candidate_version",
                "source_policy_sha256",
                "schema_archive_sha256",
            )
        )
    ):
        raise GateError("Human benchmark approval does not match the active candidate.")
    try:
        timestamp = datetime.fromisoformat(approval["timestamp"].replace("Z", "+00:00"))
        if timestamp.utcoffset() is None:
            raise ValueError
    except (KeyError, TypeError, ValueError, AttributeError):
        raise GateError("Human benchmark approval timestamp is invalid.") from None
    return path


def _evidence(root: Path) -> dict[str, str]:
    active_path = root / "submission/evidence/active-benchmark.json"
    if not active_path.is_file() or active_path.is_symlink():
        raise GateError("Independent human benchmark approval is pending.")
    active = json.loads(active_path.read_text())
    if (
        active.get("headline_gold_scoring_eligible") is not True
        or active.get("human_review") != "approved"
    ):
        raise GateError("Independent human benchmark approval is pending.")
    paths = [
        active_path.relative_to(root).as_posix(),
        _approval_path(root, active).relative_to(root).as_posix(),
    ]
    for name in ("development", "corrected-control", "blind"):
        paths.extend(
            (
                f"team/person-4-evaluation/evidence/{name}-score.json",
                f"samples/benchmarks/{name}/defect-manifest.json",
            )
        )
    paths.extend(
        (
            "team/person-1-integration/evidence/blind-first-run.json",
            "team/person-1-integration/evidence/blind-first-run.json.metadata.json",
            "team/person-1-integration/evidence/manual-review.json",
            "team/person-4-evaluation/evidence/manual-review.json",
        )
    )
    if any(not (root / p).is_file() or (root / p).is_symlink() for p in paths):
        raise GateError("Required benchmark or manual-review evidence is missing.")
    scores = {
        name: json.loads(
            (root / f"team/person-4-evaluation/evidence/{name}-score.json").read_text()
        )
        for name in ("development", "corrected-control", "blind")
    }
    for score in scores.values():
        if any(
            type(score.get(k)) is not int or score[k] < 0
            for k in ("true_positives", "false_positives", "false_negatives")
        ):
            raise GateError("Benchmark score counts are invalid.")
    if tuple(
        scores["development"][k]
        for k in ("true_positives", "false_positives", "false_negatives")
    ) != (3, 0, 0):
        raise GateError("Development benchmark acceptance failed.")
    if any(
        scores["corrected-control"][k]
        for k in ("true_positives", "false_positives", "false_negatives")
    ):
        raise GateError("Corrected control still reports scored defects.")
    blind = scores["blind"]
    tp, fp, fn = (
        blind[k] for k in ("true_positives", "false_positives", "false_negatives")
    )
    if tp + fn != 3 or 3 * tp < 2 * (tp + fn) or not tp + fp or 3 * tp < 2 * (tp + fp):
        raise GateError("Blind first-run acceptance failed.")
    from scripts.manual_review import ManualReviewError, validate_manual_reviews

    try:
        paths.extend(validate_manual_reviews(root, active))
    except ManualReviewError:
        raise GateError(
            "Independent measured manual-review evidence is incomplete."
        ) from None
    audit = json.loads(
        (
            root
            / "team/person-1-integration/evidence/blind-first-run.json.metadata.json"
        ).read_bytes()
    )
    # The fixed verifier proves this audit and its six input commitments. Include
    # every committed input/member in before/after snapshots as well as the score.
    committed_inputs = audit.get("input_bytes_sha256", {})
    if isinstance(committed_inputs, dict):
        paths.extend(committed_inputs)
    for name in ("development", "corrected-control", "blind"):
        directory = root / "samples/benchmarks" / name
        paths.extend(
            path.relative_to(root).as_posix() for path in directory.glob("*.json")
        )
    if any(
        not isinstance(p, str)
        or not (root / p).resolve().is_relative_to(root.resolve())
        or not (root / p).is_file()
        or any(item.is_symlink() for item in (root / p, *(root / p).parents))
        for p in paths
    ):
        raise GateError("Evidence snapshots require owned regular files.")
    return {p: _digest(root / p) for p in paths}


def atomic_json(output: Path, payload: object) -> None:
    """Hard-link a complete temporary file, refusing any existing destination."""
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w", encoding="utf-8", dir=output.parent, delete=False
        ) as stream:
            temporary = Path(stream.name)
            json.dump(payload, stream, indent=2, sort_keys=True, ensure_ascii=False)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.link(temporary, output)
    except FileExistsError:
        raise GateError(
            "Output already exists; evidence cannot be overwritten."
        ) from None
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def run_gate(
    root: Path,
    output: Path,
    *,
    runner: Callable[[Sequence[str], Path], subprocess.CompletedProcess[str]] = _run,
    snapshot: Callable[[], tuple[str, str]] | None = None,
    now: Callable[[], datetime] = lambda: datetime.now(UTC),
) -> dict[str, object]:
    if output.exists() or output.is_symlink():
        raise GateError("Output already exists; evidence cannot be overwritten.")
    snapshot = snapshot or (lambda: _snapshot(root))
    commit, dirty = snapshot()
    if dirty or re.fullmatch("[0-9a-f]{40}", commit) is None:
        raise GateError("Gate B requires a clean committed worktree.")
    artifact_hashes = _evidence(root)
    started = now().isoformat()
    results: list[dict[str, object]] = []
    for command in commands():
        command_started = now().isoformat()
        result = runner(command, root)
        results.append(
            {
                "command": list(command),
                "started_at": command_started,
                "completed_at": now().isoformat(),
                "exit_code": result.returncode,
                "stdout": (result.stdout or "")[-8192:],
                "stderr": (result.stderr or "")[-8192:],
            }
        )
        if result.returncode:
            raise GateError(
                "A required verification command failed; no success report was written."
            )
    if snapshot() != (commit, "") or artifact_hashes != _evidence(root):
        raise GateError(
            "The worktree or benchmark evidence changed during verification."
        )
    versions = {}
    for name, command in (
        ("python", (sys.executable, "--version")),
        ("node", ("node", "--version")),
        ("npm", ("npm", "--version")),
    ):
        result = runner(command, root)
        if result.returncode:
            raise GateError("Unable to record tool versions.")
        versions[name] = (result.stdout or result.stderr or "").strip()[:256]
    report: dict[str, object] = {
        "schema_version": "1.0",
        "status": "passed",
        "commit": commit,
        "application_commit": commit,
        "worktree": {"clean_before": True, "clean_after": True},
        "started_at": started,
        "completed_at": now().isoformat(),
        "commands": results,
        "tool_versions": versions,
        "artifact_hashes": artifact_hashes,
    }
    if snapshot() != (commit, ""):
        raise GateError("The worktree changed before evidence publication.")
    atomic_json(output, report)
    return report


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        report = run_gate(ROOT, args.output.resolve())
    except (GateError, OSError, ValueError, subprocess.SubprocessError):
        print(
            "Gate B failed. Check clean state, prerequisite evidence and verification commands.",
            file=sys.stderr,
        )
        return 1
    print(json.dumps({"status": report["status"], "commit": report["commit"]}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
