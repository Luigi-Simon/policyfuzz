from __future__ import annotations

import hashlib
import json
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile

import pytest

from scripts.seal_blind_benchmark import CUSTODIAN_ROLE, create_seal_ledger

POLICY_SHA256 = "1" * 64
MANIFEST_SHA256 = "a" * 64
DEFECT_IDS = ["blind-gap-001", "blind-hotel-conflict-002", "blind-split-claim-003"]
CREATED_AT = datetime(2026, 9, 4, 12, 30, tzinfo=UTC)


def write_valid_inputs(base: Path) -> tuple[Path, Path, Path, Path]:
    archive = base / "policyfuzz-blind-private.zip"
    with ZipFile(archive, "w", compression=ZIP_DEFLATED) as bundle:
        bundle.writestr("private-policy.txt", "synthetic blind policy")

    policy_hash = base / "policy.sha256"
    policy_hash.write_text(f"{POLICY_SHA256}  blind-policy.txt\n", encoding="utf-8")
    manifest_hash = base / "manifest.sha256"
    manifest_hash.write_text(f"{MANIFEST_SHA256}\n", encoding="utf-8")
    defect_ids = base / "defect-ids.json"
    defect_ids.write_text(json.dumps(DEFECT_IDS), encoding="utf-8")
    return archive, policy_hash, manifest_hash, defect_ids


def seal(
    *,
    archive: Path,
    policy_hash: Path,
    manifest_hash: Path,
    defect_ids: Path,
    output: Path,
    repository_root: Path,
) -> dict[str, object]:
    return create_seal_ledger(
        archive=archive,
        policy_sha256_file=policy_hash,
        manifest_sha256_file=manifest_hash,
        defect_ids_file=defect_ids,
        output=output,
        repository_root=repository_root,
        created_at=CREATED_AT,
    )


def test_seals_external_archive_with_metadata_only(tmp_path: Path) -> None:
    repository_root = tmp_path / "repository"
    repository_root.mkdir()
    external = tmp_path / "custodian"
    external.mkdir()
    archive, policy_hash, manifest_hash, defect_ids = write_valid_inputs(external)
    output = repository_root / "submission" / "evidence" / "blind-seal.json"

    ledger = seal(
        archive=archive,
        policy_hash=policy_hash,
        manifest_hash=manifest_hash,
        defect_ids=defect_ids,
        output=output,
        repository_root=repository_root,
    )

    expected_id_bytes = json.dumps(DEFECT_IDS, separators=(",", ":")).encode()
    assert ledger == {
        "archive_sha256": hashlib.sha256(archive.read_bytes()).hexdigest(),
        "policy_sha256": POLICY_SHA256,
        "manifest_sha256": MANIFEST_SHA256,
        "defect_ids_sha256": hashlib.sha256(expected_id_bytes).hexdigest(),
        "defect_count": 3,
        "created_at": "2026-09-04T12:30:00Z",
        "custodian_role": CUSTODIAN_ROLE,
    }
    assert json.loads(output.read_text(encoding="utf-8")) == ledger


def test_hashes_archive_bytes_without_requiring_a_readable_zip(tmp_path: Path) -> None:
    repository_root = tmp_path / "repository"
    repository_root.mkdir()
    external = tmp_path / "custodian"
    external.mkdir()
    archive, policy_hash, manifest_hash, defect_ids = write_valid_inputs(external)
    archive.write_bytes(
        b"opaque archive bytes that are deliberately not a ZIP directory"
    )

    ledger = seal(
        archive=archive,
        policy_hash=policy_hash,
        manifest_hash=manifest_hash,
        defect_ids=defect_ids,
        output=repository_root / "seal.json",
        repository_root=repository_root,
    )

    assert ledger["archive_sha256"] == hashlib.sha256(archive.read_bytes()).hexdigest()


def test_rejects_archive_inside_repository(tmp_path: Path) -> None:
    repository_root = tmp_path / "repository"
    repository_root.mkdir()
    archive, policy_hash, manifest_hash, defect_ids = write_valid_inputs(
        repository_root
    )

    with pytest.raises(ValueError, match="outside the repository"):
        seal(
            archive=archive,
            policy_hash=policy_hash,
            manifest_hash=manifest_hash,
            defect_ids=defect_ids,
            output=repository_root / "seal.json",
            repository_root=repository_root,
        )


def test_rejects_external_archive_symlink_resolving_inside_repository(
    tmp_path: Path,
) -> None:
    repository_root = tmp_path / "repository"
    repository_root.mkdir()
    internal_archive, policy_hash, manifest_hash, defect_ids = write_valid_inputs(
        repository_root
    )
    external = tmp_path / "custodian"
    external.mkdir()
    archive_symlink = external / "policyfuzz-blind-private.zip"
    archive_symlink.symlink_to(internal_archive)
    output = repository_root / "seal.json"

    with pytest.raises(ValueError, match="outside the repository"):
        seal(
            archive=archive_symlink,
            policy_hash=policy_hash,
            manifest_hash=manifest_hash,
            defect_ids=defect_ids,
            output=output,
            repository_root=repository_root,
        )

    assert archive_symlink.is_symlink()
    assert not output.exists()


@pytest.mark.parametrize("hash_name", ["policy", "manifest"])
def test_rejects_malformed_supplied_hash(tmp_path: Path, hash_name: str) -> None:
    repository_root = tmp_path / "repository"
    repository_root.mkdir()
    external = tmp_path / "custodian"
    external.mkdir()
    archive, policy_hash, manifest_hash, defect_ids = write_valid_inputs(external)
    malformed_file = policy_hash if hash_name == "policy" else manifest_hash
    malformed_file.write_text("not-a-sha256\n", encoding="utf-8")

    with pytest.raises(ValueError, match=f"malformed {hash_name} SHA-256"):
        seal(
            archive=archive,
            policy_hash=policy_hash,
            manifest_hash=manifest_hash,
            defect_ids=defect_ids,
            output=repository_root / "seal.json",
            repository_root=repository_root,
        )


@pytest.mark.parametrize(
    ("ids", "message"),
    [
        (["defect-a", "defect-b"], "exactly three"),
        (["defect-b", "defect-a", "defect-c"], "sorted"),
        (["defect-a", "defect-a", "defect-c"], "unique"),
        (["defect-a", "Defect B", "defect-c"], "stable"),
        ({"defect-a": 1}, "JSON array"),
    ],
)
def test_rejects_invalid_defect_id_set(
    tmp_path: Path, ids: object, message: str
) -> None:
    repository_root = tmp_path / "repository"
    repository_root.mkdir()
    external = tmp_path / "custodian"
    external.mkdir()
    archive, policy_hash, manifest_hash, defect_ids = write_valid_inputs(external)
    defect_ids.write_text(json.dumps(ids), encoding="utf-8")

    with pytest.raises(ValueError, match=message):
        seal(
            archive=archive,
            policy_hash=policy_hash,
            manifest_hash=manifest_hash,
            defect_ids=defect_ids,
            output=repository_root / "seal.json",
            repository_root=repository_root,
        )


def test_refuses_to_overwrite_existing_ledger(tmp_path: Path) -> None:
    repository_root = tmp_path / "repository"
    repository_root.mkdir()
    external = tmp_path / "custodian"
    external.mkdir()
    archive, policy_hash, manifest_hash, defect_ids = write_valid_inputs(external)
    output = repository_root / "seal.json"
    output.write_text("preserve me\n", encoding="utf-8")

    with pytest.raises(FileExistsError, match="refusing to overwrite"):
        seal(
            archive=archive,
            policy_hash=policy_hash,
            manifest_hash=manifest_hash,
            defect_ids=defect_ids,
            output=output,
            repository_root=repository_root,
        )

    assert output.read_text(encoding="utf-8") == "preserve me\n"


def test_refuses_dangling_output_symlink_without_writing_target(tmp_path: Path) -> None:
    repository_root = tmp_path / "repository"
    repository_root.mkdir()
    external = tmp_path / "custodian"
    external.mkdir()
    archive, policy_hash, manifest_hash, defect_ids = write_valid_inputs(external)
    target = repository_root / "must-not-be-created.json"
    output = repository_root / "blind-seal.json"
    output.symlink_to(target)

    with pytest.raises(FileExistsError, match="refusing to overwrite"):
        seal(
            archive=archive,
            policy_hash=policy_hash,
            manifest_hash=manifest_hash,
            defect_ids=defect_ids,
            output=output,
            repository_root=repository_root,
        )

    assert output.is_symlink()
    assert output.readlink() == target
    assert not output.exists()
    assert not target.exists()


def test_gate_a1_command_accepts_the_complete_interface(tmp_path: Path) -> None:
    repository_root = Path(__file__).resolve().parents[3]
    external = tmp_path / "custodian"
    external.mkdir()
    archive, policy_hash, manifest_hash, defect_ids = write_valid_inputs(external)
    output = tmp_path / "evidence" / "blind-seal.json"

    completed = subprocess.run(
        [
            sys.executable,
            str(repository_root / "scripts" / "seal_blind_benchmark.py"),
            "--archive",
            str(archive),
            "--policy-sha256-file",
            str(policy_hash),
            "--manifest-sha256-file",
            str(manifest_hash),
            "--defect-ids-file",
            str(defect_ids),
            "--output",
            str(output),
        ],
        capture_output=True,
        check=False,
        text=True,
    )

    assert completed.returncode == 0, completed.stderr
    assert json.loads(output.read_text(encoding="utf-8"))["defect_count"] == 3
