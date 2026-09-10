"""Generate/check the Judge schemas and deterministic offline handoff examples."""

import argparse
import json
from pathlib import Path

from .judge_contracts import JudgeRequest, JudgeResult
from .judge_examples import make_judge_example

DEFAULT_OUTPUT = Path(__file__).resolve().parents[3] / "contracts" / "v2-judge"


def render_contracts() -> dict[str, bytes]:
    values = {
        "judge-request.schema.json": JudgeRequest.model_json_schema(),
        "judge-result.schema.json": JudgeResult.model_json_schema(),
    }
    for kind in ("complete", "partial", "unscored"):
        request, result = make_judge_example(kind)
        values[f"fixtures/{kind}-request.json"] = request.model_dump(mode="json")
        values[f"fixtures/{kind}-result.json"] = result.model_dump(mode="json")
    return {
        name: (
            json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
        ).encode()
        for name, value in values.items()
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true")
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()
    rendered = render_contracts()
    if args.check:
        actual = {
            str(p.relative_to(args.output)): p.read_bytes()
            for p in args.output.rglob("*")
            if p.is_file()
        }
        if actual != rendered:
            print("Judge contract drift. Run python -m app.v2.export_judge.")
            return 1
    else:
        for name, content in rendered.items():
            target = args.output / name
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(content)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
