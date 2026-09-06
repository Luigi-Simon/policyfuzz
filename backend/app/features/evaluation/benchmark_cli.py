"""CLI for deterministic, exclusive-write benchmark scoring."""

from __future__ import annotations

import argparse
import json
import os
import sys
import tempfile
from collections.abc import Sequence
from pathlib import Path

from app.core.artifacts import validate_artifact_envelope
from app.domain.models import (
    BenchmarkManifest,
    EvaluationReport,
    FindingReport,
    PolicyIR,
    RunRecord,
    ScoreBenchmarkRequest,
)
from app.features.evaluation.benchmark import score_benchmark
from app.features.evaluation.engine import payload_hash


def _validate_json(model, value):
    return model.model_validate_json(json.dumps(value))


def _read_json(path: Path) -> object:
    if path.is_symlink():
        raise ValueError("input path must not be a symlink")
    resolved = path.resolve(strict=True)
    if not resolved.is_file():
        raise ValueError("input path must be a regular file")
    return json.loads(resolved.read_text(encoding="utf-8"))


def _select_record_evidence(
    value: object, manifest: BenchmarkManifest
) -> tuple[EvaluationReport, FindingReport]:
    record = _validate_json(RunRecord, value)
    known_hashes: set[str] = set()
    indexed = []
    for index, raw in enumerate(record.artifacts):
        envelope = validate_artifact_envelope(raw)
        if (
            envelope.run_manifest_id != record.manifest.manifest_id
            or not set(envelope.parent_hashes) <= known_hashes
        ):
            raise ValueError("run result artifact graph is inconsistent")
        known_hashes.add(envelope.artifact_sha256)
        indexed.append((index, envelope))

    baselines = [
        (index, envelope)
        for index, envelope in indexed
        if envelope.artifact_type == "policy_ir"
        and isinstance(envelope.payload, PolicyIR)
        and envelope.payload.kind == "compiled_baseline"
        and envelope.payload.review_status == "session_confirmed"
    ]
    if len(baselines) != 1:
        raise ValueError("run result requires exactly one session-confirmed baseline")
    _, baseline = baselines[0]
    if baseline.payload.document_sha256 != manifest.document_sha256:
        raise ValueError("HASH_MISMATCH: benchmark document")

    evaluations = [
        (index, envelope)
        for index, envelope in indexed
        if envelope.artifact_type == "evaluation_report"
        and isinstance(envelope.payload, EvaluationReport)
        and envelope.payload.inputs.policy_sha256 == baseline.artifact_sha256
    ]
    if len(evaluations) != 1:
        raise ValueError("run result requires one authoritative baseline evaluation")
    evaluation_index, evaluation_envelope = evaluations[0]
    evaluation = evaluation_envelope.payload
    if (
        evaluation.inputs.engine_sha256 != record.manifest.engine_sha256
        or evaluation.inputs.run_manifest_sha256 != payload_hash(record.manifest)
        or evaluation.engine_version != record.manifest.engine_version
    ):
        raise ValueError("HASH_MISMATCH: run manifest and evaluation")
    referenced = {
        envelope.artifact_sha256: envelope.artifact_type for _, envelope in indexed
    }
    if (
        referenced.get(evaluation.inputs.contract_sha256) != "policy_contract"
        or referenced.get(evaluation.inputs.suite_sha256) != "scenario_suite"
    ):
        raise ValueError("HASH_MISMATCH: baseline contract or suite")

    finding_reports = [
        envelope.payload
        for index, envelope in indexed
        if index > evaluation_index
        and envelope.artifact_type == "finding_report"
        and isinstance(envelope.payload, FindingReport)
        and envelope.payload.inputs == evaluation.inputs
    ]
    if not finding_reports:
        raise ValueError("run result has no baseline finding report")
    # Workflow ordering makes the first bound report the analyzer output. A later
    # report may contain human decisions and must not replace first-run evidence.
    return evaluation, finding_reports[0]


def _select_evidence(
    value: object, manifest: BenchmarkManifest
) -> tuple[EvaluationReport, FindingReport]:
    if not isinstance(value, dict):
        raise TypeError("run result must be a JSON object")
    if set(value) == {"evaluation", "findings"}:
        return (
            _validate_json(EvaluationReport, value["evaluation"]),
            _validate_json(FindingReport, value["findings"]),
        )
    return _select_record_evidence(value, manifest)


def _write_exclusive_atomic(path: Path, data: bytes) -> None:
    if path.is_symlink() or path.exists():
        raise FileExistsError("output already exists or is a symlink")
    parent = path.parent.resolve(strict=True)
    if not parent.is_dir():
        raise ValueError("output parent must be a directory")
    descriptor, temporary_name = tempfile.mkstemp(
        dir=parent, prefix=f".{path.name}.", suffix=".tmp"
    )
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
        os.link(temporary, parent / path.name)
    finally:
        temporary.unlink(missing_ok=True)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    score = commands.add_parser("score")
    score.add_argument("--manifest", required=True, type=Path)
    score.add_argument("--run-result", "--result", required=True, type=Path)
    score.add_argument("--output", required=True, type=Path)
    assessment = commands.add_parser(
        "assess-gold",
        help="Post-run gold-assisted assessment; never first-run discovery recall",
    )
    for flag in (
        "run-result",
        "run-metadata",
        "benchmark-dir",
        "schema-seal",
        "output",
    ):
        assessment.add_argument("--" + flag, required=True, type=Path)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        if args.command == "assess-gold":
            from app.features.evaluation.gold_assessment import assess_gold

            assess_gold(
                run_result=args.run_result,
                run_metadata=args.run_metadata,
                benchmark_dir=args.benchmark_dir,
                schema_seal=args.schema_seal,
                output=args.output,
            )
            print(
                "Post-run gold assessment written; first-run discovery gate remains unmeasured"
            )
            return 0
        manifest = _validate_json(BenchmarkManifest, _read_json(args.manifest))
        evaluation, findings = _select_evidence(_read_json(args.run_result), manifest)
        score = score_benchmark(
            ScoreBenchmarkRequest(
                manifest=manifest, evaluation=evaluation, findings=findings
            )
        )
        _write_exclusive_atomic(
            args.output, (score.model_dump_json(indent=2) + "\n").encode("utf-8")
        )
    except (OSError, TypeError, ValueError, json.JSONDecodeError):
        print(
            "benchmark scoring failed: invalid evidence or unsafe path", file=sys.stderr
        )
        return 1
    print("benchmark score written")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
