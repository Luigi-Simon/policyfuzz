#!/usr/bin/env python3
"""Run actual specialist stages using explicit scripted development responses."""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.demo_support import digest, latest, run_demo


async def smoke(*, record: bool = False):
    run, responses = await run_demo()
    suite = latest(run, "scenario_suite")
    comparison = latest(run, "comparison_bundle")
    summary = {
        "status": "passed",
        "data_type": "synthetic",
        "provider_mode": "scripted",
        "run_mode": "cached",
        "scenario_count": len(suite.scenarios),
        "baseline_defects": comparison.baseline_metrics.unique_finding_count,
        "remaining_defects": comparison.revised_metrics.unique_finding_count,
        "patch_accepted": comparison.acceptance.patch_accepted,
        "suite_sha256": digest(suite),
        "engine_version": run.manifest.engine_version,
        "scripted_model_calls": len(responses),
        "actual_provider_calls": 0,
        "confirmation_source": "authored demonstration decisions",
        "blind_scoring_eligible": False,
    }
    if summary["baseline_defects"] != 3 or summary["remaining_defects"] != 0:
        raise ValueError(
            "Development defect counts differ from the seeded demonstration."
        )
    if record:
        destination = ROOT / "samples/cached-demo"
        destination.mkdir(parents=True, exist_ok=True)
        (destination / "run-record.json").write_text(
            run.model_dump_json(indent=2) + "\n"
        )
        (destination / "model-responses.json").write_text(
            json.dumps(
                {
                    "schema_version": "1.0",
                    "label": "SYNTHETIC SCRIPTED PROVIDER OUTPUTS — NOT LIVE MODEL QUALITY EVIDENCE",
                    "actual_provider_calls": 0,
                    "responses": responses,
                },
                indent=2,
                sort_keys=True,
            )
            + "\n"
        )
        (destination / "summary.json").write_text(
            json.dumps(summary, indent=2, sort_keys=True) + "\n"
        )
    return summary


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--record",
        action="store_true",
        help="Replace the development cache with newly validated outputs.",
    )
    args = parser.parse_args()
    try:
        print(json.dumps(asyncio.run(smoke(record=args.record)), sort_keys=True))
    except Exception:  # noqa: BLE001 - CLI emits only a safe status
        print(
            "Offline smoke failed; run the integration tests for detailed synthetic diagnostics.",
            file=sys.stderr,
        )
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
