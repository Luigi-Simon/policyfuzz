"""Opt-in real-provider smoke check using a small synthetic policy only."""

import argparse
import asyncio
import json
import os
from pathlib import Path
from uuid import uuid4

from app.v2.contracts import SandboxRequest, make_example_request, public_sandbox_result

from .language import OpenAILanguageTools
from .service import MiroFishSandboxService
from .transport import MiroFishClient


async def run(args):
    model = os.environ.get("LLM_MODEL") or os.environ.get("LLM_MODEL_NAME")
    key = os.environ.get("OPENAI_API_KEY") or os.environ.get("LLM_API_KEY")
    if not model or not key:
        raise SystemExit(
            "Set the configured model and provider key in the environment; never place keys in arguments."
        )
    language = OpenAILanguageTools(
        model=model, api_key=key, base_url=os.environ.get("LLM_BASE_URL") or None
    )
    client = MiroFishClient(args.base_url)
    service = MiroFishSandboxService(client, language)
    identity = args.request_id or f"sandbox-smoke-{uuid4()}"
    request = SandboxRequest.model_validate(
        make_example_request().model_dump()
        | {
            "request_id": identity,
            "run_id": identity,
            "stakeholder_count": args.count,
            "max_rounds": args.rounds,
            "timeout_seconds": args.timeout,
            **({"personality_seed": args.seed} if args.seed else {}),
        }
    )
    try:
        result = await service.run(request)
        args.output.mkdir(parents=True, exist_ok=True)
        (args.output / "request.json").write_text(
            request.model_dump_json(indent=2), encoding="utf-8"
        )
        (args.output / "public-result.json").write_text(
            json.dumps(public_sandbox_result(result), indent=2), encoding="utf-8"
        )
        # Internal originals and raw data stay outside public-result.json.
        (args.output / "internal-result.json").write_text(
            result.model_dump_json(indent=2), encoding="utf-8"
        )
        archive = service.internal_capture(result.request_fingerprint)
        if archive:
            (args.output / "internal-capture.json").write_text(
                archive, encoding="utf-8"
            )
        print(
            json.dumps(
                {
                    "execution_mode": result.execution_mode,
                    "status": result.status,
                    "requested": result.requested_stakeholder_count,
                    "configured": result.configured_stakeholder_count,
                    "observed": result.observed_stakeholder_count,
                    "messages": len(result.messages),
                    "limitations": result.limitations,
                    "errors": result.errors,
                },
                indent=2,
            )
        )
        return 0 if result.status == "completed" else 1
    finally:
        await client.close()
        await language.close()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--live", action="store_true", help="Required: authorizes real model usage"
    )
    parser.add_argument("--base-url", default="http://127.0.0.1:5002")
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument(
        "--request-id", help="Reuse the exact ID and settings to resume a known job"
    )
    parser.add_argument("--count", type=int, default=2)
    parser.add_argument("--rounds", type=int, default=2)
    parser.add_argument(
        "--seed", help="Optional synthetic stakeholder personality seed"
    )
    parser.add_argument("--timeout", type=int, default=180)
    args = parser.parse_args()
    if not args.live:
        parser.error("--live is required; this command makes real provider calls")
    raise SystemExit(asyncio.run(run(args)))


if __name__ == "__main__":
    main()
