"""Standalone v2 API, including the assembled four-agent workflow."""

from __future__ import annotations

import os
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from .metric.sample import SAMPLE_POLICY
from .orchestrator import AdapterExecutionError, AdapterTimeoutError, Orchestrator
from .run_models import (
    CreateRunRequest,
    HealthResponse,
    PublicError,
    PublicSandboxResult,
    RunPolicyInput,
)
from .runtime import V2Settings, WorkflowRuntime
from .workflow import WorkflowUnavailable
from .workflow_models import (
    WorkflowCapabilities,
    WorkflowHealth,
    WorkflowRequest,
    WorkflowResult,
)


def create_app(
    orchestrator: Orchestrator | None = None,
    *,
    workflow=None,
    settings: V2Settings | None = None,
) -> FastAPI:
    runner = orchestrator or Orchestrator()
    config = settings or V2Settings(_env_file=os.environ.get("POLICYFUZZ_V2_ENV_FILE"))
    runtime = WorkflowRuntime(config)
    workflow_runner = workflow or runtime

    @asynccontextmanager
    async def lifespan(application):
        try:
            yield
        finally:
            await runtime.close()

    application = FastAPI(title="PolicyFuzz v2 API", version="2.0.0", lifespan=lifespan)

    @application.exception_handler(RequestValidationError)
    async def invalid_request(
        request: Request, error: RequestValidationError
    ) -> JSONResponse:
        del request, error
        return JSONResponse(status_code=422, content={"detail": "Invalid run input."})

    @application.get(
        "/api/v2/health",
        response_model=HealthResponse,
        description="Legacy fixture API liveness. Use /api/v2/workflows/health for live workflow configuration and engine reachability.",
    )
    async def health() -> HealthResponse:
        return HealthResponse()

    @application.get("/api/v2/workflows/health", response_model=WorkflowHealth)
    async def workflow_health() -> WorkflowHealth:
        return await runtime.health()

    @application.get(
        "/api/v2/workflows/capabilities", response_model=WorkflowCapabilities
    )
    async def workflow_capabilities() -> WorkflowCapabilities:
        return WorkflowCapabilities(
            live_available=config.live_available,
            live_detail="Provider configured. MiroFish availability is checked when a live run starts."
            if config.live_available
            else "Configure the server's model and provider key to enable live runs.",
        )

    @application.get("/api/v2/workflows/sample", response_model=RunPolicyInput)
    async def workflow_sample() -> RunPolicyInput:
        return SAMPLE_POLICY

    @application.post(
        "/api/v2/workflows",
        response_model=WorkflowResult,
        responses={422: {"model": PublicError}, 503: {"model": PublicError}},
    )
    async def create_workflow(body: WorkflowRequest) -> WorkflowResult | JSONResponse:
        try:
            return await workflow_runner.run(body)
        except WorkflowUnavailable:
            return JSONResponse(
                status_code=503,
                content={
                    "detail": "Live Sandbox and Judge services are not configured."
                },
            )

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
