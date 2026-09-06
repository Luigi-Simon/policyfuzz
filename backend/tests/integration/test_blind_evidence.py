"""Candidate binding uses public synthetic fixtures and a temporary local Git repo."""

import hashlib
import json
import shutil
import subprocess
from datetime import UTC, datetime
from pathlib import Path

import pytest
from scripts.blind_evidence import bind_first_run
from scripts.record_blind_run import RUNTIME_FIELDS, _preflight

from app.core.artifacts import complete_payload_projection
from app.core.hashing import canonical_sha256
from app.domain.models import RunRecord
from app.features.evaluation.gold_assessment import _ARTIFACT_MODELS

ROOT = Path(__file__).resolve().parents[3]
NOW = datetime(2026, 9, 7, tzinfo=UTC)


@pytest.fixture
def bound_packet(tmp_path):
    record = RunRecord.model_validate_json(
        (ROOT / "samples/cached-demo/run-record.json").read_bytes()
    )
    document = next(
        a.payload for a in record.artifacts if a.artifact_type == "policy_document"
    )
    policy = tmp_path / "samples/policies/blind-policy.txt"
    policy.parent.mkdir(parents=True)
    policy.write_text("".join(page.text for page in document.pages))
    directory = tmp_path / "samples/benchmarks/blind"
    shutil.copytree(ROOT / "samples/benchmarks/development", directory)

    def write(name, value):
        path = tmp_path / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(value, sort_keys=True) + "\n")
        return hashlib.sha256(path.read_bytes()).hexdigest()

    artifacts = {
        name: model.model_validate_json((directory / name).read_bytes())
        for name, model in _ARTIFACT_MODELS.items()
    }
    defect_ids = canonical_sha256(
        sorted(d.defect_id for d in artifacts["defect-manifest.json"].defects)
    )
    source_name = "submission/evidence/benchmark-v2/blind-seal.json"
    schema_name = "submission/evidence/benchmark-v2/blind-schema-seal.json"
    provenance_name = "submission/evidence/benchmark-v2/provenance.json"
    approval_name = "submission/evidence/approval.json"
    active_name = "submission/evidence/active-benchmark.json"
    moment = "2026-09-06T00:00:00Z"
    binding = {
        "candidate_version": 2,
        "source_policy_sha256": document.document_sha256,
        "schema_archive_sha256": "a" * 64,
    }
    write(
        source_name,
        {
            "policy_sha256": document.document_sha256,
            "archive_sha256": "b" * 64,
            "manifest_sha256": "c" * 64,
            "defect_ids_sha256": defect_ids,
            "defect_count": 3,
            "created_at": moment,
        },
    )
    write(
        schema_name,
        {
            "schema_version": "1.0",
            "source_policy_sha256": document.document_sha256,
            "archive_sha256": "a" * 64,
            "defect_ids_sha256": defect_ids,
            "defect_count": 3,
            "scenario_count": 15,
            "rule_count": 10,
            "created_at": moment,
            "artifact_hashes": {
                name: canonical_sha256(complete_payload_projection(value))
                for name, value in artifacts.items()
            },
        },
    )
    write(
        provenance_name,
        {
            **binding,
            "source_archive_sha256": "b" * 64,
            "defect_ids_sha256": defect_ids,
            "independent_human_review": "pending",
            "headline_gold_scoring_eligible": False,
            "created_at": moment,
        },
    )
    approval_hash = write(
        approval_name,
        {
            **binding,
            "reviewer_type": "human",
            "reviewer_id": "synthetic-test-approval",
            "decision": "approve",
            "timestamp": moment,
        },
    )
    active = {
        **binding,
        "schema_version": "1.0",
        "source_seal": source_name,
        "schema_seal": schema_name,
        "provenance": provenance_name,
        "defect_ids_sha256": defect_ids,
        "human_review": "approved",
        "headline_gold_scoring_eligible": True,
        "approval_evidence": {"path": approval_name, "sha256": approval_hash},
    }
    write(active_name, active)
    _, _, inputs = _preflight(
        tmp_path,
        policy,
        tmp_path / source_name,
        tmp_path / schema_name,
        tmp_path / active_name,
        record.manifest.started_at,
    )

    def git(*args):
        return (
            subprocess.check_output(
                ("git", *args), cwd=tmp_path, stderr=subprocess.DEVNULL
            )
            .decode()
            .strip()
        )

    git("init", "-q")
    git("add", ".")
    identity = (
        "-c",
        "user.name=PolicyFuzz synthetic tests",
        "-c",
        "user.email=tests@example.invalid",
    )
    git(*identity, "commit", "-qm", "Synthetic test fixture")
    git(*identity, "tag", "-a", "blind-candidate-test", "-m", "Synthetic test tag")
    values = record.manifest.model_dump(mode="json")
    metadata = {
        "schema_version": "1.0",
        "status": "recorded",
        "error_code": None,
        "run_id": record.run_id,
        "stage": record.stage,
        "candidate": binding,
        "started_at": moment,
        "completed_at": "2026-09-06T00:01:00Z",
        "result_sha256": canonical_sha256(complete_payload_projection(record)),
        "runtime": {key: values[key] for key in RUNTIME_FIELDS},
        "input_bytes_sha256": inputs,
        "tag": "blind-candidate-test",
        "tag_object": git("rev-parse", "refs/tags/blind-candidate-test"),
        "commit": git("rev-parse", "HEAD"),
        "tree": git("rev-parse", "HEAD^{tree}"),
    }
    return tmp_path, active, record, metadata


def test_binds_actual_document_sealed_members_runtime_and_annotated_tag(bound_packet):
    paths = bind_first_run(*bound_packet, now=NOW)
    assert len(paths) == 13
    assert "samples/benchmarks/blind/defect-manifest.json" in paths


@pytest.mark.parametrize(
    "kind",
    [
        "missing_document",
        "wrong_source",
        "substituted_labels",
        "missing_audit",
        "wrong_runtime",
        "wrong_tag",
    ],
)
def test_rejects_unbound_first_run_evidence(bound_packet, kind):
    root, active, record, metadata = bound_packet
    if kind == "missing_document":
        record = record.model_copy(
            update={
                "artifacts": tuple(
                    a for a in record.artifacts if a.artifact_type != "policy_document"
                )
            }
        )
        metadata["result_sha256"] = canonical_sha256(
            complete_payload_projection(record)
        )
    elif kind == "wrong_source":
        documents = []
        for artifact in record.artifacts:
            if artifact.artifact_type == "policy_document":
                artifact = artifact.model_copy(
                    update={
                        "payload": artifact.payload.model_copy(
                            update={"document_sha256": "f" * 64}
                        )
                    }
                )
            documents.append(artifact)
        record = record.model_copy(update={"artifacts": tuple(documents)})
        metadata["result_sha256"] = canonical_sha256(
            complete_payload_projection(record)
        )
    elif kind == "substituted_labels":
        path = root / "samples/benchmarks/blind/defect-manifest.json"
        value = json.loads(path.read_bytes())
        value["defects"][0]["expected_finding_fingerprint_sha256"] = "f" * 64
        path.write_text(json.dumps(value))
    elif kind == "missing_audit":
        metadata.pop("runtime")
    elif kind == "wrong_runtime":
        metadata["runtime"]["engine_sha256"] = "f" * 64
    else:
        metadata["tag_object"] = "f" * 40
    with pytest.raises(ValueError):
        bind_first_run(root, active, record, metadata, now=NOW)
