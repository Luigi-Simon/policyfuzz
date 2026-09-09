"""Frozen HTTP commands forwarded to the coordinator through owned jobs."""

from contextlib import suppress
from typing import Annotated

import httpx
from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from starlette.concurrency import run_in_threadpool

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
    PolicyDocument,
    PublicError,
    RunView,
    SelectFindingsRequest,
)
from app.features.fuzzing import HttpPolicyEngineClient, RehearsalRequest
from app.features.fuzzing.engine_client import EngineClientError
from app.workflow.errors import (
    InvalidRunCommandError,
    InvalidRunStateError,
    StaleArtifactError,
    WorkflowError,
)
from app.workflow.state_machine import allowed_actions

router = APIRouter(prefix="/api/v1")
Container = Annotated[AppContainer, Depends(get_container)]


class AgentSimulationCommand(BaseModel):
    """The user-controlled seed; all policy artifacts are resolved server-side."""

    seed_text: str = Field(default="", max_length=50_000)
    population_size: int = Field(default=12, ge=1, le=50)
    groups: tuple[str, ...] = ()
    policy_ir_sha256: str
    policy_contract_sha256: str
    scenario_suite_sha256: str
    confirmation: str


class CustomAgentSimulationCommand(BaseModel):
    """Fallback request for policies outside PolicyFuzz's typed T&E vocabulary.

    The generic MiroFish-compatible engine owns extraction for this path. It is
    deliberately separate from the confirmed PolicyFuzz launch route so the
    public contract never silently treats generic policy prose as travel or
    expense rules.
    """

    title: str = Field(min_length=1, max_length=200)
    policy_text: str = Field(min_length=1, max_length=50_000)
    seed_text: str = Field(default="", max_length=50_000)
    population_size: int = Field(default=12, ge=1, le=50)
    groups: tuple[str, ...] = ()
    non_confidential_confirmed: bool


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
    return await container.coordinator.confirm_contract(
        run_id, command, schedule=lambda work: container.submit(run_id, work)
    )


@router.post(
    "/runs/{run_id}/agent-simulation",
    operation_id="start_agent_simulation",
    include_in_schema=False,
)
async def start_agent_simulation(
    run_id: str,
    command: AgentSimulationCommand,
    container: Container,
):
    """Authorize an independent exploratory simulation after core review."""

    record = await container.coordinator.store.get(run_id)
    if record is None:
        raise InvalidRunCommandError()
    ready_stages = {
        "awaiting_finding_review",
        "completed_no_findings",
        "completed_no_revision",
        "complete",
    }
    if record.stage not in ready_stages:
        raise InvalidRunStateError(
            current_stage=record.stage,
            allowed_actions=allowed_actions(record.stage),
        )
    if command.confirmation != "confirmed":
        raise InvalidRunCommandError(
            current_stage=record.stage, allowed_actions=allowed_actions(record.stage)
        )
    artifacts = {
        envelope.artifact_type: envelope.artifact_sha256
        for envelope in record.artifacts
    }
    if not all(
        artifacts.get(kind)
        for kind in ("policy_ir", "policy_contract", "scenario_suite")
    ):
        raise InvalidRunCommandError(
            current_stage=record.stage, allowed_actions=allowed_actions(record.stage)
        )
    if (
        command.policy_ir_sha256 != artifacts["policy_ir"]
        or command.policy_contract_sha256 != artifacts["policy_contract"]
        or command.scenario_suite_sha256 != artifacts["scenario_suite"]
    ):
        raise StaleArtifactError(
            current_stage=record.stage, allowed_actions=allowed_actions(record.stage)
        )
    document = next(
        (
            envelope.payload
            for envelope in record.artifacts
            if envelope.artifact_type == "policy_document"
        ),
        None,
    )
    policy_text = (
        "\n\n".join(page.text for page in document.pages)
        if isinstance(document, PolicyDocument)
        else ""
    )
    if not policy_text.strip():
        raise InvalidRunCommandError(
            current_stage=record.stage, allowed_actions=allowed_actions(record.stage)
        )
    payload = await run_in_threadpool(
        _run_simulation,
        RehearsalRequest(
            policy_text=policy_text,
            seed_text=command.seed_text,
            population_size=command.population_size,
            groups=tuple(command.groups),
        ),
    )
    # These hashes anchor the launch decision only. The independent sidecar
    # reinterprets the source and generates its own exploratory scenarios.
    payload["source_policyfuzz_run_id"] = run_id
    payload["policy_title"] = document.title
    payload["source_artifact_hashes"] = {
        "policy_ir": command.policy_ir_sha256,
        "policy_contract": command.policy_contract_sha256,
        "scenario_suite": command.scenario_suite_sha256,
    }
    return payload


@router.get(
    "/agent-simulation/{engine_run_id}",
    operation_id="get_agent_simulation",
    include_in_schema=False,
)
def get_agent_simulation(engine_run_id: str):
    """Reopen a completed local MiroFish result for read-only evidence viewing."""

    client = None
    try:
        client = HttpPolicyEngineClient(timeout=30.0)
        result = client.get_rehearsal(engine_run_id)
        return _exploratory_payload(result.raw)
    except (EngineClientError, httpx.HTTPError, ValueError, TypeError):
        raise _simulation_unavailable() from None
    finally:
        if client is not None:
            with suppress(Exception):  # Cleanup must not mask the original result.
                client.close()


@router.post(
    "/custom-agent-simulation",
    operation_id="start_custom_agent_simulation",
    include_in_schema=False,
)
async def start_custom_agent_simulation(command: CustomAgentSimulationCommand):
    """Run arbitrary policy prose through the generic local rehearsal engine.

    This is a compatibility fallback for the frontend's agent demo. It is not
    used for the confirmed PolicyFuzz contract path and requires an explicit
    non-confidential acknowledgement before the source leaves the browser.
    """

    if not command.non_confidential_confirmed:
        raise InvalidRunCommandError()
    payload = await run_in_threadpool(
        _run_simulation,
        RehearsalRequest(
            policy_text=command.policy_text,
            seed_text=command.seed_text,
            population_size=command.population_size,
            groups=command.groups,
            policy_filename=command.title,
        ),
    )
    payload["compatibility_mode"] = "mirofish_generic_policy"
    payload["policy_title"] = command.title
    payload["policy_source_text"] = command.policy_text
    return payload


def _simulation_unavailable() -> WorkflowError:
    return WorkflowError(
        PublicError(
            code="PROVIDER_UNAVAILABLE",
            message="The simulation service could not complete this request. Check its status before starting another simulation.",
            retryable=False,
        )
    )


def _exploratory_payload(raw: dict) -> dict:
    payload = dict(raw)
    if not isinstance(payload.get("run_id"), str) or not payload["run_id"]:
        raise _simulation_unavailable()
    payload["evidence_scope"] = "independent_exploratory_simulation"
    payload["frozen_suite_reused"] = False
    if payload.get("error"):
        payload["error"] = (
            "The exploratory simulation did not complete. Any retained observations are partial and unverified."
        )
    return payload


def _run_simulation(request: RehearsalRequest) -> dict:
    """Keep synchronous sidecar I/O off the core API event loop; always close it."""
    client = None
    try:
        client = HttpPolicyEngineClient(timeout=300.0)
        created = client.create_rehearsal(request)
        if not created.engine_run_id:
            raise _simulation_unavailable()
        if created.error:
            return _exploratory_payload(created.raw)
        return _exploratory_payload(
            client.rehearse(created.engine_run_id, swarm=True).raw
        )
    except (EngineClientError, httpx.HTTPError, ValueError, TypeError):
        raise _simulation_unavailable() from None
    finally:
        if client is not None:
            with suppress(Exception):  # Cleanup must not mask the original result.
                client.close()


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
    return await container.coordinator.select_findings(
        run_id, command, schedule=lambda work: container.submit(run_id, work)
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
