#!/usr/bin/env python3
"""Mechanically verify PolicyFuzz submission artifacts and evidence claims."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import re
import subprocess
import sys
from collections import Counter
from collections.abc import Callable, Sequence
from pathlib import Path
from typing import Any

MAX_PACKAGE_BYTES = 5_000_000_000
MAX_VIDEO_SECONDS = 300.0
COMMAND_TIMEOUT_SECONDS = 120
SUPPORTED_VIDEO_CODECS = {"av1", "h264", "hevc", "vp8", "vp9"}
REQUIRED_METRIC_KEYS = (
    "manual_review_1_minutes",
    "manual_review_2_minutes",
    "time_to_first_correct_finding_seconds",
    "total_run_time_seconds",
    "scenario_count",
    "confirmation_count",
    "model_call_count",
    "provider_cost_usd",
    "development_seeded_defect_recall",
    "development_regression_pass_rate",
    "control_regression_pass_rate",
    "blind_seeded_defect_recall",
)
RATE_METRIC_KEYS = {
    "development_seeded_defect_recall",
    "development_regression_pass_rate",
    "control_regression_pass_rate",
    "blind_seeded_defect_recall",
}
FINAL_SCRIPT_PATH = Path("submission/video/script.md")
MAX_METRIC_INTEGER = 10**15
PRIVATE_PATH_MARKERS = {"featureprompts", "privatebench", "privatebenchmark"}
EXCLUDED_DIRECTORY_MARKERS = {
    "git",
    "superpowers",
    "nodemodules",
    "venv",
    "cache",
    "pytestcache",
    "ruffcache",
    "coverage",
    "htmlcov",
    "build",
    "dist",
    "rawvideo",
    "backupvideo",
    "rawbackupvideo",
}
FINAL_DELIVERABLE_NAMES = {
    "PolicyFuzz-Pitch.pdf",
    "PolicyFuzz-Pitch.pptx",
    "PolicyFuzz-Demo.mp4",
    "PolicyFuzz-Demo.srt",
    "verified-metrics.json",
    "demo-run.json",
}
PROVENANCE_FIELDS = (
    "data_type",
    "run_mode",
    "verification_status",
    "blind_eligibility",
)
VERIFIED_METRIC_FIELDS = {
    "status",
    "display_value",
    "numerator",
    "denominator",
    "basis_points",
    "source_artifact",
    "frozen_commit",
    "suite_hash",
    "engine_version",
    "provenance",
}
METRIC_PLACEHOLDER = re.compile(r"\{\{metric:([a-z0-9_]+)\}\}")
METRIC_CLAIM = re.compile(
    r"\[\[metric:([a-z0-9_]+)\|([^|\]\n]+)\|([^|\]\n]+)\|"
    r"([^|\]\n]+)\|([^|\]\n]+)\|blind-([^|\]\n]+)\]\]"
)
ANY_METRIC_MARKER = re.compile(r"\[\[metric:[^\]\n]*\]\]")
NUMBER = re.compile(r"(?<![\w:])\d+(?:\.\d+)?%?")
TIMECODE = re.compile(r"\b\d{1,2}:\d{2}(?:\s*[–—-]\s*\d{1,2}:\d{2})?\b")
STRUCTURAL_SLIDE_PREFIX = re.compile(
    r"^\s*(?:(?:slide|page)\s+)?\d+\s+"
    r"(?=(?:measured\s+)?(?:benchmark\s+)?(?:evidence|results?|metrics?)\b)",
    re.IGNORECASE,
)
MEASUREMENT_WORD = re.compile(
    r"\b(?:accuracy|basis points?|benchmark(?:ed)?|confirmations?|coverage|"
    r"defects? found|findings? confirmed|measured|metrics?|model calls?|"
    r"precision|provider cost|recall|run ?time|scenarios?|time to first)\b",
    re.IGNORECASE,
)
HEX_40 = re.compile(r"[0-9a-f]{40}")
HEX_64 = re.compile(r"[0-9a-f]{64}")

Runner = Callable[..., Any]


def _normalise_part(value: str) -> str:
    return re.sub(r"[^a-z0-9]", "", value.lower())


def _has_private_part(parts: Sequence[str]) -> bool:
    return any(
        marker in _normalise_part(part)
        for part in parts
        for marker in PRIVATE_PATH_MARKERS
    )


def _safe_file(
    path: Path,
    root: Path,
    description: str,
    errors: list[str],
    *,
    require_relative: bool = False,
) -> Path | None:
    if require_relative and path.is_absolute():
        errors.append(f"{description} path must be relative to package root: {path}")
        return None
    if _has_private_part(path.parts):
        errors.append(f"{description} uses prohibited private path: {path}")
        return None
    candidate = path if path.is_absolute() else root / path
    try:
        resolved_root = root.resolve(strict=True)
        resolved = candidate.resolve(strict=True)
    except (FileNotFoundError, OSError) as exc:
        errors.append(f"{description} is unavailable: {path} ({exc})")
        return None
    if not resolved.is_relative_to(resolved_root):
        errors.append(f"{description} escapes package root: {path}")
        return None
    resolved_relative = resolved.relative_to(resolved_root)
    if _has_private_part(resolved_relative.parts):
        errors.append(f"{description} resolves through prohibited private path: {path}")
        return None
    if not resolved.is_file():
        errors.append(f"{description} is not a regular file: {path}")
        return None
    return resolved


def _run(
    name: str,
    args: list[str],
    runner: Runner,
    errors: list[str],
) -> str | None:
    try:
        result = runner(
            args,
            capture_output=True,
            text=True,
            timeout=COMMAND_TIMEOUT_SECONDS,
            check=False,
        )
    except subprocess.TimeoutExpired:
        errors.append(f"{name} timed out after {COMMAND_TIMEOUT_SECONDS} seconds")
        return None
    except (OSError, ValueError) as exc:
        errors.append(f"{name} could not run: {exc}")
        return None
    if result.returncode != 0:
        detail = str(result.stderr).strip().splitlines()
        suffix = f": {detail[0]}" if detail else ""
        errors.append(f"{name} failed with exit code {result.returncode}{suffix}")
        return None
    return str(result.stdout)


def _inspect_deck(deck: Path, runner: Runner, errors: list[str]) -> str:
    info = _run("pdfinfo", ["pdfinfo", str(deck)], runner, errors)
    if info is not None:
        match = re.search(r"^Pages:\s*(\d+)\s*$", info, re.MULTILINE)
        if match is None:
            errors.append("pdfinfo response has no integer Pages field")
        else:
            pages = int(match.group(1))
            if not 1 <= pages <= 10:
                errors.append(f"deck has {pages} pages; expected 1 through 10")
    text = _run("pdftotext", ["pdftotext", str(deck), "-"], runner, errors)
    if text is None or not text.strip(" \t\r\n\f"):
        errors.append("deck text is empty or could not be extracted for claim audit")
        return ""
    return text


def _inspect_video(video: Path, runner: Runner, errors: list[str]) -> None:
    output = _run(
        "ffprobe",
        [
            "ffprobe",
            "-v",
            "error",
            "-show_entries",
            "format=duration:stream=index,codec_type,codec_name,duration",
            "-of",
            "json",
            str(video),
        ],
        runner,
        errors,
    )
    video_stream: dict[str, Any] | None = None
    payload: dict[str, Any] = {}
    if output is not None:
        try:
            decoded = json.loads(output)
            if isinstance(decoded, dict):
                payload = decoded
            else:
                errors.append("ffprobe response must be a JSON object")
        except json.JSONDecodeError as exc:
            errors.append(f"ffprobe returned malformed JSON: {exc.msg}")
    streams = payload.get("streams", [])
    if isinstance(streams, list):
        video_stream = next(
            (
                stream
                for stream in streams
                if isinstance(stream, dict) and stream.get("codec_type") == "video"
            ),
            None,
        )
    if video_stream is None:
        errors.append("video has no video stream")
    else:
        codec = video_stream.get("codec_name")
        if codec not in SUPPORTED_VIDEO_CODECS:
            errors.append(f"video codec is unsupported: {codec!r}")
    duration_value = None
    if isinstance(payload.get("format"), dict):
        duration_value = payload["format"].get("duration")
    if duration_value is None and video_stream is not None:
        duration_value = video_stream.get("duration")
    try:
        duration = float(duration_value)
        if not math.isfinite(duration) or duration <= 0:
            raise ValueError
    except (TypeError, ValueError):
        errors.append("video duration is missing or invalid")
    else:
        if duration > MAX_VIDEO_SECONDS:
            errors.append(
                f"video duration is {duration:.3f} seconds; maximum is {MAX_VIDEO_SECONDS:.1f}"
            )
    _run(
        "ffmpeg decode",
        [
            "ffmpeg",
            "-nostdin",
            "-xerror",
            "-v",
            "error",
            "-i",
            str(video),
            "-map",
            "0:v:0",
            "-f",
            "null",
            "-",
        ],
        runner,
        errors,
    )


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _is_integer(value: object) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def _percent_display(basis_points: int) -> str:
    whole, fraction = divmod(basis_points, 100)
    if fraction == 0:
        return f"{whole}%"
    return f"{whole}.{fraction:02d}".rstrip("0") + "%"


def _validate_arithmetic(
    key: str, metric: dict[str, Any], errors: list[str]
) -> str | None:
    numerator = metric.get("numerator")
    denominator = metric.get("denominator")
    basis_points = metric.get("basis_points")
    not_applicable = "not_applicable"
    numeric_values = (numerator, denominator, basis_points)
    if any(isinstance(value, float) for value in numeric_values):
        errors.append(f"metric '{key}' must use integer arithmetic")
        return None
    integers = [value for value in numeric_values if _is_integer(value)]
    if any(value < 0 for value in integers):
        errors.append(f"metric '{key}' arithmetic values must be non-negative")
        return None
    if any(value > MAX_METRIC_INTEGER for value in integers):
        errors.append(f"metric '{key}' exceeds numeric bound {MAX_METRIC_INTEGER}")
        return None
    if numerator == denominator == basis_points == not_applicable:
        return "N/A"
    if (
        _is_integer(numerator)
        and _is_integer(denominator)
        and _is_integer(basis_points)
    ):
        if key not in RATE_METRIC_KEYS:
            errors.append(f"metric '{key}' must use count or N/A arithmetic")
            return None
        if denominator <= 0:
            errors.append(f"metric '{key}' denominator must be greater than zero")
            return None
        if numerator > denominator:
            errors.append(f"metric '{key}' numerator cannot exceed denominator")
            return None
        expected = (numerator * 10_000 + denominator // 2) // denominator
        if basis_points != expected:
            errors.append(
                f"metric '{key}' basis_points is {basis_points}; expected {expected}"
            )
            return None
        return _percent_display(basis_points)
    if _is_integer(numerator) and denominator == basis_points == not_applicable:
        if key in RATE_METRIC_KEYS:
            errors.append(f"metric '{key}' must use ratio or N/A arithmetic")
            return None
        if key == "provider_cost_usd":
            dollars, cents = divmod(numerator, 100)
            return f"${dollars}.{cents:02d}"
        return str(numerator)
    errors.append(f"metric '{key}' numerator/denominator/basis_points are inconsistent")
    return None


def _validate_display(
    key: str, metric: dict[str, Any], expected: str | None, errors: list[str]
) -> None:
    display = metric.get("display_value")
    if not isinstance(display, str) or not display:
        errors.append(f"metric '{key}' display_value is required")
        return
    if expected is not None and display != expected:
        errors.append(
            f"metric '{key}' display_value {display!r} does not match arithmetic {expected!r}"
        )


def _load_evidence(path: Path, errors: list[str]) -> dict[str, Any]:
    try:
        decoded = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        errors.append(f"evidence JSON is invalid: {exc}")
        return {}
    if not isinstance(decoded, dict):
        errors.append("evidence JSON must contain an object")
        return {}
    return decoded


def _validate_provenance(
    value: object, description: str, errors: list[str]
) -> dict[str, str] | None:
    if not isinstance(value, dict) or set(value) != set(PROVENANCE_FIELDS):
        errors.append(
            f"{description} provenance must contain exactly "
            + ", ".join(PROVENANCE_FIELDS)
        )
        return None
    if not all(isinstance(value[field], str) for field in PROVENANCE_FIELDS):
        errors.append(f"{description} provenance values must be strings")
        return None
    provenance = {field: value[field] for field in PROVENANCE_FIELDS}
    expected_values = {
        "data_type": {"synthetic"},
        "run_mode": {"live", "cached"},
        "verification_status": {"verified"},
        "blind_eligibility": {"eligible"},
    }
    for field, allowed in expected_values.items():
        if provenance[field] not in allowed:
            errors.append(
                f"{description} provenance {field}={provenance[field]!r} is not "
                f"one of {', '.join(sorted(allowed))}"
            )
    return provenance


def _compare_provenance(
    value: object,
    expected: dict[str, str] | None,
    description: str,
    errors: list[str],
) -> dict[str, str] | None:
    provenance = _validate_provenance(value, description, errors)
    if provenance is None or expected is None:
        return provenance
    for field in PROVENANCE_FIELDS:
        if provenance[field] != expected[field]:
            errors.append(
                f"{description} provenance {field} does not match submission provenance"
            )
    return provenance


def _validate_evidence(
    evidence: dict[str, Any], root: Path, errors: list[str]
) -> tuple[
    dict[str, dict[str, Any]],
    list[Path],
    dict[Path, dict[str, str]],
    dict[str, str] | None,
]:
    if evidence.get("status") != "final":
        errors.append("evidence status must be final for gold scoring")
    if evidence.get("scoring_eligible") is not True:
        errors.append("evidence scoring_eligible must be true for gold scoring")

    frozen = {
        "frozen_commit": evidence.get("frozen_commit"),
        "suite_hash": evidence.get("suite_hash"),
        "engine_version": evidence.get("engine_version"),
    }
    if not isinstance(frozen["frozen_commit"], str) or not HEX_40.fullmatch(
        frozen["frozen_commit"]
    ):
        errors.append("frozen_commit must be a full 40-character lowercase commit hash")
    if not isinstance(frozen["suite_hash"], str) or not HEX_64.fullmatch(
        frozen["suite_hash"]
    ):
        errors.append("suite_hash must be a lowercase SHA-256 digest")
    if not isinstance(frozen["engine_version"], str) or not frozen["engine_version"]:
        errors.append("engine_version must be a non-empty string")
    submission_provenance = _validate_provenance(
        evidence.get("provenance"), "submission", errors
    )

    candidate_files: list[Path] = []
    valid_artifacts: set[str] = set()
    artifacts = evidence.get("source_artifacts")
    if not isinstance(artifacts, dict):
        errors.append("source_artifacts must be an object")
        artifacts = {}
    for artifact_id, artifact in artifacts.items():
        if not isinstance(artifact_id, str) or not isinstance(artifact, dict):
            errors.append("each source_artifact must be a named object")
            continue
        raw_path = artifact.get("path")
        expected_hash = artifact.get("sha256")
        if not isinstance(raw_path, str):
            errors.append(f"source artifact '{artifact_id}' has no path")
            continue
        source = _safe_file(
            Path(raw_path),
            root,
            f"source artifact '{artifact_id}'",
            errors,
            require_relative=True,
        )
        if not isinstance(expected_hash, str) or not HEX_64.fullmatch(expected_hash):
            errors.append(f"source artifact '{artifact_id}' has an invalid sha256")
            continue
        if source is None:
            continue
        candidate_files.append(source)
        if _sha256(source) != expected_hash:
            errors.append(f"source artifact '{artifact_id}' hash mismatch")
            continue
        valid_artifacts.add(artifact_id)

    metrics = evidence.get("metrics")
    if not isinstance(metrics, dict):
        errors.append("metrics must be an object")
        metrics = {}
    required = evidence.get("required_metrics")
    if not isinstance(required, list) or not all(
        isinstance(item, str) for item in required
    ):
        errors.append("required_metrics must be a list of metric keys")
        required = []
    if len(required) != len(set(required)):
        errors.append("required_metrics contains duplicates")
    if set(required) != set(REQUIRED_METRIC_KEYS):
        errors.append("required_metrics must contain the fixed Task 24 keys")
    extra_metrics = set(metrics) - set(REQUIRED_METRIC_KEYS)
    if extra_metrics:
        errors.append(
            f"metrics contains unsupported keys: {', '.join(sorted(extra_metrics))}"
        )

    validated_metrics: dict[str, dict[str, Any]] = {}
    for key in REQUIRED_METRIC_KEYS:
        metric = metrics.get(key)
        if not isinstance(metric, dict):
            errors.append(f"required metric '{key}' is missing")
            continue
        if metric.get("status") != "verified":
            errors.append(f"required metric '{key}' is pending or unverified")
            continue
        if set(metric) != VERIFIED_METRIC_FIELDS:
            errors.append(
                f"metric '{key}' must contain exactly the metric contract fields"
            )
        for field, expected in frozen.items():
            if metric.get(field) != expected:
                errors.append(f"metric '{key}' {field} does not match frozen metadata")
        artifact_id = metric.get("source_artifact")
        if artifact_id not in valid_artifacts:
            errors.append(f"metric '{key}' has no hash-verified source_artifact")
        metric_provenance = _compare_provenance(
            metric.get("provenance"), submission_provenance, f"metric '{key}'", errors
        )
        expected_display = _validate_arithmetic(key, metric, errors)
        _validate_display(key, metric, expected_display, errors)
        if metric_provenance is not None:
            validated_metrics[key] = metric

    claim_source_paths: dict[Path, dict[str, str]] = {}
    claim_sources = evidence.get("claim_sources", [])
    if not isinstance(claim_sources, list):
        errors.append("claim_sources must be a list of path/provenance objects")
    else:
        declared_paths: list[str] = []
        for index, entry in enumerate(claim_sources):
            if not isinstance(entry, dict) or set(entry) != {"path", "provenance"}:
                errors.append(
                    f"claim source {index + 1} must contain exactly path and provenance"
                )
                continue
            source_path = entry["path"]
            if not isinstance(source_path, str):
                errors.append(f"claim source {index + 1} path must be a string")
                continue
            declared_paths.append(source_path)
            source = _safe_file(
                Path(source_path),
                root,
                f"claim source {index + 1}",
                errors,
                require_relative=True,
            )
            provenance = _compare_provenance(
                entry["provenance"],
                submission_provenance,
                f"claim source {source_path!r}",
                errors,
            )
            if source is not None and provenance is not None:
                claim_source_paths[source] = provenance
        if len(declared_paths) != len(set(declared_paths)):
            errors.append("claim_sources contains duplicate paths")
        if FINAL_SCRIPT_PATH.as_posix() not in declared_paths:
            errors.append(
                f"final script claim source is required: {FINAL_SCRIPT_PATH.as_posix()}"
            )
    return (
        validated_metrics,
        candidate_files,
        claim_source_paths,
        submission_provenance,
    )


def _read_claim_source(path: Path, errors: list[str]) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except (OSError, UnicodeError) as exc:
        errors.append(f"claim source cannot be read as UTF-8: {path} ({exc})")
        return ""


def _validate_claims(
    texts: Sequence[tuple[str, str, dict[str, str] | None]],
    metrics: dict[str, dict[str, Any]],
    errors: list[str],
) -> None:
    for source_name, text, source_provenance in texts:
        for key in sorted(set(METRIC_PLACEHOLDER.findall(text))):
            errors.append(f"{source_name}: unresolved metric placeholder '{key}'")
        claims = list(METRIC_CLAIM.finditer(text))
        canonical_text = METRIC_CLAIM.sub("", text)
        for marker in ANY_METRIC_MARKER.findall(canonical_text):
            errors.append(f"{source_name}: noncanonical metric marker {marker!r}")
        for claim in claims:
            key, display, data_type, run_mode, verification, blind = claim.groups()
            metric = metrics.get(key)
            if metric is None:
                errors.append(
                    f"{source_name}: metric reference '{key}' has no evidence entry"
                )
                continue
            if display != metric.get("display_value"):
                errors.append(
                    f"{source_name}: claim display {display!r} does not match evidence "
                    f"{metric.get('display_value')!r} for '{key}'"
                )
            claim_provenance = {
                "data_type": data_type,
                "run_mode": run_mode,
                "verification_status": verification,
                "blind_eligibility": blind,
            }
            metric_provenance = metric.get("provenance")
            for field in PROVENANCE_FIELDS:
                expected = (
                    metric_provenance.get(field)
                    if isinstance(metric_provenance, dict)
                    else None
                )
                if claim_provenance[field] != expected:
                    errors.append(
                        f"{source_name}: claim provenance {field} does not match "
                        f"metric '{key}'"
                    )
                if (
                    source_provenance is not None
                    and claim_provenance[field] != source_provenance[field]
                ):
                    errors.append(
                        f"{source_name}: claim provenance {field} does not match source"
                    )
        for line_number, line in enumerate(text.splitlines(), start=1):
            has_canonical_claim = METRIC_CLAIM.search(line) is not None
            claim_text = METRIC_CLAIM.sub("", line)
            claim_text = METRIC_PLACEHOLDER.sub("", claim_text)
            claim_text = TIMECODE.sub("", claim_text)
            claim_text = STRUCTURAL_SLIDE_PREFIX.sub("", claim_text)
            if NUMBER.search(claim_text) and (
                has_canonical_claim or MEASUREMENT_WORD.search(claim_text)
            ):
                errors.append(
                    f"{source_name}:{line_number}: measured value is not bound by a "
                    "canonical metric claim"
                )


def _is_excluded_directory(name: str) -> bool:
    return _normalise_part(name) in EXCLUDED_DIRECTORY_MARKERS


def _is_excluded_file(path: Path) -> bool:
    name = path.name.lower()
    if (
        name == ".git"
        or name == ".env"
        or (name.startswith(".env.") and name != ".env.example")
    ):
        return True
    if name in {"coverage.xml", ".coverage"} or name.endswith((".pyc", ".pyo")):
        return True
    if path.suffix.lower() in {".mp4", ".mov", ".mkv", ".webm"}:
        stem = _normalise_part(path.stem)
        return "raw" in stem or "backup" in stem
    return False


def enumerate_candidate_files(
    package_root: Path,
) -> tuple[tuple[Path, ...], list[str]]:
    """Return the deterministic, root-relative file set Task 25 must package."""
    errors: list[str] = []
    try:
        root = package_root.resolve(strict=True)
    except (FileNotFoundError, OSError) as exc:
        return (), [f"package root is unavailable: {package_root} ({exc})"]
    if not root.is_dir():
        return (), [f"package root is not a directory: {package_root}"]

    candidate_files: list[Path] = []
    try:
        for directory, directory_names, file_names in os.walk(root, followlinks=False):
            parent = Path(directory)
            kept_directories: list[str] = []
            for name in sorted(directory_names):
                path = parent / name
                relative = path.relative_to(root)
                if _has_private_part(relative.parts):
                    errors.append(
                        f"candidate contains prohibited private path: {relative}"
                    )
                    continue
                if path.is_symlink():
                    errors.append(f"candidate contains symlink: {relative}")
                    continue
                if _is_excluded_directory(name):
                    continue
                kept_directories.append(name)
            directory_names[:] = kept_directories
            for name in sorted(file_names):
                path = parent / name
                relative = path.relative_to(root)
                if _has_private_part(relative.parts):
                    errors.append(
                        f"candidate contains prohibited private path: {relative}"
                    )
                    continue
                if _is_excluded_file(path):
                    continue
                if path.is_symlink():
                    errors.append(f"candidate contains symlink: {relative}")
                    continue
                if not path.is_file():
                    errors.append(f"candidate member is not a regular file: {relative}")
                    continue
                candidate_files.append(relative)
    except OSError as exc:
        errors.append(f"candidate directory could not be scanned: {exc}")

    candidate_files.sort(key=lambda path: path.as_posix())
    return tuple(candidate_files), errors


def _validate_candidate_files(
    root: Path,
    candidate_files: Sequence[Path],
    final_names: set[str],
    errors: list[str],
) -> None:
    total = 0
    final_counts: Counter[str] = Counter()
    try:
        for relative in candidate_files:
            total += (root / relative).stat().st_size
            if relative.name in final_names:
                final_counts[relative.name] += 1
    except OSError as exc:
        errors.append(f"candidate file could not be measured: {exc}")
        return
    for name, count in sorted(final_counts.items()):
        if count > 1:
            errors.append(f"duplicate final deliverable filename '{name}'")
    if total >= MAX_PACKAGE_BYTES:
        errors.append(
            f"candidate package is {total} bytes; must be below {MAX_PACKAGE_BYTES} bytes"
        )


def verify_submission(
    *,
    deck: Path,
    video: Path,
    evidence: Path,
    package_root: Path,
    sources: Sequence[Path] = (),
    runner: Runner = subprocess.run,
) -> list[str]:
    """Return compact validation failures; an empty list means all checks passed."""
    errors: list[str] = []
    try:
        root = package_root.resolve(strict=True)
    except (FileNotFoundError, OSError) as exc:
        return [f"package root is unavailable: {package_root} ({exc})"]
    if not root.is_dir():
        return [f"package root is not a directory: {package_root}"]

    safe_deck = _safe_file(deck, root, "deck", errors)
    safe_video = _safe_file(video, root, "video", errors)
    safe_evidence = _safe_file(evidence, root, "evidence", errors)
    explicit_sources = [
        safe
        for index, source in enumerate(sources)
        if (safe := _safe_file(source, root, f"source {index + 1}", errors)) is not None
    ]
    deck_text = _inspect_deck(safe_deck, runner, errors) if safe_deck else ""
    if safe_video:
        _inspect_video(safe_video, runner, errors)

    payload = _load_evidence(safe_evidence, errors) if safe_evidence else {}
    metrics, _artifact_files, manifest_sources, submission_provenance = (
        _validate_evidence(payload, root, errors)
    )
    for source in explicit_sources:
        if source not in manifest_sources:
            errors.append(
                f"explicit claim source is not declared in evidence: "
                f"{source.relative_to(root)}"
            )
    all_sources = list(dict.fromkeys([*manifest_sources, *explicit_sources]))
    claim_texts: list[tuple[str, str, dict[str, str] | None]] = [
        ("deck", deck_text, submission_provenance)
    ]
    for path in all_sources:
        text = _read_claim_source(path, errors)
        if not text.strip():
            errors.append(f"claim source is empty: {path.relative_to(root)}")
        claim_texts.append(
            (str(path.relative_to(root)), text, manifest_sources.get(path))
        )
    _validate_claims(claim_texts, metrics, errors)

    final_names = set(FINAL_DELIVERABLE_NAMES)
    final_names.update(path.name for path in (deck, video, evidence))
    candidate_files, candidate_errors = enumerate_candidate_files(root)
    errors.extend(candidate_errors)
    _validate_candidate_files(root, candidate_files, final_names, errors)
    return errors


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--deck", type=Path, required=True)
    parser.add_argument("--video", type=Path, required=True)
    parser.add_argument("--evidence", type=Path, required=True)
    parser.add_argument(
        "--source",
        action="append",
        type=Path,
        default=[],
        help="additional UTF-8 claim source; may be repeated",
    )
    parser.add_argument(
        "--package-root",
        "--candidate-root",
        dest="package_root",
        type=Path,
        default=Path.cwd(),
        help=(
            "complete candidate directory to scan and path-confinement root; "
            "known development/dependency/build/cache and raw-video exclusions apply"
        ),
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    errors = verify_submission(
        deck=args.deck,
        video=args.video,
        evidence=args.evidence,
        package_root=args.package_root,
        sources=args.source,
    )
    if errors:
        print(f"FAIL ({len(errors)})")
        for error in errors:
            print(f"- {error}")
        return 1
    print("PASS submission artifacts and evidence verified")
    return 0


if __name__ == "__main__":
    sys.exit(main())
