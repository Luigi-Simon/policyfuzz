#!/usr/bin/env python3
"""Replay the same frozen baseline/revision artifacts three times."""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT / "backend") not in sys.path:
    sys.path.insert(0, str(ROOT / "backend"))

from app.container import make_manifest_factory
from app.core.artifacts import semantic_payload_projection
from app.core.config import Settings
from app.core.hashing import canonical_sha256
from app.domain.models import EvaluatePolicyRequest, RunRecord
from app.features.evaluation.engine import DeterministicEvaluationEngine
from app.workflow.types import SystemClock
from app.workflow.validation import validate_cached_record


def replay(
    path: Path = ROOT / "samples/cached-demo/run-record.json",
) -> dict[str, object]:
    record = validate_cached_record(RunRecord.model_validate_json(path.read_bytes()))
    current = make_manifest_factory(Settings(app_mode="cached"), SystemClock())(
        "replay-verification", "cached"
    )
    if (record.manifest.engine_version, record.manifest.engine_sha256) != (
        current.engine_version,
        current.engine_sha256,
    ):
        raise ValueError("Recorded engine commitment differs from current source.")

    def one(kind):
        return next(a.payload for a in record.artifacts if a.artifact_type == kind)

    suite, contract = one("scenario_suite"), one("policy_contract")
    reports = [
        a.payload for a in record.artifacts if a.artifact_type == "evaluation_report"
    ]
    policies = {
        a.artifact_sha256: a.payload
        for a in record.artifacts
        if a.artifact_type == "policy_ir"
    }
    hashes = []
    engine = DeterministicEvaluationEngine()
    for _ in range(3):
        result_hashes = []
        for report in reports:
            fresh = engine.evaluate(
                EvaluatePolicyRequest(
                    policy=policies[report.inputs.policy_sha256],
                    contract=contract,
                    suite=suite,
                    inputs=report.inputs,
                    engine_version=record.manifest.engine_version,
                )
            )
            actual = canonical_sha256(semantic_payload_projection(fresh))
            expected = canonical_sha256(semantic_payload_projection(report))
            if actual != expected:
                raise ValueError(
                    "Recorded execution differs from current deterministic replay."
                )
            result_hashes.append(actual)
        hashes.append(canonical_sha256(result_hashes))
    if not reports or len(set(hashes)) != 1:
        raise ValueError("Frozen replay is not deterministic.")
    return {
        "status": "passed",
        "replays": 3,
        "semantic_execution_sha256": hashes[0],
        "run_mode": "cached",
    }


def main() -> int:
    try:
        print(json.dumps(replay(), sort_keys=True))
    except (OSError, ValueError, KeyError):
        print("Recorded replay failed.", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
