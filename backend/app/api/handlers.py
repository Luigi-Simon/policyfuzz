"""Fixed public errors; no exception text or validation input crosses HTTP."""

from fastapi import FastAPI, Request
from fastapi.exception_handlers import http_exception_handler
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException

from app.core.errors import to_public_error
from app.domain.models import PublicError
from app.workflow.errors import WorkflowError

ERROR_STATUSES = {
    "RUN_NOT_FOUND": 404,
    "INVALID_STATE": 409,
    "HASH_MISMATCH": 409,
    "PROVIDER_UNAVAILABLE": 503,
    "MALFORMED_MODEL_OUTPUT": 502,
    "INTERNAL_ERROR": 500,
}


def error_response(
    error: PublicError, *, status_code: int | None = None
) -> JSONResponse:
    return JSONResponse(
        status_code=status_code or ERROR_STATUSES.get(error.code, 422),
        content={"error": error.model_dump(mode="json")},
    )


def install_handlers(app: FastAPI) -> None:
    @app.exception_handler(HTTPException)
    async def parsing_error(request: Request, exc: HTTPException):
        if (
            exc.status_code == 400
            and request.method == "POST"
            and request.url.path.startswith("/api/v1/")
        ):
            return error_response(
                PublicError(code="INVALID_INPUT", message="The request is invalid.")
            )
        return await http_exception_handler(request, exc)

    @app.exception_handler(RequestValidationError)
    async def invalid_input(request: Request, exc: RequestValidationError):
        return error_response(
            PublicError(code="INVALID_INPUT", message="The request is invalid.")
        )

    @app.exception_handler(WorkflowError)
    async def workflow_error(request: Request, exc: WorkflowError):
        # A corrupted server-owned cache is not a stale client decision.
        if (
            request.url.path == "/api/v1/runs"
            and exc.public_error.code == "HASH_MISMATCH"
        ):
            return error_response(exc.public_error, status_code=500)
        return error_response(exc.public_error)

    @app.exception_handler(Exception)
    async def internal_error(request: Request, exc: Exception):
        return error_response(to_public_error(exc))


class SafeErrorMiddleware:
    """Contain unexpected failures inside CORS and suppress raw server tracebacks."""

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            return await self.app(scope, receive, send)
        started = False

        async def safe_send(message):
            nonlocal started
            if message["type"] == "http.response.start":
                started = True
            await send(message)

        try:
            await self.app(scope, receive, safe_send)
        except Exception as exc:  # noqa: BLE001 - sanitize the outer HTTP boundary
            if started:
                raise RuntimeError("Response delivery failed.") from None
            await error_response(to_public_error(exc))(scope, receive, send)
