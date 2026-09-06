"""FastAPI application factory and lifespan-owned cleanup."""

import os
from contextlib import asynccontextmanager
from urllib.parse import urlsplit

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.handlers import SafeErrorMiddleware, install_handlers
from app.api.routes import router
from app.container import AppContainer, build_container


def create_app(
    *, container: AppContainer | None = None, allowed_origin: str | None = None
) -> FastAPI:
    origin = (
        allowed_origin
        if allowed_origin is not None
        else os.environ.get("POLICYFUZZ_ALLOWED_ORIGIN", "http://localhost:5173")
    )
    try:
        parsed = urlsplit(origin)
    except ValueError:
        raise ValueError("A single local HTTP origin is required.") from None
    if (
        parsed.scheme not in {"http", "https"}
        or parsed.hostname not in {"localhost", "127.0.0.1", "::1"}
        or parsed.username
        or parsed.password
        or parsed.path
        or parsed.query
        or parsed.fragment
    ):
        raise ValueError("A single local HTTP origin is required.")
    # Validate port syntax without exposing an invalid origin in diagnostics.
    try:
        _ = parsed.port
    except ValueError:
        raise ValueError("A single local HTTP origin is required.") from None

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        owned = container if container is not None else build_container()
        app.state.container = owned
        owned.task_runner.start()
        try:
            yield
        finally:
            await owned.aclose()

    app = FastAPI(
        title="PolicyFuzz API",
        version="1.0",
        lifespan=lifespan,
        separate_input_output_schemas=False,
    )
    app.add_middleware(SafeErrorMiddleware)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[origin],
        allow_methods=["GET", "POST", "DELETE"],
        allow_headers=["Content-Type"],
    )
    install_handlers(app)
    app.include_router(router)
    return app


app = create_app()
