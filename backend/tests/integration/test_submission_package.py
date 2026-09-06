from __future__ import annotations

import hashlib
import json
import subprocess
import sys
from pathlib import Path
from zipfile import ZipFile

import pytest
from scripts import package_submission
from scripts.verify_submission import enumerate_candidate_files

REQUIRED_FILES = {
    "README.md": b"# Synthetic submission\n",
    "submission/deck/PolicyFuzz-Pitch.pdf": b"synthetic pdf fixture\n",
    "submission/video/PolicyFuzz-Demo.mp4": b"synthetic video fixture\n",
    "submission/evidence/verified-metrics.json": b"{}\n",
}
PACKAGE_SCRIPT = Path(__file__).resolve().parents[3] / "scripts/package_submission.py"


def _git(repository: Path, *args: str) -> str:
    result = subprocess.run(
        ["git", *args],
        cwd=repository,
        check=True,
        capture_output=True,
        text=True,
    )
    return result.stdout.strip()


def _write(repository: Path, relative: str, content: bytes) -> None:
    path = repository / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content)


def _commit_and_tag(repository: Path, *, tag: str = "demo-v1") -> str:
    _git(repository, "add", ".")
    _git(repository, "commit", "-m", "test fixture")
    _git(repository, "tag", tag)
    return _git(repository, "rev-parse", "HEAD")


@pytest.fixture
def submission_repository(tmp_path: Path) -> tuple[Path, str]:
    repository = tmp_path / "repository"
    repository.mkdir()
    _git(repository, "init", "-q")
    _git(repository, "config", "user.name", "PolicyFuzz Test")
    _git(repository, "config", "user.email", "policyfuzz@example.invalid")

    for relative, content in REQUIRED_FILES.items():
        _write(repository, relative, content)
    _write(
        repository,
        ".gitignore",
        b".env\nnode_modules/\n.venv/\nbuild/\ndist/\nraw-video/\n",
    )
    openai_key_name = b"OPENAI_API_" + b"KEY"
    _write(
        repository,
        ".env.example",
        openai_key_name + b"=\nLLM_PROVIDER=openai\n",
    )
    _write(
        repository,
        "src/config.py",
        b"openai_api_key: SecretText | None = None\n"
        b"TEST_ENV = {'OPENAI_API_KEY': 'test-api-key'}\n",
    )
    _write(repository, "src/main.py", b"print('synthetic fixture')\n")
    _write(repository, "backup/notes.txt", b"ordinary included notes\n")
    _write(repository, ".env", b"ignored local setting\n")
    _write(repository, "frontend/node_modules/dependency.js", b"excluded\n")
    _write(repository, "backend/.venv/installed.txt", b"excluded\n")
    _write(repository, "frontend/build/app.js", b"excluded\n")
    _write(repository, "submission/raw-video/take.mp4", b"excluded\n")
    _write(repository, "submission/video/demo-backup.mov", b"excluded\n")
    return repository, _commit_and_tag(repository)


def test_package_is_deterministic_and_manifest_matches_exact_p5_candidates(
    submission_repository: tuple[Path, str], tmp_path: Path
) -> None:
    repository, commit = submission_repository
    first_archive = tmp_path / "first.zip"
    second_archive = tmp_path / "second.zip"
    first_manifest = tmp_path / "first-manifest.json"
    second_manifest = tmp_path / "second-manifest.json"

    package_submission.package_submission(
        package_root=repository,
        output=first_archive,
        manifest_output=first_manifest,
    )
    package_submission.package_submission(
        package_root=repository,
        output=second_archive,
        manifest_output=second_manifest,
    )

    candidates, errors = enumerate_candidate_files(repository)
    assert errors == []
    expected_names = [path.as_posix() for path in candidates]
    with ZipFile(first_archive) as archive:
        assert archive.namelist() == expected_names
        assert all(
            info.date_time == (1980, 1, 1, 0, 0, 0) for info in archive.infolist()
        )
        assert archive.testzip() is None
    assert first_archive.read_bytes() == second_archive.read_bytes()

    manifest = json.loads(first_manifest.read_text(encoding="utf-8"))
    assert manifest == json.loads(second_manifest.read_text(encoding="utf-8"))
    assert manifest["tag"] == "demo-v1"
    assert manifest["commit"] == commit
    assert [member["path"] for member in manifest["members"]] == expected_names
    assert (
        manifest["archive"]["sha256"]
        == hashlib.sha256(first_archive.read_bytes()).hexdigest()
    )
    expected_hashes = {
        name: hashlib.sha256((repository / name).read_bytes()).hexdigest()
        for name in expected_names
    }
    assert {
        member["path"]: member["sha256"] for member in manifest["members"]
    } == expected_hashes
    assert ".env.example" in expected_names
    assert "backup/notes.txt" in expected_names
    assert ".env" not in expected_names
    assert not any("node_modules" in name for name in expected_names)
    assert not any(".venv" in name for name in expected_names)
    assert not any("/build/" in f"/{name}/" for name in expected_names)
    assert not any("raw-video" in name for name in expected_names)
    assert not any("backup.mov" in name for name in expected_names)


@pytest.mark.parametrize("missing", sorted(REQUIRED_FILES))
def test_check_only_rejects_each_missing_official_deliverable_without_writing(
    tmp_path: Path, missing: str
) -> None:
    repository = tmp_path / "repository"
    repository.mkdir()
    _git(repository, "init", "-q")
    _git(repository, "config", "user.name", "PolicyFuzz Test")
    _git(repository, "config", "user.email", "policyfuzz@example.invalid")
    for relative, content in REQUIRED_FILES.items():
        if relative != missing:
            _write(repository, relative, content)
    _commit_and_tag(repository)
    output = tmp_path / "must-not-exist.zip"
    manifest = tmp_path / "must-not-exist.json"

    with pytest.raises(package_submission.PackageValidationError, match=missing):
        package_submission.package_submission(
            package_root=repository,
            output=output,
            manifest_output=manifest,
            check_only=True,
        )

    assert not output.exists()
    assert not manifest.exists()


def test_rejects_candidate_symlink(
    submission_repository: tuple[Path, str], tmp_path: Path
) -> None:
    repository, _ = submission_repository
    (repository / "linked-readme").symlink_to(repository / "README.md")

    with pytest.raises(package_submission.PackageValidationError, match="symlink"):
        package_submission.package_submission(
            package_root=repository,
            output=tmp_path / "submission.zip",
            manifest_output=tmp_path / "manifest.json",
            check_only=True,
        )


def test_rejects_committed_environment_file_even_though_p5_excludes_it(
    submission_repository: tuple[Path, str], tmp_path: Path
) -> None:
    repository, _ = submission_repository
    _write(repository, "config/.env.production", b"SYNTHETIC_ONLY=true\n")
    _git(repository, "add", "-f", "config/.env.production")
    _git(repository, "commit", "-m", "tracked environment file")
    _git(repository, "tag", "-f", "demo-v1")

    with pytest.raises(
        package_submission.PackageValidationError, match="tracked environment file"
    ):
        package_submission.package_submission(
            package_root=repository,
            output=tmp_path / "submission.zip",
            manifest_output=tmp_path / "manifest.json",
            check_only=True,
        )


def test_rejects_credential_shaped_content_without_echoing_value(
    submission_repository: tuple[Path, str], tmp_path: Path
) -> None:
    repository, _ = submission_repository
    credential_name = "OPENAI_API_" + "KEY"
    credential = "sk-" + "proj-" + "SYNTHETIC0123456789abcdef"
    _write(repository, "notes.txt", f"{credential_name}={credential}\n".encode())
    _git(repository, "add", "notes.txt")
    _git(repository, "commit", "-m", "credential fixture")
    _git(repository, "tag", "-f", "demo-v1")

    with pytest.raises(package_submission.PackageValidationError) as raised:
        package_submission.package_submission(
            package_root=repository,
            output=tmp_path / "submission.zip",
            manifest_output=tmp_path / "manifest.json",
            check_only=True,
        )

    assert "credential-shaped content" in str(raised.value)
    assert credential not in str(raised.value)


def test_rejects_populated_credential_that_only_contains_placeholder_text(
    submission_repository: tuple[Path, str], tmp_path: Path
) -> None:
    repository, _ = submission_repository
    credential_name = "DATABASE_" + "URL"
    credential = "postgresql://user:real" + "example" + "password@host/db"
    _write(repository, "database.conf", f"{credential_name}={credential}\n".encode())
    _git(repository, "add", "database.conf")
    _git(repository, "commit", "-m", "database credential fixture")
    _git(repository, "tag", "-f", "demo-v1")
    output = tmp_path / "submission.zip"
    manifest = tmp_path / "manifest.json"

    with pytest.raises(package_submission.PackageValidationError) as raised:
        package_submission.package_submission(
            package_root=repository,
            output=output,
            manifest_output=manifest,
        )

    assert "credential-shaped content" in str(raised.value)
    assert credential not in str(raised.value)
    assert not output.exists()
    assert not manifest.exists()


def test_manifest_staging_failure_preserves_existing_archive(
    submission_repository: tuple[Path, str], tmp_path: Path
) -> None:
    repository, _ = submission_repository
    output = tmp_path / "submission.zip"
    existing_archive = b"previous verified archive"
    output.write_bytes(existing_archive)
    blocked_parent = tmp_path / "not-a-directory"
    blocked_parent.write_text("blocks manifest parent creation", encoding="utf-8")
    manifest = blocked_parent / "manifest.json"

    with pytest.raises(OSError):
        package_submission.package_submission(
            package_root=repository,
            output=output,
            manifest_output=manifest,
        )

    assert output.read_bytes() == existing_archive
    assert not manifest.exists()


def test_manifest_publish_failure_preserves_existing_archive(
    submission_repository: tuple[Path, str], tmp_path: Path
) -> None:
    repository, _ = submission_repository
    output = tmp_path / "submission.zip"
    existing_archive = b"previous verified archive"
    output.write_bytes(existing_archive)
    manifest = tmp_path / "manifest-target"
    manifest.mkdir()

    with pytest.raises(OSError):
        package_submission.package_submission(
            package_root=repository,
            output=output,
            manifest_output=manifest,
        )

    assert output.read_bytes() == existing_archive
    assert manifest.is_dir()


def test_rejects_candidate_at_size_limit(
    submission_repository: tuple[Path, str],
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repository, _ = submission_repository
    candidate_size = sum(
        (repository / relative).stat().st_size
        for relative in enumerate_candidate_files(repository)[0]
    )
    monkeypatch.setattr(package_submission, "MAX_PACKAGE_BYTES", candidate_size)

    with pytest.raises(
        package_submission.PackageValidationError, match="must be below"
    ):
        package_submission.package_submission(
            package_root=repository,
            output=tmp_path / "submission.zip",
            manifest_output=tmp_path / "manifest.json",
            check_only=True,
        )


def test_rejects_when_tag_does_not_point_to_head(
    submission_repository: tuple[Path, str], tmp_path: Path
) -> None:
    repository, _ = submission_repository
    _write(repository, "later.txt", b"later commit\n")
    _git(repository, "add", "later.txt")
    _git(repository, "commit", "-m", "commit after tag")

    with pytest.raises(
        package_submission.PackageValidationError, match="does not match HEAD"
    ):
        package_submission.package_submission(
            package_root=repository,
            output=tmp_path / "submission.zip",
            manifest_output=tmp_path / "manifest.json",
            check_only=True,
        )


def test_rejects_dirty_repository(
    submission_repository: tuple[Path, str], tmp_path: Path
) -> None:
    repository, _ = submission_repository
    _write(repository, "README.md", b"dirty\n")

    with pytest.raises(
        package_submission.PackageValidationError, match="working tree is not clean"
    ):
        package_submission.package_submission(
            package_root=repository,
            output=tmp_path / "submission.zip",
            manifest_output=tmp_path / "manifest.json",
            check_only=True,
        )


def test_cli_check_only_uses_default_final_tag_and_writes_nothing(
    submission_repository: tuple[Path, str],
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    repository, _ = submission_repository
    output = tmp_path / "submission.zip"
    manifest = tmp_path / "manifest.json"

    exit_code = package_submission.main(
        [
            "--package-root",
            str(repository),
            "--output",
            str(output),
            "--manifest-output",
            str(manifest),
            "--check-only",
        ]
    )

    assert exit_code == 0
    assert "PASS submission package preflight" in capsys.readouterr().out
    assert not output.exists()
    assert not manifest.exists()


def test_script_entry_point_runs_from_outside_repository(
    submission_repository: tuple[Path, str], tmp_path: Path
) -> None:
    repository, _ = submission_repository
    output = tmp_path / "submission.zip"
    manifest = tmp_path / "manifest.json"

    result = subprocess.run(
        [
            sys.executable,
            str(PACKAGE_SCRIPT),
            "--package-root",
            str(repository),
            "--output",
            str(output),
            "--manifest-output",
            str(manifest),
            "--check-only",
        ],
        cwd=tmp_path,
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0, result.stderr
    assert "PASS submission package preflight" in result.stdout
    assert not output.exists()
    assert not manifest.exists()
