"""Launch an existing MiroFish checkout with the owned v2 Sandbox extension."""

import argparse
import importlib.util
import os
import sys
from pathlib import Path


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", required=True, type=Path)
    parser.add_argument("--port", type=int, default=5002)
    parser.add_argument(
        "--journal",
        type=Path,
        help="Durable SQLite job journal; defaults to MiroFish uploads",
    )
    args = parser.parse_args()
    backend = args.root.resolve() / "backend"
    if not (backend / "app/__init__.py").is_file():
        parser.error("--root must name an existing MiroFish checkout")
    local = Path(__file__).resolve().parent
    contracts = load("policyfuzz_v2_contracts", local.parent / "contracts.py")
    extension = load("policyfuzz_v2_extension", local / "extension.py")
    sys.path.insert(0, str(backend))
    os.environ["POLICYFUZZ_MIROFISH_ROOT"] = str(args.root.resolve())
    from app import create_app
    from app.config import Config

    if not Config.LLM_API_KEY:
        parser.error(
            "Configure the model provider in MiroFish's local environment first"
        )
    app = create_app()
    extension.install(
        app, contracts, args.journal or backend / "uploads/policyfuzz-v2-jobs.sqlite"
    )
    app.run(host="127.0.0.1", port=args.port, debug=False, threaded=True)


if __name__ == "__main__":
    main()
