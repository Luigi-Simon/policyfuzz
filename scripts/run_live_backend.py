"""Start PolicyFuzz in live mode without persisting provider credentials."""

from __future__ import annotations

import argparse
import getpass
import importlib.util
import os
import sys
from collections.abc import Mapping, Sequence
from pathlib import Path

DEFAULT_MODELS = {
    "openai": "gpt-5.6-luna",
    "bedrock": "amazon.nova-lite-v1:0",
}
DEFAULT_AWS_REGION = "us-east-1"


def select_provider_model(
    current: Mapping[str, str],
    *,
    requested_provider: str | None,
    requested_model: str | None,
) -> tuple[str, str]:
    """Select a matching provider/model pair without cross-provider env leakage."""
    provider = requested_provider or current.get("LLM_PROVIDER") or "openai"
    if provider not in DEFAULT_MODELS:
        raise ValueError("Provider must be 'openai' or 'bedrock'.")
    if requested_model is not None:
        model = requested_model
    elif requested_provider is not None:
        model = DEFAULT_MODELS[provider]
    else:
        model = current.get("LLM_MODEL") or DEFAULT_MODELS[provider]
    if not isinstance(model, str) or not model.strip():
        raise ValueError("A non-empty model ID is required.")
    return provider, model.strip()


def build_live_environment(
    current: Mapping[str, str],
    *,
    provider: str,
    model: str,
    openai_api_key: str | None = None,
    aws_region: str | None = None,
) -> dict[str, str]:
    """Return a live-mode environment while keeping secrets out of arguments."""
    if provider not in DEFAULT_MODELS:
        raise ValueError("Provider must be 'openai' or 'bedrock'.")
    if not isinstance(model, str) or not model.strip():
        raise ValueError("A non-empty model ID is required.")
    environment = dict(current)
    environment.update(
        {
            "APP_MODE": "live",
            "LLM_PROVIDER": provider,
            "LLM_MODEL": model.strip(),
        }
    )
    if provider == "openai":
        if not isinstance(openai_api_key, str) or not openai_api_key.strip():
            raise ValueError("A non-empty OpenAI API key is required.")
        environment["OPENAI_API_KEY"] = openai_api_key.strip()
    else:
        if not isinstance(aws_region, str) or not aws_region.strip():
            raise ValueError("A non-empty AWS region is required.")
        environment["AWS_REGION"] = aws_region.strip()
        environment.pop("OPENAI_API_KEY", None)
    return environment


def server_command(
    python_executable: str, *, port: int = 8000, reload: bool = True
) -> tuple[str, ...]:
    """Build the credential-free server command."""
    if type(port) is not int or not 1 <= port <= 65_535:
        raise ValueError("Port must be a valid TCP port.")
    command = (
        python_executable,
        "-m",
        "uvicorn",
        "app.main:app",
        "--host",
        "127.0.0.1",
        "--port",
        str(port),
    )
    return command + (("--reload",) if reload else ())


def _arguments(argv: Sequence[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Start the PolicyFuzz backend with OpenAI or Amazon Bedrock."
    )
    parser.add_argument(
        "--provider",
        choices=tuple(DEFAULT_MODELS),
        help="Hosted model provider. Defaults to LLM_PROVIDER or 'openai'.",
    )
    parser.add_argument(
        "--model",
        help=(
            "Provider model ID. With --provider, defaults to that provider's model; "
            "otherwise uses LLM_MODEL or the provider default."
        ),
    )
    parser.add_argument(
        "--aws-region",
        help=(
            f"AWS region for Bedrock. Defaults to AWS_REGION or {DEFAULT_AWS_REGION!r}."
        ),
    )
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument(
        "--no-reload",
        action="store_true",
        help="Disable automatic development reloads.",
    )
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> None:
    args = _arguments(argv)
    if importlib.util.find_spec("uvicorn") is None:
        raise SystemExit(
            "Backend dependencies are not installed. From the repository root run: "
            "python3 -m venv backend/.venv && "
            "backend/.venv/bin/python -m pip install -e './backend[dev]'"
        )

    try:
        provider, model = select_provider_model(
            os.environ,
            requested_provider=args.provider,
            requested_model=args.model,
        )
    except ValueError as error:
        raise SystemExit(str(error)) from None
    api_key = os.environ.get("OPENAI_API_KEY")
    if provider == "openai" and not api_key:
        api_key = getpass.getpass("OpenAI API key (input hidden): ")
    aws_region = (
        args.aws_region
        or os.environ.get("AWS_REGION")
        or os.environ.get("AWS_DEFAULT_REGION")
        or DEFAULT_AWS_REGION
    )
    try:
        environment = build_live_environment(
            os.environ,
            provider=provider,
            model=model,
            openai_api_key=api_key,
            aws_region=aws_region,
        )
        command = server_command(
            sys.executable, port=args.port, reload=not args.no_reload
        )
    except ValueError as error:
        raise SystemExit(str(error)) from None

    repository = Path(__file__).resolve().parents[1]
    os.chdir(repository / "backend")
    print(
        f"Starting PolicyFuzz live backend with provider {provider!r} "
        f"and model {model!r}."
    )
    if provider == "bedrock":
        print(
            "Bedrock credentials are loaded through the AWS SDK credential chain; "
            "temporary student credentials must still be valid."
        )
    print(f"Health check: http://127.0.0.1:{args.port}/api/v1/health")
    os.execvpe(command[0], command, environment)


if __name__ == "__main__":
    main()
