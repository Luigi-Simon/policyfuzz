from __future__ import annotations

import hashlib
import importlib.util
import json
import subprocess
from pathlib import Path
from types import ModuleType, SimpleNamespace
from typing import Any

import pytest

REPOSITORY_ROOT = Path(__file__).parents[2]
VERIFIER_PATH = REPOSITORY_ROOT / "scripts" / "verify_submission.py"
REQUIRED_KEYS = (
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
PROVENANCE = {
    "data_type": "synthetic",
    "run_mode": "live",
    "verification_status": "verified",
    "blind_eligibility": "eligible",
}
RATE_KEYS = {
    "development_seeded_defect_recall",
    "development_regression_pass_rate",
    "control_regression_pass_rate",
    "blind_seeded_defect_recall",
}


def load_verifier() -> ModuleType:
    assert VERIFIER_PATH.exists(), "submission verifier has not been implemented"
    spec = importlib.util.spec_from_file_location("verify_submission", VERIFIER_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class FakeRunner:
    def __init__(
        self,
        *,
        pages: str = "Pages:           9\n",
        deck_text: str = (
            "Measured development seeded-defect recall "
            "[[metric:development_seeded_defect_recall|50%|synthetic|live|"
            "verified|blind-eligible]]"
        ),
        probe: dict[str, Any] | None = None,
        failures: dict[str, int] | None = None,
    ) -> None:
        self.pages = pages
        self.deck_text = deck_text
        self.probe = probe or {
            "format": {"duration": "280.0"},
            "streams": [
                {"index": 0, "codec_type": "video", "codec_name": "h264"},
                {"index": 1, "codec_type": "audio", "codec_name": "aac"},
            ],
        }
        self.failures = failures or {}
        self.calls: list[list[str]] = []

    def __call__(self, args: list[str], **_: Any) -> SimpleNamespace:
        self.calls.append(args)
        tool = Path(args[0]).name
        returncode = self.failures.get(tool, 0)
        if tool == "pdfinfo":
            stdout = self.pages
        elif tool == "pdftotext":
            stdout = self.deck_text
        elif tool == "ffprobe":
            stdout = json.dumps(self.probe)
        elif tool == "ffmpeg":
            stdout = ""
        else:  # pragma: no cover - catches an accidental new external dependency
            raise AssertionError(f"unexpected command: {args}")
        return SimpleNamespace(returncode=returncode, stdout=stdout, stderr="failed")


@pytest.fixture
def candidate(tmp_path: Path) -> dict[str, Any]:
    deck = tmp_path / "PolicyFuzz-Pitch.pdf"
    video = tmp_path / "PolicyFuzz-Demo.mp4"
    script = tmp_path / "submission" / "video" / "script.md"
    artifact = tmp_path / "gate-b.json"
    evidence = tmp_path / "verified-metrics.json"
    script.parent.mkdir(parents=True)
    deck.write_bytes(b"%PDF-1.4 synthetic fixture")
    video.write_bytes(b"synthetic video fixture")
    script.write_text(
        "Measured development seeded-defect recall "
        "[[metric:development_seeded_defect_recall|50%|synthetic|live|verified|"
        "blind-eligible]]\n",
        encoding="utf-8",
    )
    artifact.write_text('{"result":"fixture"}\n', encoding="utf-8")
    artifact_hash = hashlib.sha256(artifact.read_bytes()).hexdigest()
    metrics: dict[str, Any] = {}
    for key in REQUIRED_KEYS:
        if key in RATE_KEYS:
            arithmetic = {"numerator": 1, "denominator": 2, "basis_points": 5000}
            display_value = "50%"
        elif key == "provider_cost_usd":
            arithmetic = {
                "numerator": "not_applicable",
                "denominator": "not_applicable",
                "basis_points": "not_applicable",
            }
            display_value = "N/A"
        else:
            arithmetic = {
                "numerator": 1,
                "denominator": "not_applicable",
                "basis_points": "not_applicable",
            }
            display_value = "1"
        metrics[key] = {
            "status": "verified",
            "display_value": display_value,
            **arithmetic,
            "source_artifact": "gate_b",
            "frozen_commit": "1" * 40,
            "suite_hash": "2" * 64,
            "engine_version": "policyfuzz-evaluator-v1",
            "provenance": dict(PROVENANCE),
        }
    payload = {
        "schema_version": "1.0",
        "status": "final",
        "scoring_eligible": True,
        "frozen_commit": "1" * 40,
        "suite_hash": "2" * 64,
        "engine_version": "policyfuzz-evaluator-v1",
        "required_metrics": list(REQUIRED_KEYS),
        "provenance": dict(PROVENANCE),
        "claim_sources": [
            {
                "path": "submission/video/script.md",
                "provenance": dict(PROVENANCE),
            }
        ],
        "source_artifacts": {
            "gate_b": {"path": "gate-b.json", "sha256": artifact_hash}
        },
        "metrics": metrics,
    }
    evidence.write_text(json.dumps(payload), encoding="utf-8")
    return {
        "root": tmp_path,
        "deck": deck,
        "video": video,
        "script": script,
        "artifact": artifact,
        "evidence": evidence,
        "payload": payload,
    }


def verify(candidate: dict[str, Any], **overrides: Any) -> list[str]:
    verifier = load_verifier()
    arguments = {
        "deck": candidate["deck"],
        "video": candidate["video"],
        "evidence": candidate["evidence"],
        "package_root": candidate["root"],
        "sources": [],
        "runner": FakeRunner(),
    }
    arguments.update(overrides)
    return verifier.verify_submission(**arguments)


def rewrite_evidence(candidate: dict[str, Any]) -> None:
    candidate["evidence"].write_text(json.dumps(candidate["payload"]), encoding="utf-8")


def test_valid_candidate_passes_all_checks(candidate: dict[str, Any]) -> None:
    assert verify(candidate) == []


def test_reports_malformed_ffprobe_response(candidate: dict[str, Any]) -> None:
    errors = verify(candidate, runner=FakeRunner(probe={"streams": []}))

    assert any("video stream" in error for error in errors)
    assert any("duration" in error for error in errors)


def test_reports_external_tool_failure(candidate: dict[str, Any]) -> None:
    errors = verify(candidate, runner=FakeRunner(failures={"pdfinfo": 1}))

    assert any("pdfinfo failed" in error for error in errors)


def test_reports_external_tool_timeout(candidate: dict[str, Any]) -> None:
    def timed_out(args: list[str], **_: Any) -> Any:
        raise subprocess.TimeoutExpired(args, timeout=1)

    errors = verify(candidate, runner=timed_out)

    assert any("timed out" in error for error in errors)


def test_rejects_tampered_source_artifact(candidate: dict[str, Any]) -> None:
    candidate["artifact"].write_text("tampered\n", encoding="utf-8")

    errors = verify(candidate)

    assert any("hash mismatch" in error for error in errors)


def test_rejects_unresolved_metric_placeholder(candidate: dict[str, Any]) -> None:
    runner = FakeRunner(
        deck_text="Measured coverage: {{metric:development_seeded_defect_recall}}"
    )

    errors = verify(candidate, runner=runner)

    assert any("unresolved metric placeholder" in error for error in errors)


def test_rejects_opaque_unreferenced_measured_number(candidate: dict[str, Any]) -> None:
    runner = FakeRunner(deck_text="Synthetic live blind measured coverage is 50%.")

    errors = verify(candidate, runner=runner)

    assert any("measured value is not bound" in error for error in errors)


def test_ignores_ordinary_structural_numbers(candidate: dict[str, Any]) -> None:
    runner = FakeRunner(
        deck_text=(
            "Slide 7 of 9. Target duration 280 seconds. Synthetic live blind evidence."
        )
    )

    assert verify(candidate, runner=runner) == []


def test_ignores_segment_timecodes_near_descriptive_defect_text(
    candidate: dict[str, Any],
) -> None:
    candidate["script"].write_text(
        "## 2:25–2:50 — Measured coverage and one targeted cycle\n"
        "Synthetic live blind evidence.\n",
        encoding="utf-8",
    )

    assert verify(candidate) == []


def test_rejects_zero_denominator(candidate: dict[str, Any]) -> None:
    candidate["payload"]["metrics"]["development_seeded_defect_recall"][
        "denominator"
    ] = 0
    rewrite_evidence(candidate)

    errors = verify(candidate)

    assert any("denominator must be greater than zero" in error for error in errors)


def test_rejects_boilerplate_labels_when_claim_mode_is_wrong(
    candidate: dict[str, Any],
) -> None:
    runner = FakeRunner(
        deck_text=(
            "Labels: synthetic live cached blind unverified verified eligible.\n"
            "Measured coverage [[metric:development_seeded_defect_recall|50%|"
            "synthetic|cached|verified|blind-eligible]]"
        )
    )

    errors = verify(candidate, runner=runner)

    assert any("claim provenance run_mode does not match" in error for error in errors)


def test_rejects_source_path_escape(candidate: dict[str, Any], tmp_path: Path) -> None:
    outside = tmp_path.parent / "outside-evidence.json"
    outside.write_text("outside\n", encoding="utf-8")
    candidate["payload"]["source_artifacts"]["gate_b"] = {
        "path": "../outside-evidence.json",
        "sha256": hashlib.sha256(outside.read_bytes()).hexdigest(),
    }
    rewrite_evidence(candidate)

    errors = verify(candidate)

    assert any("escapes package root" in error for error in errors)


def test_rejects_source_symlink_escape(
    candidate: dict[str, Any], tmp_path: Path
) -> None:
    outside = tmp_path.parent / "outside-target.json"
    outside.write_text("outside\n", encoding="utf-8")
    link = candidate["root"] / "linked-evidence.json"
    link.symlink_to(outside)
    candidate["payload"]["source_artifacts"]["gate_b"] = {
        "path": "linked-evidence.json",
        "sha256": hashlib.sha256(outside.read_bytes()).hexdigest(),
    }
    rewrite_evidence(candidate)

    errors = verify(candidate)

    assert any("escapes package root" in error for error in errors)


def test_rejects_private_source_path(candidate: dict[str, Any]) -> None:
    private_dir = candidate["root"] / "privatebench"
    private_dir.mkdir()
    private_file = private_dir / "result.json"
    private_file.write_text("private\n", encoding="utf-8")
    candidate["payload"]["source_artifacts"]["gate_b"] = {
        "path": "privatebench/result.json",
        "sha256": hashlib.sha256(private_file.read_bytes()).hexdigest(),
    }
    rewrite_evidence(candidate)

    errors = verify(candidate)

    assert any("prohibited private path" in error for error in errors)


def test_rejects_unlisted_file_at_candidate_size_limit(
    candidate: dict[str, Any],
) -> None:
    unlisted = candidate["root"] / "unlisted-large.bin"
    with unlisted.open("wb") as handle:
        handle.truncate(5_000_000_000)

    errors = verify(candidate)

    assert any("must be below 5000000000 bytes" in error for error in errors)


def test_rejects_duplicate_candidate_filenames(candidate: dict[str, Any]) -> None:
    duplicate = candidate["root"] / "archive" / candidate["deck"].name
    duplicate.parent.mkdir()
    duplicate.write_bytes(b"duplicate final deck")

    errors = verify(candidate)

    assert any(
        f"duplicate final deliverable filename '{candidate['deck'].name}'" in error
        for error in errors
    )


def test_rejects_draft_and_pending_evidence(candidate: dict[str, Any]) -> None:
    candidate["payload"]["status"] = "draft"
    candidate["payload"]["scoring_eligible"] = False
    candidate["payload"]["metrics"]["development_seeded_defect_recall"]["status"] = (
        "pending"
    )
    rewrite_evidence(candidate)

    errors = verify(candidate)

    assert any("evidence status must be final" in error for error in errors)
    assert any("scoring_eligible must be true" in error for error in errors)
    assert any(
        "required metric 'development_seeded_defect_recall' is pending" in error
        for error in errors
    )


def test_rejects_frozen_metadata_mismatch(candidate: dict[str, Any]) -> None:
    candidate["payload"]["metrics"]["development_seeded_defect_recall"][
        "suite_hash"
    ] = "3" * 64
    rewrite_evidence(candidate)

    errors = verify(candidate)

    assert any("suite_hash does not match frozen metadata" in error for error in errors)


def test_rejects_claim_key_outside_required_metric_contract(
    candidate: dict[str, Any],
) -> None:
    candidate["payload"]["metrics"]["rogue"] = {"status": "verified"}
    rewrite_evidence(candidate)
    runner = FakeRunner(
        deck_text=(
            "Measured coverage [[metric:rogue|50%|synthetic|live|verified|"
            "blind-eligible]]"
        )
    )

    errors = verify(candidate, runner=runner)

    assert any(
        "metric reference 'rogue' has no evidence entry" in error for error in errors
    )


def test_rejects_fractional_metric_arithmetic_fields(candidate: dict[str, Any]) -> None:
    metric = candidate["payload"]["metrics"]["development_seeded_defect_recall"]
    metric["numerator"] = 0.5
    metric["denominator"] = 1
    metric["basis_points"] = 5000
    rewrite_evidence(candidate)

    errors = verify(candidate)

    assert any("must use integer arithmetic" in error for error in errors)


def test_rejects_empty_final_contract_and_blank_deck(candidate: dict[str, Any]) -> None:
    candidate["payload"]["required_metrics"] = []
    candidate["payload"]["metrics"] = {}
    candidate["payload"]["claim_sources"] = []
    rewrite_evidence(candidate)

    errors = verify(candidate, runner=FakeRunner(deck_text=""))

    assert any(
        "required_metrics must contain the fixed Task 24 keys" in error
        for error in errors
    )
    assert any("final script claim source is required" in error for error in errors)
    assert any("deck text is empty" in error for error in errors)


def test_rejects_duplicate_required_metric_key(candidate: dict[str, Any]) -> None:
    candidate["payload"]["required_metrics"].append(REQUIRED_KEYS[0])
    rewrite_evidence(candidate)

    errors = verify(candidate)

    assert any("required_metrics contains duplicates" in error for error in errors)


def test_requires_default_final_script_even_with_explicit_source(
    candidate: dict[str, Any],
) -> None:
    candidate["payload"]["claim_sources"] = []
    rewrite_evidence(candidate)

    errors = verify(candidate, sources=[candidate["script"]])

    assert any("final script claim source is required" in error for error in errors)


def test_rejects_empty_extracted_deck_text(candidate: dict[str, Any]) -> None:
    errors = verify(candidate, runner=FakeRunner(deck_text=" \n\f\n"))

    assert any("deck text is empty" in error for error in errors)


def test_rejects_claim_display_that_disagrees_with_metric(
    candidate: dict[str, Any],
) -> None:
    runner = FakeRunner(
        deck_text=(
            "Measured coverage [[metric:development_seeded_defect_recall|99%|"
            "synthetic|live|verified|blind-eligible]]"
        )
    )

    errors = verify(candidate, runner=runner)

    assert any(
        "claim display '99%' does not match evidence '50%'" in error for error in errors
    )


def test_rejects_unbound_number_beside_canonical_claim(
    candidate: dict[str, Any],
) -> None:
    runner = FakeRunner(
        deck_text=(
            "Measured coverage 99% "
            "[[metric:development_seeded_defect_recall|50%|synthetic|live|"
            "verified|blind-eligible]]"
        )
    )

    errors = verify(candidate, runner=runner)

    assert any(
        "measured value is not bound by a canonical metric claim" in error
        for error in errors
    )


def test_rejects_unrelated_visible_number_beside_canonical_claim(
    candidate: dict[str, Any],
) -> None:
    runner = FakeRunner(
        deck_text=(
            "Found 99 defects alongside "
            "[[metric:scenario_count|1|synthetic|live|verified|blind-eligible]]"
        )
    )

    errors = verify(candidate, runner=runner)

    assert any(
        "measured value is not bound by a canonical metric claim" in error
        for error in errors
    )


def test_rejects_missing_display_value(candidate: dict[str, Any]) -> None:
    del candidate["payload"]["metrics"]["development_seeded_defect_recall"][
        "display_value"
    ]
    rewrite_evidence(candidate)

    errors = verify(candidate)

    assert any("display_value is required" in error for error in errors)


def test_rejects_na_display_with_numeric_arithmetic(candidate: dict[str, Any]) -> None:
    candidate["payload"]["metrics"]["development_seeded_defect_recall"][
        "display_value"
    ] = "N/A"
    rewrite_evidence(candidate)

    errors = verify(candidate)

    assert any(
        "display_value 'N/A' does not match arithmetic '50%'" in error
        for error in errors
    )


@pytest.mark.parametrize(
    ("field", "claim_fragment"),
    [
        ("data_type", "observed|live|verified|blind-eligible"),
        ("run_mode", "synthetic|cached|verified|blind-eligible"),
        ("verification_status", "synthetic|live|unverified|blind-eligible"),
        ("blind_eligibility", "synthetic|live|verified|blind-ineligible"),
    ],
)
def test_rejects_claim_provenance_mismatch_despite_boilerplate_labels(
    candidate: dict[str, Any], field: str, claim_fragment: str
) -> None:
    runner = FakeRunner(
        deck_text=(
            "Boilerplate: synthetic observed live cached verified unverified "
            "blind eligible ineligible.\n"
            "Measured coverage [[metric:development_seeded_defect_recall|50%|"
            f"{claim_fragment}]]"
        )
    )

    errors = verify(candidate, runner=runner)

    assert any(field in error and "claim provenance" in error for error in errors)


def test_rejects_claim_source_provenance_mismatch(candidate: dict[str, Any]) -> None:
    candidate["payload"]["claim_sources"][0]["provenance"]["run_mode"] = "cached"
    rewrite_evidence(candidate)

    errors = verify(candidate)

    assert any("claim source" in error and "run_mode" in error for error in errors)


def test_rejects_metric_provenance_mismatch(candidate: dict[str, Any]) -> None:
    candidate["payload"]["metrics"]["development_seeded_defect_recall"]["provenance"][
        "verification_status"
    ] = "unverified"
    rewrite_evidence(candidate)

    errors = verify(candidate)

    assert any(
        "metric 'development_seeded_defect_recall' provenance" in error
        for error in errors
    )


def test_rejects_legacy_or_extra_metric_label_fields(candidate: dict[str, Any]) -> None:
    candidate["payload"]["metrics"]["development_seeded_defect_recall"]["labels"] = [
        "synthetic",
        "cached",
    ]
    rewrite_evidence(candidate)

    errors = verify(candidate)

    assert any(
        "must contain exactly the metric contract fields" in error for error in errors
    )


def test_rejects_in_root_symlink_to_privatebench(candidate: dict[str, Any]) -> None:
    private_dir = candidate["root"] / "privatebench"
    private_dir.mkdir()
    private_file = private_dir / "result.json"
    private_file.write_text("private\n", encoding="utf-8")
    link = candidate["root"] / "innocent-result.json"
    link.symlink_to(private_file)
    candidate["payload"]["source_artifacts"]["gate_b"] = {
        "path": "innocent-result.json",
        "sha256": hashlib.sha256(private_file.read_bytes()).hexdigest(),
    }
    rewrite_evidence(candidate)

    errors = verify(candidate)

    assert any("resolves through prohibited private path" in error for error in errors)


def test_ffmpeg_decode_uses_unattended_fatal_error_flags(
    candidate: dict[str, Any],
) -> None:
    runner = FakeRunner()

    assert verify(candidate, runner=runner) == []
    ffmpeg_call = next(call for call in runner.calls if Path(call[0]).name == "ffmpeg")
    assert "-nostdin" in ffmpeg_call
    assert "-xerror" in ffmpeg_call


def test_allows_duplicate_ordinary_source_filenames(candidate: dict[str, Any]) -> None:
    first = candidate["root"] / "one" / "AGENTS.md"
    second = candidate["root"] / "two" / "AGENTS.md"
    first.parent.mkdir()
    second.parent.mkdir()
    first.write_text("one\n", encoding="utf-8")
    second.write_text("two\n", encoding="utf-8")

    assert verify(candidate) == []


def test_excludes_known_dependency_directory_from_candidate_size(
    candidate: dict[str, Any],
) -> None:
    dependency = candidate["root"] / "node_modules" / "huge.bin"
    dependency.parent.mkdir()
    with dependency.open("wb") as handle:
        handle.truncate(5_000_000_000)

    assert verify(candidate) == []


def test_exposes_deterministic_candidate_file_enumeration(
    candidate: dict[str, Any],
) -> None:
    ordinary = candidate["root"] / "ordinary.txt"
    root_template = candidate["root"] / ".env.example"
    nested_template = candidate["root"] / "frontend" / ".env.example"
    root_secret = candidate["root"] / ".env"
    nested_secret = candidate["root"] / "frontend" / ".env.local"
    generic_backup = candidate["root"] / "backup" / "payload.bin"
    dependency = candidate["root"] / "node_modules" / "ignored.bin"
    ordinary.write_text("ordinary\n", encoding="utf-8")
    root_template.write_text("SAFE_ROOT=value\n", encoding="utf-8")
    nested_template.parent.mkdir()
    nested_template.write_text("SAFE_NESTED=value\n", encoding="utf-8")
    root_secret.write_text("ROOT_SECRET=value\n", encoding="utf-8")
    nested_secret.write_text("NESTED_SECRET=value\n", encoding="utf-8")
    generic_backup.parent.mkdir()
    generic_backup.write_bytes(b"candidate payload")
    dependency.parent.mkdir()
    dependency.write_bytes(b"dependency")
    verifier = load_verifier()

    files, errors = verifier.enumerate_candidate_files(candidate["root"])

    assert errors == []
    assert files == tuple(sorted(files, key=lambda path: path.as_posix()))
    assert Path("ordinary.txt") in files
    assert Path(".env.example") in files
    assert Path("frontend/.env.example") in files
    assert Path(".env") not in files
    assert Path("frontend/.env.local") not in files
    assert Path("backup/payload.bin") in files
    assert Path("node_modules/ignored.bin") not in files


@pytest.mark.parametrize("directory_name", ["raw", "backup", "backups"])
def test_generic_named_directory_cannot_hide_oversized_payload(
    candidate: dict[str, Any], directory_name: str
) -> None:
    unlisted = candidate["root"] / directory_name / "unlisted-large.bin"
    unlisted.parent.mkdir()
    with unlisted.open("wb") as handle:
        handle.truncate(5_000_000_000)

    errors = verify(candidate)

    assert any("must be below 5000000000 bytes" in error for error in errors)


def test_rejects_symlink_in_candidate_directory(candidate: dict[str, Any]) -> None:
    target = candidate["root"] / "ordinary.txt"
    target.write_text("ordinary\n", encoding="utf-8")
    (candidate["root"] / "linked.txt").symlink_to(target)

    errors = verify(candidate)

    assert any("candidate contains symlink" in error for error in errors)


def test_ignores_huge_structural_slide_number(candidate: dict[str, Any]) -> None:
    runner = FakeRunner(deck_text=f"{'9' * 5000} Measured benchmark evidence")

    assert verify(candidate, runner=runner) == []


def test_huge_metric_integer_returns_bounded_error(candidate: dict[str, Any]) -> None:
    metric = candidate["payload"]["metrics"]["development_seeded_defect_recall"]
    metric["numerator"] = 10**1000
    metric["denominator"] = 10**1000
    metric["basis_points"] = 10_000
    metric["display_value"] = "100%"
    rewrite_evidence(candidate)

    errors = verify(candidate)

    assert any("exceeds numeric bound" in error for error in errors)
