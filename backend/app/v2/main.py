"""Standalone v2 API for reviewed Metric runs and Sandbox fixture previews."""

from __future__ import annotations

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from .metric_contracts import MetricReview, MetricRunResult
from .orchestrator import (
    AdapterExecutionError,
    AdapterTimeoutError,
    Orchestrator,
    StaleMetricReviewError,
)
from .run_models import (
    CreateRunRequest,
    HealthResponse,
    PrepareMetricRequest,
    PublicError,
    PublicSandboxResult,
    RunMetricRequest,
    RunPolicyInput,
)


def create_app(orchestrator: Orchestrator | None = None) -> FastAPI:
    runner = orchestrator or Orchestrator()
    application = FastAPI(title="PolicyFuzz v2 API", version="2.0.0")

    @application.exception_handler(RequestValidationError)
    async def invalid_request(
        request: Request, error: RequestValidationError
    ) -> JSONResponse:
        del request, error
        return JSONResponse(status_code=422, content={"detail": "Invalid run input."})

    @application.get("/api/v2/health", response_model=HealthResponse)
    async def health() -> HealthResponse:
        return HealthResponse()

    @application.get("/api/v2/metric/sample", response_model=RunPolicyInput)
    def metric_sample() -> RunPolicyInput:
        from .metric.sample import SAMPLE_POLICY

        return SAMPLE_POLICY

    @application.post(
        "/api/v2/metric/prepare",
        response_model=MetricReview,
        responses={422: {"model": PublicError}},
    )
    def prepare_metric(body: PrepareMetricRequest) -> MetricReview:
        return runner.prepare_metric(body.policy)

    @application.post(
        "/api/v2/metric/runs",
        response_model=MetricRunResult,
        responses={409: {"model": PublicError}, 422: {"model": PublicError}},
    )
    def metric_run(body: RunMetricRequest) -> MetricRunResult | JSONResponse:
        try:
            return runner.run_metric(body)
        except StaleMetricReviewError:
            return JSONResponse(
                status_code=409,
                content={
                    "detail": "Policy inputs changed. Review the policy again.",
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
