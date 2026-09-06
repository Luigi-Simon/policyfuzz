#!/usr/bin/env python3
"""Example: GST voucher policy through Person 3 (≤50 agents, fuzz score)."""

from __future__ import annotations

import json
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parent
BASE = "http://127.0.0.1:8000"


def main() -> None:
    policy = ROOT / "gst_voucher_sg.txt"
    seed = (ROOT / "gst_voucher_seed.txt").read_text(encoding="utf-8")
    with httpx.Client(timeout=120.0) as client:
        client.get(f"{BASE}/health").raise_for_status()
        created = client.post(
            f"{BASE}/v1/runs",
            files={"file": ("gst_voucher_sg.txt", policy.read_bytes(), "text/plain")},
            data={
                "seed_text": seed,
                "population_size": "50",
                "groups": "citizens,permanent_residents,work_pass,children,working_adults,seniors,overseas,guardians",
            },
        )
        created.raise_for_status()
        run = created.json()
        run_id = run["run_id"]
        score = client.get(f"{BASE}/v1/runs/{run_id}/effectiveness")
        score.raise_for_status()
        evaluation = client.get(f"{BASE}/v1/runs/{run_id}/evaluation")
        evaluation.raise_for_status()

    effectiveness = score.json()
    print(
        json.dumps(
            {
                "run_id": run_id,
                "status": run["status"],
                "title": (run.get("ir") or {}).get("title"),
                "rule_count": len((run.get("ir") or {}).get("rules") or []),
                "scenario_count": len((run.get("suite") or {}).get("scenarios") or []),
                "score": effectiveness.get("score"),
                "swarm_used": effectiveness.get("swarm_used"),
                "justification": effectiveness.get("justification"),
                "recommended_actions": effectiveness.get("recommended_actions"),
                "verdicts": (evaluation.json().get("metrics") or {}).get("verdicts"),
                "docs": f"{BASE}/docs",
                "effectiveness_url": f"{BASE}/v1/runs/{run_id}/effectiveness",
                "note": "POST /v1/runs/{id}/rehearse?swarm=true once MiroFish is running to ground the score in agent talk.",
            },
            indent=2,
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    main()
