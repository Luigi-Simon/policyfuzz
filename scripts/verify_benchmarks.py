#!/usr/bin/env python3
"""Re-evaluate public synthetic fixtures without rewriting their independent labels."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
if str(ROOT / "backend") not in sys.path:
    sys.path.insert(0, str(ROOT / "backend"))

from app.domain.models import (
    AnalyzeFindingsRequest,
    BenchmarkManifest,
    BenchmarkScore,
    EvaluatePolicyRequest,
    EvaluationReport,
    PolicyContract,
    PolicyIR,
    RunRecord,
    ScenarioSuite,
    ScoreBenchmarkRequest,
)
from app.features.evaluation.benchmark import score_benchmark
from app.features.evaluation.benchmark_cli import main as score_cli
from app.features.evaluation.engine import DeterministicEvaluationEngine
from app.features.evaluation.findings import DeterministicFindingAnalyzer
from app.workflow.validation import validate_evaluation


def verify_benchmarks(root: Path = ROOT) -> dict[str, object]:
    scores = {}
    for name in ("development", "corrected-control"):
        directory = root / "samples/benchmarks" / name

        def read(filename, model, directory=directory):
            path = directory / filename
            if path.is_symlink():
                raise ValueError("Benchmark members must be regular files.")
            return model.model_validate_json(path.read_bytes())

        policy = read("canonical-policy-ir.json", PolicyIR)
        contract = read("confirmed-contract.json", PolicyContract)
        suite = read("frozen-suite.json", ScenarioSuite)
        expected = read("expected-effects.json", EvaluationReport)
        manifest = read("defect-manifest.json", BenchmarkManifest)
        request = EvaluatePolicyRequest(
            policy=policy,
            contract=contract,
            suite=suite,
            inputs=expected.inputs,
            engine_version=expected.engine_version,
        )
        actual = validate_evaluation(
            DeterministicEvaluationEngine().evaluate(request), request
        )
        if actual != expected:
            raise ValueError(
                "Deterministic execution differs from the recorded fixture."
            )
        findings = DeterministicFindingAnalyzer().analyze(
            AnalyzeFindingsRequest(
                policy=policy, contract=contract, suite=suite, evaluation=actual
            )
        )
        score = score_benchmark(
            ScoreBenchmarkRequest(
                manifest=manifest, findings=findings, evaluation=actual
            )
        )
        saved = BenchmarkScore.model_validate_json(
            (root / f"team/person-4-evaluation/evidence/{name}-score.json").read_bytes()
        )
        if score != saved:
            raise ValueError(
                "Published technical score differs from independent labels."
            )
        values = (score.true_positives, score.false_positives, score.false_negatives)
        if values != ((3, 0, 0) if name == "development" else (0, 0, 0)):
            raise ValueError("Synthetic benchmark acceptance failed.")
        scores[name] = {
            "true_positives": values[0],
            "false_positives": values[1],
            "false_negatives": values[2],
        }
    return {
        "status": "passed",
        "data_type": "synthetic",
        "human_reviewed": False,
        "scores": scores,
    }


def verify_blind_score(root: Path = ROOT) -> None:
    """Only accept exact first-run scoring; gold-assisted assessments do not qualify."""
    from scripts.blind_evidence import bind_first_run
    from scripts.run_gate_b import _approval_path

    active = json.loads(
        (root / "submission/evidence/active-benchmark.json").read_bytes()
    )
    if (
        active.get("human_review") != "approved"
        or active.get("headline_gold_scoring_eligible") is not True
    ):
        raise ValueError("Human benchmark approval remains pending.")
    _approval_path(root, active)
    raw = root / "team/person-1-integration/evidence/blind-first-run.json"
    metadata_path = raw.with_name(raw.name + ".metadata.json")
    if raw.is_symlink() or metadata_path.is_symlink():
        raise ValueError("Blind evidence must be regular files.")
    data = raw.read_bytes()
    record = RunRecord.model_validate_json(data)
    metadata = json.loads(metadata_path.read_bytes())
    if (
        record.manifest.mode != "live"
        or metadata.get("status") != "recorded"
        or metadata.get("run_id") != record.run_id
        or metadata.get("result_bytes_sha256") != hashlib.sha256(data).hexdigest()
        or any(
            metadata.get("candidate", {}).get(key) != active.get(key)
            for key in (
                "candidate_version",
                "source_policy_sha256",
                "schema_archive_sha256",
            )
        )
    ):
        raise ValueError("Blind evidence does not match the first recorded attempt.")
    bind_first_run(root, active, record, metadata)
    from app.container import make_manifest_factory
    from app.core.config import Settings
    from app.workflow.types import SystemClock

    current = make_manifest_factory(Settings(app_mode="cached"), SystemClock())(
        "blind-score-verification", "cached"
    )
    if (
        current.engine_sha256 != record.manifest.engine_sha256
        or current.engine_version != record.manifest.engine_version
        or current.prompt_hashes != record.manifest.prompt_hashes
    ):
        raise ValueError("Application source changed after the recorded blind attempt.")
    artifacts = {item.artifact_sha256: item.payload for item in record.artifacts}
    evaluations = [
        item.payload
        for item in record.artifacts
        if item.artifact_type == "evaluation_report"
    ]
    if not evaluations:
        raise ValueError("The first recorded attempt has no execution evidence.")
    for expected in evaluations:
        request = EvaluatePolicyRequest(
            policy=artifacts[expected.inputs.policy_sha256],
            contract=artifacts[expected.inputs.contract_sha256],
            suite=artifacts[expected.inputs.suite_sha256],
            inputs=expected.inputs,
            engine_version=expected.engine_version,
        )
        if DeterministicEvaluationEngine().evaluate(request) != expected:
            raise ValueError("Blind execution evidence cannot be reproduced.")
    saved = BenchmarkScore.model_validate_json(
        (root / "team/person-4-evaluation/evidence/blind-score.json").read_bytes()
    )
    with tempfile.TemporaryDirectory() as directory:
        output = Path(directory) / "score.json"
        status = score_cli(
            (
                "score",
                "--manifest",
                str(root / "samples/benchmarks/blind/defect-manifest.json"),
                "--run-result",
                str(raw),
                "--output",
                str(output),
            )
        )
        if status or BenchmarkScore.model_validate_json(output.read_bytes()) != saved:
            raise ValueError(
                "First-run benchmark score cannot be independently reproduced."
            )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--include-blind", action="store_true")
    args = parser.parse_args()
    try:
        report = verify_benchmarks()
        if args.include_blind:
            verify_blind_score()
            report["blind_score"] = "verified"
        print(json.dumps(report, sort_keys=True))
    except (OSError, ValueError, TypeError, KeyError):
        print("Public synthetic benchmark verification failed.", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
