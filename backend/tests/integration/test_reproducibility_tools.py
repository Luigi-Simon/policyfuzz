import hashlib
import json
import subprocess
from datetime import UTC, datetime
from pathlib import Path

import pytest
from scripts.run_gate_b import GateError, run_gate


def _runner(command, cwd):
    return subprocess.CompletedProcess(command, 0, "ok", "")


def _setup(tmp_path):
    def write(name, value):
        path = tmp_path / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(value))

    for name, counts in (
        ("development", (3, 0, 0)),
        ("corrected-control", (0, 0, 0)),
        ("blind", (2, 1, 1)),
    ):
        write(
            f"team/person-4-evaluation/evidence/{name}-score.json",
            dict(zip(("true_positives", "false_positives", "false_negatives"), counts)),
        )
        write(f"samples/benchmarks/{name}/defect-manifest.json", {})
    approval = {
        "reviewer_type": "human",
        "decision": "approve",
        "reviewer_id": "independent-reviewer",
        "timestamp": "2026-01-01T00:00:00+00:00",
        "candidate_version": 2,
        "source_policy_sha256": "a" * 64,
        "schema_archive_sha256": "b" * 64,
    }
    write("submission/evidence/benchmark-approval.json", approval)
    approval_hash = hashlib.sha256(
        (tmp_path / "submission/evidence/benchmark-approval.json").read_bytes()
    ).hexdigest()
    write(
        "submission/evidence/active-benchmark.json",
        {
            "headline_gold_scoring_eligible": True,
            "human_review": "approved",
            "candidate_version": 2,
            "source_policy_sha256": "a" * 64,
            "schema_archive_sha256": "b" * 64,
            "approval_evidence": {
                "path": "submission/evidence/benchmark-approval.json",
                "sha256": approval_hash,
            },
        },
    )
    write("team/person-1-integration/evidence/blind-first-run.json", {})
    write(
        "team/person-1-integration/evidence/blind-first-run.json.metadata.json",
        {"started_at": "2026-01-01T00:00:00Z"},
    )
    for person in ("1-integration", "4-evaluation"):
        raw = {
            "reviewer_type": "human",
            "independent": True,
            "reviewer_id": person,
            "duration_seconds": 600,
            "candidate_version": 2,
            "source_policy_sha256": "a" * 64,
            "started_at": "2025-12-31T23:40:00Z",
            "completed_at": "2025-12-31T23:50:00Z",
            "reported_issues": [],
            "first_reported_issue_seconds": None,
        }
        raw_name = f"team/person-{person}/evidence/manual-review.raw.json"
        write(raw_name, raw)
        wrapper = {key: value for key, value in raw.items() if key != "reported_issues"}
        wrapper.update(
            external_file=raw_name,
            external_file_sha256=hashlib.sha256(
                (tmp_path / raw_name).read_bytes()
            ).hexdigest(),
        )
        write(f"team/person-{person}/evidence/manual-review.json", wrapper)
    return tmp_path / "report.json"


def test_gate_records_commands_commit_and_evidence(tmp_path):
    output = _setup(tmp_path)
    report = run_gate(
        tmp_path,
        output,
        runner=_runner,
        snapshot=lambda: ("a" * 40, ""),
        now=lambda: datetime(2026, 1, 1, tzinfo=UTC),
    )
    assert report["status"] == "passed"
    assert len(report["commands"]) == 11
    assert all(row["exit_code"] == 0 for row in report["commands"])
    assert report["commit"] == "a" * 40
    assert report["artifact_hashes"]
    assert json.loads(output.read_text()) == report


@pytest.mark.parametrize(
    "dirty,fail,drift",
    [(True, False, False), (False, True, False), (False, False, True)],
)
def test_gate_refuses_dirty_failure_or_drift(tmp_path, dirty, fail, drift):
    output = _setup(tmp_path)
    calls = 0

    def snapshot():
        nonlocal calls
        calls += 1
        return ("a" * 40, " M tracked" if dirty or (drift and calls > 1) else "")

    def runner(command, cwd):
        return subprocess.CompletedProcess(command, int(fail), "bounded output", "")

    with pytest.raises(GateError):
        run_gate(tmp_path, output, runner=runner, snapshot=snapshot)
    assert not output.exists()


def test_gate_refuses_missing_evidence_and_existing_output(tmp_path):
    output = tmp_path / "report.json"
    with pytest.raises(GateError):
        run_gate(tmp_path, output, runner=_runner, snapshot=lambda: ("a" * 40, ""))
    output.write_text("original")
    with pytest.raises(GateError):
        run_gate(tmp_path, output, runner=_runner, snapshot=lambda: ("a" * 40, ""))
    assert output.read_text() == "original"


def test_contract_validator_detects_drift_without_rewriting(tmp_path):
    import shutil

    from scripts.validate_contracts import ContractDriftError, validate_contracts

    root = Path(__file__).resolve().parents[3]
    target = tmp_path / "contracts"
    shutil.copytree(root / "contracts", target)
    validate_contracts(tmp_path)
    path = target / "openapi.json"
    path.write_text("{}")
    with pytest.raises(ContractDriftError):
        validate_contracts(tmp_path)
    assert path.read_text() == "{}"


@pytest.mark.parametrize(
    "kind", ["unapproved", "failed_blind", "same_reviewer", "short_review"]
)
def test_gate_refuses_unmet_benchmark_or_human_gates(tmp_path, kind):
    output = _setup(tmp_path)
    if kind == "unapproved":
        path = tmp_path / "submission/evidence/active-benchmark.json"
        data = json.loads(path.read_text())
        data["headline_gold_scoring_eligible"] = False
    elif kind == "failed_blind":
        path = tmp_path / "team/person-4-evaluation/evidence/blind-score.json"
        data = {"true_positives": 1, "false_positives": 2, "false_negatives": 2}
    else:
        path = tmp_path / "team/person-4-evaluation/evidence/manual-review.json"
        data = json.loads(path.read_text())
        if kind == "same_reviewer":
            data["reviewer_id"] = "1-integration"
        else:
            data["duration_seconds"] = 599
    path.write_text(json.dumps(data))
    with pytest.raises(GateError):
        run_gate(tmp_path, output, runner=_runner, snapshot=lambda: ("a" * 40, ""))
    assert not output.exists()


@pytest.mark.parametrize("kind", ["missing", "changed", "outside", "wrong_candidate"])
def test_gate_binds_human_approval_to_candidate(tmp_path, kind):
    output = _setup(tmp_path)
    active_path = tmp_path / "submission/evidence/active-benchmark.json"
    active = json.loads(active_path.read_text())
    if kind == "missing":
        active.pop("approval_evidence")
    elif kind == "changed":
        (tmp_path / active["approval_evidence"]["path"]).write_text("{}")
    elif kind == "outside":
        active["approval_evidence"]["path"] = "../outside.json"
    else:
        active["candidate_version"] = 3
    active_path.write_text(json.dumps(active))
    with pytest.raises(GateError):
        run_gate(tmp_path, output, runner=_runner, snapshot=lambda: ("a" * 40, ""))
    assert not output.exists()


def test_blind_verification_rejects_cached_record_as_first_run(tmp_path):
    from scripts.verify_benchmarks import verify_blind_score

    _setup(tmp_path)
    root = Path(__file__).resolve().parents[3]
    data = (root / "samples/cached-demo/run-record.json").read_bytes()
    raw = tmp_path / "team/person-1-integration/evidence/blind-first-run.json"
    raw.write_bytes(data)
    metadata = {
        "status": "recorded",
        "run_id": json.loads(data)["run_id"],
        "result_bytes_sha256": hashlib.sha256(data).hexdigest(),
        "candidate": {
            "candidate_version": 2,
            "source_policy_sha256": "a" * 64,
            "schema_archive_sha256": "b" * 64,
        },
    }
    raw.with_name(raw.name + ".metadata.json").write_text(json.dumps(metadata))
    with pytest.raises(ValueError, match="first recorded attempt"):
        verify_blind_score(tmp_path)


def test_public_benchmark_verifier_detects_changed_labels(tmp_path):
    import shutil

    from scripts.verify_benchmarks import verify_benchmarks

    root = Path(__file__).resolve().parents[3]
    shutil.copytree(root / "samples/benchmarks", tmp_path / "samples/benchmarks")
    shutil.copytree(
        root / "team/person-4-evaluation/evidence",
        tmp_path / "team/person-4-evaluation/evidence",
    )
    path = tmp_path / "samples/benchmarks/development/defect-manifest.json"
    data = json.loads(path.read_bytes())
    data["defects"][0]["expected_finding_fingerprint_sha256"] = "f" * 64
    path.write_text(json.dumps(data))
    with pytest.raises(ValueError, match="independent labels"):
        verify_benchmarks(tmp_path)
