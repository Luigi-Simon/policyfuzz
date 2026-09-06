"""Frozen HTTP commands forwarded to the coordinator through owned jobs."""

from typing import Annotated

from fastapi import APIRouter, Depends

from app.api.dependencies import get_container, json_command
from app.container import AppContainer
from app.domain.export_schemas import build_openapi
from app.domain.models import (
    ConfirmContractRequest,
    ConfirmRevisionRequest,
    CreateRunRequest,
    CreateRunResponse,
    DeleteRunResponse,
    HealthResponse,
    RunView,
    SelectFindingsRequest,
)
from app.workflow.errors import InvalidRunCommandError

router = APIRouter(prefix="/api/v1")
Container = Annotated[AppContainer, Depends(get_container)]


def errors(path, method):
    return {
        int(status): response
        for status, response in build_openapi()["paths"]["/api/v1" + path][method][
            "responses"
        ].items()
        if int(status) >= 400
    }


@router.post(
    "/runs",
    status_code=202,
    response_model=CreateRunResponse,
    operation_id="create_run",
    responses=errors("/runs", "post"),
)
async def create_run(
    command: Annotated[CreateRunRequest, json_command(CreateRunRequest)],
    container: Container,
):
    if (
        command.text is not None
        and len(command.text) > container.settings.max_policy_chars
    ):
        raise InvalidRunCommandError()
    if container.validate_create is not None:
        container.validate_create(command)
    created = await container.coordinator.create_run(command)
    if container.coordinator.mode != "cached":
        container.task_runner.submit(
            created.run_id,
            lambda: container.execute(
                created.run_id, lambda: container.coordinator.start(created.run_id)
            ),
        )
    return created


@router.get(
    "/runs/{run_id}",
    response_model=RunView,
    operation_id="get_run",
    responses=errors("/runs/{run_id}", "get"),
)
async def get_run(run_id: str, container: Container):
    await container.task_runner.sweep()
    return await container.coordinator.get_run(run_id)


@router.post(
    "/runs/{run_id}/confirm-contract",
    response_model=RunView,
    operation_id="confirm_contract",
    responses=errors("/runs/{run_id}/confirm-contract", "post"),
)
async def confirm_contract(
    run_id: str,
    command: Annotated[ConfirmContractRequest, json_command(ConfirmContractRequest)],
    container: Container,
):
    return await container.task_runner.run(
        run_id,
        lambda: container.execute(
            run_id, lambda: container.coordinator.confirm_contract(run_id, command)
        ),
    )


@router.post(
    "/runs/{run_id}/select-findings",
    response_model=RunView,
    operation_id="select_findings",
    responses=errors("/runs/{run_id}/select-findings", "post"),
)
async def select_findings(
    run_id: str,
    command: Annotated[SelectFindingsRequest, json_command(SelectFindingsRequest)],
    container: Container,
):
    return await container.task_runner.run(
        run_id,
        lambda: container.execute(
            run_id, lambda: container.coordinator.select_findings(run_id, command)
        ),
    )


@router.post(
    "/runs/{run_id}/confirm-revision",
    response_model=RunView,
    operation_id="confirm_revision",
    responses=errors("/runs/{run_id}/confirm-revision", "post"),
)
async def confirm_revision(
    run_id: str,
    command: Annotated[ConfirmRevisionRequest, json_command(ConfirmRevisionRequest)],
    container: Container,
):
    return await container.task_runner.run(
        run_id,
        lambda: container.execute(
            run_id, lambda: container.coordinator.confirm_revision(run_id, command)
        ),
    )


@router.delete(
    "/runs/{run_id}",
    response_model=DeleteRunResponse,
    operation_id="delete_run",
    responses=errors("/runs/{run_id}", "delete"),
)
async def delete_run(run_id: str, container: Container):
    await container.task_runner.sweep()
    try:
        await container.coordinator.delete_run(run_id)
    finally:
        await container.task_runner.cancel(run_id)
    return DeleteRunResponse(run_id=run_id)


@router.get(
    "/health",
    response_model=HealthResponse,
    operation_id="health",
    responses=errors("/health", "get"),
)
async def health(container: Container):
    return HealthResponse(
        status="degraded"
        if container.settings.app_mode == "live" and not container.provider_configured
        else "ok",
        provider_configured=container.provider_configured,
        engine_version=container.engine_version,
    )
