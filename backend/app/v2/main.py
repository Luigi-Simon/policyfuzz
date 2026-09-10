"""Standalone FastAPI application for the v2 fixture milestone."""

from __future__ import annotations

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from .orchestrator import AdapterExecutionError, AdapterTimeoutError, Orchestrator
from .run_models import (
    CreateRunRequest,
    HealthResponse,
    PublicError,
    PublicSandboxResult,
)


def create_app(orchestrator: Orchestrator | None = None) -> FastAPI:
    runner = orchestrator or Orchestrator()
    application = FastAPI(title="PolicyFuzz v2 Fixture API", version="2.0.0")

    @application.exception_handler(RequestValidationError)
    async def invalid_request(
        request: Request, error: RequestValidationError
    ) -> JSONResponse:
        del request, error
        return JSONResponse(status_code=422, content={"detail": "Invalid run input."})

    @application.get("/api/v2/health", response_model=HealthResponse)
    async def health() -> HealthResponse:
        return HealthResponse()

    @application.post(
        "/api/v2/runs",
        response_model=PublicSandboxResult,
        responses={
            422: {"model": PublicError},
            502: {"model": PublicError},
            504: {"model": PublicError},
        },
    )
    async def create_run(body: CreateRunRequest) -> PublicSandboxResult | JSONResponse:
        try:
            return await runner.run(body)
        except AdapterTimeoutError:
            return JSONResponse(
                status_code=504,
                content={"detail": "Sandbox execution timed out."},
            )
        except AdapterExecutionError:
            return JSONResponse(
                status_code=502,
                content={"detail": "Sandbox execution failed."},
            )

    return application


app = create_app()
