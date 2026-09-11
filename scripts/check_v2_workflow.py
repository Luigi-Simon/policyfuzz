"""Check the assembled workflow. Provider calls require the explicit --live flag."""

import argparse
import asyncio
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from app.v2.metric.sample import SAMPLE_POLICY
from app.v2.runtime import V2Settings, WorkflowRuntime
from app.v2.workflow_models import WorkflowRequest


async def check(args):
    runtime = WorkflowRuntime(
        V2Settings(_env_file=args.env_file, mirofish_base_url=args.mirofish_url)
    )
    try:
        result = await runtime.run(
            WorkflowRequest(
                policy=SAMPLE_POLICY.model_copy(update={"agent_count": args.count}),
                mode="live" if args.live else "fixture",
                max_rounds=args.rounds,
                sandbox_timeout_seconds=args.timeout,
                test_budget=args.test_budget,
            )
        )
        if args.output:
            args.output.parent.mkdir(parents=True, exist_ok=True)
            args.output.write_text(
                result.model_dump_json(indent=2) + "\n", encoding="utf-8"
            )
        print(
            json.dumps(
                {
                    "run_id": result.run_id,
                    "execution_mode": result.execution_mode.value,
                    "status": result.status,
                    "metric_passed": result.metric.passed,
                    "metric_failed": result.metric.failed,
                    "sandbox_status": result.sandbox.status.value
                    if result.sandbox
                    else None,
                    "observed_stakeholders": result.sandbox.observed_stakeholder_count
                    if result.sandbox
                    else 0,
                    "messages": len(result.sandbox.messages) if result.sandbox else 0,
                    "judge_status": result.judge.status if result.judge else None,
                    "judge_errors": result.judge.errors if result.judge else (),
                },
                indent=2,
            )
        )
        return 0 if result.status == "completed" else 1
    finally:
        await runtime.close()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--live", action="store_true")
    parser.add_argument("--env-file", type=Path)
    parser.add_argument("--mirofish-url", default="http://127.0.0.1:5002")
    parser.add_argument("--output", type=Path)
    parser.add_argument("--count", type=int, default=3)
    parser.add_argument("--rounds", type=int, default=2)
    parser.add_argument("--timeout", type=int, default=240)
    parser.add_argument("--test-budget", type=int, default=12)
    args = parser.parse_args()
    try:
        return asyncio.run(check(args))
    except Exception:  # noqa: BLE001 - never print credentials or provider diagnostics
        print(
            "Workflow check could not start or complete. Check the server configuration.",
            file=sys.stderr,
        )
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
