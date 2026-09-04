#!/usr/bin/env python3
"""Create a metadata-only seal for an externally held blind benchmark."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
from collections.abc import Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Final

CUSTODIAN_ROLE: Final = "Person 5 — Product and demo lead"
_SHA256_PATTERN: Final = re.compile(r"[0-9a-fA-F]{64}")
_STABLE_ID_PATTERN: Final = re.compile(r"[a-z0-9]+(?:[-_][a-z0-9]+)*")
_REPOSITORY_ROOT: Final = Path(__file__).resolve().parents[1]


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _read_supplied_sha256(path: Path, label: str) -> str:
    try:
        tokens = path.read_text(encoding="utf-8").split()
    except (OSError, UnicodeError) as exc:
        raise ValueError(f"cannot read {label} SHA-256 file: {path}") from exc
    if not tokens or _SHA256_PATTERN.fullmatch(tokens[0]) is None:
        raise ValueError(f"malformed {label} SHA-256")
    return tokens[0].lower()


def _read_defect_ids(path: Path) -> list[str]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ValueError("defect IDs file must contain a valid JSON array") from exc
    if not isinstance(value, list):
        raise ValueError("defect IDs file must contain a JSON array")  # noqa: TRY004
    if len(value) != 3:
        raise ValueError("defect IDs file must contain exactly three IDs")
    if any(
        not isinstance(item, str) or _STABLE_ID_PATTERN.fullmatch(item) is None
        for item in value
    ):
        raise ValueError("defect IDs must be stable lowercase identifiers")
    if len(set(value)) != len(value):
        raise ValueError("defect IDs must be unique")
    if value != sorted(value):
        raise ValueError("defect IDs must be sorted")
    return value


def _format_timestamp(value: datetime) -> str:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("creation time must include a timezone")
    return (
        value.astimezone(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    )


def _assert_archive_is_external(archive: Path, repository_root: Path) -> Path:
    try:
        resolved_archive = archive.resolve(strict=True)
    except OSError as exc:
        raise ValueError(f"cannot read archive: {archive}") from exc
    if not resolved_archive.is_file():
        raise ValueError(f"archive must be a regular file: {archive}")
    resolved_repository = repository_root.resolve(strict=True)
    if resolved_archive.is_relative_to(resolved_repository):
        raise ValueError("archive must be outside the repository")
    return resolved_archive


def create_seal_ledger(
    *,
    archive: Path,
    policy_sha256_file: Path,
    manifest_sha256_file: Path,
    defect_ids_file: Path,
    output: Path,
    repository_root: Path = _REPOSITORY_ROOT,
    created_at: datetime | None = None,
) -> dict[str, object]:
    """Validate external metadata and write a new public seal ledger.

    The archive is treated as opaque bytes. This function never opens it as a
    ZIP file and never reads, extracts, or records member names.
    """

    output = Path(output)
    if os.path.lexists(output):
        raise FileExistsError(f"refusing to overwrite existing ledger: {output}")

    resolved_archive = _assert_archive_is_external(Path(archive), Path(repository_root))
    policy_sha256 = _read_supplied_sha256(Path(policy_sha256_file), "policy")
    manifest_sha256 = _read_supplied_sha256(Path(manifest_sha256_file), "manifest")
    defect_ids = _read_defect_ids(Path(defect_ids_file))
    canonical_ids = json.dumps(
        defect_ids, ensure_ascii=False, separators=(",", ":")
    ).encode("utf-8")
    timestamp = _format_timestamp(created_at or datetime.now(UTC))

    ledger: dict[str, object] = {
        "archive_sha256": _sha256_file(resolved_archive),
        "policy_sha256": policy_sha256,
        "manifest_sha256": manifest_sha256,
        "defect_ids_sha256": hashlib.sha256(canonical_ids).hexdigest(),
        "defect_count": len(defect_ids),
        "created_at": timestamp,
        "custodian_role": CUSTODIAN_ROLE,
    }

    output.parent.mkdir(parents=True, exist_ok=True)
    try:
        with output.open("x", encoding="utf-8", newline="\n") as stream:
            json.dump(ledger, stream, ensure_ascii=False, indent=2, sort_keys=True)
            stream.write("\n")
    except FileExistsError as exc:
        raise FileExistsError(
            f"refusing to overwrite existing ledger: {output}"
        ) from exc
    return ledger


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Seal an externally held blind benchmark without opening its archive."
    )
    parser.add_argument("--archive", required=True, type=Path)
    parser.add_argument("--policy-sha256-file", required=True, type=Path)
    parser.add_argument("--manifest-sha256-file", required=True, type=Path)
    parser.add_argument("--defect-ids-file", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)
    try:
        create_seal_ledger(
            archive=args.archive,
            policy_sha256_file=args.policy_sha256_file,
            manifest_sha256_file=args.manifest_sha256_file,
            defect_ids_file=args.defect_ids_file,
            output=args.output,
        )
    except (FileExistsError, ValueError) as exc:
        parser.exit(2, f"error: {exc}\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
