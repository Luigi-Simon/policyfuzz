#!/usr/bin/env python3
"""Build a deterministic PolicyFuzz submission archive after strict preflight."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import stat
import subprocess
import sys
import tempfile
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile, ZipInfo

try:
    from scripts.verify_submission import (
        MAX_PACKAGE_BYTES as VERIFIER_MAX_PACKAGE_BYTES,
    )
    from scripts.verify_submission import enumerate_candidate_files
except ModuleNotFoundError as exc:
    if exc.name != "scripts":
        raise
    from verify_submission import (  # type: ignore[no-redef]
        MAX_PACKAGE_BYTES as VERIFIER_MAX_PACKAGE_BYTES,
    )
    from verify_submission import enumerate_candidate_files  # type: ignore[no-redef]

MAX_PACKAGE_BYTES = VERIFIER_MAX_PACKAGE_BYTES
DEFAULT_TAG = "demo-v1"
REQUIRED_MEMBERS = (
    Path("README.md"),
    Path("submission/deck/PolicyFuzz-Pitch.pdf"),
    Path("submission/video/PolicyFuzz-Demo.mp4"),
    Path("submission/evidence/verified-metrics.json"),
)
ZIP_TIMESTAMP = (1980, 1, 1, 0, 0, 0)
READ_CHUNK_BYTES = 1024 * 1024
SCAN_OVERLAP_BYTES = 4096
COMMAND_TIMEOUT_SECONDS = 30

_DIRECT_CREDENTIAL_PATTERNS = (
    re.compile(rb"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----"),
    re.compile(rb"\bsk-(?:proj-)?[A-Za-z0-9_-]{16,}\b"),
    re.compile(rb"\bghp_[A-Za-z0-9]{20,}\b"),
    re.compile(rb"\bgithub_pat_[A-Za-z0-9_]{20,}\b"),
    re.compile(rb"\bxox[baprs]-[A-Za-z0-9-]{16,}\b"),
    re.compile(rb"\bAKIA[0-9A-Z]{16}\b"),
)
_ASSIGNED_CREDENTIAL = re.compile(
    rb"(?m)[\"']?\b(?:OPENAI_API_KEY|AWS_SECRET_ACCESS_KEY|GITHUB_TOKEN|"
    rb"DATABASE_URL|CLIENT_SECRET|PRIVATE_KEY|API_KEY|ACCESS_TOKEN|PASSWORD)"
    rb"\b[\"']?[ \t]*[:=][ \t]*[\"']?([^\s\"'#]{8,512})"
)
_SAFE_PLACEHOLDER_VALUES = {
    b"changeme",
    b"dummy",
    b"example",
    b"placeholder",
    b"replace-me",
    b"secret-key",
    b"synthetic-secret",
    b"test-api-key",
}
_SAFE_PLACEHOLDER_FORMS = (
    re.compile(rb"<[A-Za-z_][A-Za-z0-9_.:-]*>"),
    re.compile(rb"\$\{[A-Za-z_][A-Za-z0-9_]*\}"),
    re.compile(rb"\{[A-Za-z_][A-Za-z0-9_]*\}"),
    re.compile(
        rb"(?:your|replace|example|dummy|test|synthetic)"
        rb"(?:[-_][a-z0-9]+){1,4}"
    ),
)


class PackageValidationError(ValueError):
    """Raised when submission packaging preflight refuses the candidate."""


@dataclass(frozen=True)
class MemberRecord:
    path: Path
    size: int
    sha256: str


@dataclass(frozen=True)
class PackageResult:
    tag: str
    commit: str
    members: tuple[MemberRecord, ...]
    total_bytes: int
    archive_sha256: str | None
    archive_bytes: int | None


def _git(repository: Path, *args: str) -> bytes:
    try:
        result = subprocess.run(
            ["git", *args],
            cwd=repository,
            check=False,
            capture_output=True,
            timeout=COMMAND_TIMEOUT_SECONDS,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise PackageValidationError(f"git validation could not run: {exc}") from exc
    if result.returncode != 0:
        raise PackageValidationError(
            f"git {' '.join(args[:2])} failed with exit code {result.returncode}"
        )
    return result.stdout


def _is_environment_file(path: Path) -> bool:
    name = path.name.lower()
    return name == ".env" or (name.startswith(".env.") and name != ".env.example")


def _validate_git_state(repository: Path, tag: str) -> tuple[str, list[str]]:
    errors: list[str] = []
    try:
        _git(repository, "rev-parse", "--show-toplevel")
        _git(repository, "check-ref-format", f"refs/tags/{tag}")
        head = _git(repository, "rev-parse", "--verify", "HEAD").decode().strip()
        tagged = (
            _git(repository, "rev-parse", "--verify", f"refs/tags/{tag}^{{commit}}")
            .decode()
            .strip()
        )
        if tagged != head:
            errors.append(f"tag '{tag}' does not match HEAD commit")
        status_output = _git(
            repository, "status", "--porcelain=v1", "--untracked-files=all"
        )
        if status_output:
            errors.append("Git working tree is not clean")
        tracked_output = _git(repository, "ls-files", "-z")
        tracked = (
            Path(os.fsdecode(item)) for item in tracked_output.split(b"\0") if item
        )
        tracked_environments = sorted(
            path.as_posix() for path in tracked if _is_environment_file(path)
        )
        if tracked_environments:
            errors.append(
                "Git contains tracked environment file(s): "
                + ", ".join(tracked_environments)
            )
    except (PackageValidationError, UnicodeError) as exc:
        return "", [str(exc)]
    return head, errors


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(READ_CHUNK_BYTES), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _safe_placeholder(value: bytes) -> bool:
    lowered = value.lower()
    return lowered in _SAFE_PLACEHOLDER_VALUES or any(
        pattern.fullmatch(lowered) for pattern in _SAFE_PLACEHOLDER_FORMS
    )


def _has_credential_shaped_content(path: Path) -> bool:
    overlap = b""
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(READ_CHUNK_BYTES), b""):
            window = overlap + chunk
            if any(pattern.search(window) for pattern in _DIRECT_CREDENTIAL_PATTERNS):
                return True
            if any(
                not _safe_placeholder(match.group(1))
                for match in _ASSIGNED_CREDENTIAL.finditer(window)
            ):
                return True
            overlap = window[-SCAN_OVERLAP_BYTES:]
    return False


def _inspect_members(
    repository: Path, candidates: Sequence[Path]
) -> tuple[tuple[MemberRecord, ...], list[str]]:
    errors: list[str] = []
    missing = [path.as_posix() for path in REQUIRED_MEMBERS if path not in candidates]
    if missing:
        errors.extend(f"required package member is missing: {path}" for path in missing)

    records: list[MemberRecord] = []
    total_bytes = 0
    for relative in candidates:
        source = repository / relative
        try:
            size = source.stat().st_size
            digest = _sha256_file(source)
            has_credential = _has_credential_shaped_content(source)
        except OSError as exc:
            errors.append(f"candidate member could not be read: {relative} ({exc})")
            continue
        total_bytes += size
        records.append(MemberRecord(path=relative, size=size, sha256=digest))
        if has_credential:
            errors.append(f"credential-shaped content detected in: {relative}")
    if total_bytes >= MAX_PACKAGE_BYTES:
        errors.append(
            f"candidate package is {total_bytes} bytes; must be below "
            f"{MAX_PACKAGE_BYTES} bytes"
        )
    return tuple(records), errors


def _preflight(repository: Path, tag: str) -> PackageResult:
    try:
        root = repository.resolve(strict=True)
    except OSError as exc:
        raise PackageValidationError(
            f"package root is unavailable: {repository}"
        ) from exc
    if not root.is_dir():
        raise PackageValidationError(f"package root is not a directory: {repository}")

    candidates, candidate_errors = enumerate_candidate_files(root)
    commit, git_errors = _validate_git_state(root, tag)
    members, member_errors = _inspect_members(root, candidates)
    errors = [*candidate_errors, *git_errors, *member_errors]
    if errors:
        raise PackageValidationError("\n".join(errors))
    return PackageResult(
        tag=tag,
        commit=commit,
        members=members,
        total_bytes=sum(member.size for member in members),
        archive_sha256=None,
        archive_bytes=None,
    )


def _zip_info(member: MemberRecord) -> ZipInfo:
    info = ZipInfo(member.path.as_posix(), date_time=ZIP_TIMESTAMP)
    info.compress_type = ZIP_DEFLATED
    info.create_system = 3
    info.external_attr = (stat.S_IFREG | 0o644) << 16
    info.file_size = member.size
    return info


def _write_archive(
    repository: Path, destination: Path, members: Sequence[MemberRecord]
) -> None:
    with ZipFile(
        destination, "w", compression=ZIP_DEFLATED, allowZip64=True
    ) as archive:
        for member in members:
            with (
                (repository / member.path).open("rb") as source,
                archive.open(_zip_info(member), "w", force_zip64=True) as target,
            ):
                shutil.copyfileobj(source, target, length=READ_CHUNK_BYTES)


def _verify_archive(path: Path, members: Sequence[MemberRecord]) -> None:
    expected_names = [member.path.as_posix() for member in members]
    with ZipFile(path) as archive:
        infos = archive.infolist()
        if [info.filename for info in infos] != expected_names:
            raise PackageValidationError("archive member list does not match allowlist")
        for info, member in zip(infos, members, strict=True):
            if info.date_time != ZIP_TIMESTAMP:
                raise PackageValidationError(
                    f"archive member has nondeterministic timestamp: {member.path}"
                )
            digest = hashlib.sha256()
            with archive.open(info) as source:
                for chunk in iter(lambda: source.read(READ_CHUNK_BYTES), b""):
                    digest.update(chunk)
            if info.file_size != member.size or digest.hexdigest() != member.sha256:
                raise PackageValidationError(
                    f"archive member hash or size mismatch: {member.path}"
                )


def _manifest_payload(result: PackageResult) -> dict[str, object]:
    return {
        "schema_version": "1.0",
        "tag": result.tag,
        "commit": result.commit,
        "total_member_bytes": result.total_bytes,
        "archive": {
            "sha256": result.archive_sha256,
            "size_bytes": result.archive_bytes,
        },
        "members": [
            {
                "path": member.path.as_posix(),
                "size_bytes": member.size,
                "sha256": member.sha256,
            }
            for member in result.members
        ],
    }


def _stage_text(path: Path, text: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{path.name}.", dir=path.parent
    )
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as stream:
            stream.write(text)
        return temporary
    except BaseException:
        temporary.unlink(missing_ok=True)
        raise


def _validate_output_target(path: Path, description: str) -> None:
    if path.is_symlink():
        raise OSError(f"{description} output must not be a symlink: {path}")
    if path.exists() and not path.is_file():
        raise IsADirectoryError(
            f"{description} output must be a regular file path: {path}"
        )


def _backup_path(path: Path) -> Path:
    descriptor, backup_name = tempfile.mkstemp(
        prefix=f".{path.name}.", suffix=".backup", dir=path.parent
    )
    os.close(descriptor)
    return Path(backup_name)


def _publish_pair(
    archive_staged: Path,
    archive_output: Path,
    manifest_staged: Path,
    manifest_output: Path,
) -> None:
    pairs = (
        (archive_staged, archive_output),
        (manifest_staged, manifest_output),
    )
    backups: list[tuple[Path, Path]] = []
    published: list[Path] = []
    try:
        for _, output in pairs:
            if os.path.lexists(output):
                backup = _backup_path(output)
                try:
                    output.replace(backup)
                except BaseException:
                    backup.unlink(missing_ok=True)
                    raise
                backups.append((output, backup))
        for staged, output in pairs:
            staged.replace(output)
            published.append(output)
    except BaseException as exc:
        rollback_errors: list[str] = []
        for output in reversed(published):
            try:
                output.unlink(missing_ok=True)
            except OSError:
                rollback_errors.append(str(output))
        for output, backup in reversed(backups):
            try:
                backup.replace(output)
            except OSError:
                rollback_errors.append(str(output))
        if rollback_errors:
            failed = ", ".join(rollback_errors)
            raise PackageValidationError(
                f"package publication failed and rollback was incomplete: {failed}"
            ) from exc
        raise
    else:
        for _, backup in backups:
            backup.unlink(missing_ok=True)


def package_submission(
    *,
    package_root: Path,
    output: Path,
    manifest_output: Path,
    tag: str = DEFAULT_TAG,
    check_only: bool = False,
) -> PackageResult:
    """Validate and optionally write the deterministic archive and hash manifest."""
    repository = Path(package_root)
    result = _preflight(repository, tag)
    if check_only:
        return result

    output = Path(output)
    manifest_output = Path(manifest_output)
    if output.resolve() == manifest_output.resolve():
        raise PackageValidationError("archive and manifest outputs must be different")
    output.parent.mkdir(parents=True, exist_ok=True)
    _validate_output_target(output, "archive")
    _validate_output_target(manifest_output, "manifest")
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{output.name}.", suffix=".tmp", dir=output.parent
    )
    os.close(descriptor)
    temporary = Path(temporary_name)
    manifest_temporary: Path | None = None
    try:
        _write_archive(repository.resolve(), temporary, result.members)
        _verify_archive(temporary, result.members)
        archive_bytes = temporary.stat().st_size
        if archive_bytes >= MAX_PACKAGE_BYTES:
            raise PackageValidationError(
                f"archive is {archive_bytes} bytes; must be below {MAX_PACKAGE_BYTES} bytes"
            )
        archive_sha256 = _sha256_file(temporary)
        completed = PackageResult(
            tag=result.tag,
            commit=result.commit,
            members=result.members,
            total_bytes=result.total_bytes,
            archive_sha256=archive_sha256,
            archive_bytes=archive_bytes,
        )
        manifest_text = (
            json.dumps(_manifest_payload(completed), indent=2, sort_keys=True) + "\n"
        )
        manifest_temporary = _stage_text(manifest_output, manifest_text)
        _publish_pair(temporary, output, manifest_temporary, manifest_output)
        return completed
    except BaseException:
        temporary.unlink(missing_ok=True)
        if manifest_temporary is not None:
            manifest_temporary.unlink(missing_ok=True)
        raise


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--package-root",
        "--candidate-root",
        dest="package_root",
        type=Path,
        default=Path.cwd(),
    )
    parser.add_argument("--tag", default=DEFAULT_TAG)
    parser.add_argument(
        "--output", type=Path, default=Path("dist/policyfuzz-submission.zip")
    )
    parser.add_argument(
        "--manifest-output",
        type=Path,
        default=Path("dist/submission-manifest.json"),
    )
    parser.add_argument(
        "--check-only",
        action="store_true",
        help="run every preflight without writing an archive or manifest",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        result = package_submission(
            package_root=args.package_root,
            output=args.output,
            manifest_output=args.manifest_output,
            tag=args.tag,
            check_only=args.check_only,
        )
    except PackageValidationError as exc:
        print("FAIL submission package preflight")
        for error in str(exc).splitlines():
            print(f"- {error}")
        return 1
    if args.check_only:
        print(
            f"PASS submission package preflight: {len(result.members)} members, "
            f"{result.total_bytes} bytes, tag {result.tag} at {result.commit}"
        )
    else:
        print(
            f"PASS deterministic submission package: {args.output} "
            f"({result.archive_bytes} bytes, sha256 {result.archive_sha256})"
        )
        print(f"Manifest: {args.manifest_output}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
