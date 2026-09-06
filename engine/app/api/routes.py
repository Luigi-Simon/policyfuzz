from __future__ import annotations

import json

from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from fastapi.responses import PlainTextResponse
from pydantic import BaseModel, ValidationError

from app.contracts.effectiveness import PolicyEffectivenessReport
from app.contracts.evaluation import EvaluationReport
from app.contracts.mirofish import MiroFishPack
from app.contracts.policy import PolicyIR
from app.contracts.run import AudienceSegment, RunRecord, SeedSpec
from app.contracts.scenario import ScenarioSuite
from app.services.coordinator import Coordinator
from app.services.ingest import ingest_bytes
from app.store import RunStore

router = APIRouter()


def _coordinator() -> Coordinator:
    return Coordinator()


class ReviseBody(BaseModel):
    instruction: str


class RunSummary(BaseModel):
    run_id: str
    status: str
    message: str
    policy_id: str | None = None
    policy_revision: int | None = None
    rule_count: int = 0
    scenario_count: int = 0
    score: int | None = None
    error: str | None = None


def _summary(record: RunRecord) -> RunSummary:
    return RunSummary(
        run_id=record.run_id,
        status=record.status,
        message=record.message,
        policy_id=record.ir.policy_id if record.ir else None,
        policy_revision=record.ir.revision if record.ir else None,
        rule_count=len(record.ir.rules) if record.ir else 0,
        scenario_count=len(record.suite.scenarios) if record.suite else 0,
        score=record.effectiveness.score if record.effectiveness else None,
        error=record.error,
    )


def _parse_audience_json(raw: str) -> list[AudienceSegment]:
    if not raw or not raw.strip():
        return []
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError as error:
        raise HTTPException(400, f"audience_json is not valid JSON: {error}") from error
    items = payload.get("segments") if isinstance(payload, dict) else payload
    if not isinstance(items, list):
        raise HTTPException(400, "audience_json must be a list of segments or {segments: [...]}")
    try:
        return [AudienceSegment.model_validate(item) for item in items]
    except ValidationError as error:
        raise HTTPException(400, f"Invalid audience segment: {error}") from error


@router.post("/runs", response_model=RunRecord)
async def create_run(
    file: UploadFile | None = File(default=None, description="Policy PDF, TXT, or MD"),
    policy_text: str = Form(default="", description="Paste a policy if you are not uploading a file"),
    seed_text: str = Form(default=""),
    population_size: int | None = Form(default=None),
    groups: str = Form(default="", description="Comma-separated audience groups"),
    audience_json: str = Form(
        default="",
        description='Structured audience segments JSON: [{"id","label","weight","attributes"}] or {segments:[...]}',
    ),
    locale: str = Form(default="", description="Optional locale / jurisdiction label for the audience"),
    seed_file: UploadFile | None = File(
        default=None,
        description="Optional audience seed PDF/TXT/MD. Text is merged into seed_text.",
    ),
):
    filename = "policy.txt"
    payload = b""
    if file is not None:
        payload = await file.read()
        filename = file.filename or "policy.txt"
    if not payload and policy_text.strip():
        payload = policy_text.encode("utf-8")
        filename = "policy.txt"
    if not payload:
        raise HTTPException(400, "Upload a policy file or paste policy text")
    seed_body = seed_text
    if seed_file is not None:
        seed_payload = await seed_file.read()
        if seed_payload:
            extracted = ingest_bytes(seed_file.filename or "seed.txt", seed_payload)
            seed_body = "\n\n".join(part for part in (seed_text, extracted.text) if part.strip())
    segments = _parse_audience_json(audience_json)
    group_list = [item.strip() for item in groups.split(",") if item.strip()]
    if not group_list and segments:
        group_list = [item.id for item in segments]
    seed = SeedSpec(
        text=seed_body,
        population_size=population_size,
        groups=group_list,
        segments=segments,
        locale=locale.strip(),
    )
    try:
        return _coordinator().create_run(
            filename=filename,
            payload=payload,
            seed=seed,
        )
    except Exception as error:
        raise HTTPException(400, str(error)) from error


@router.get("/runs", response_model=list[RunSummary])
def list_runs(limit: int = 50):
    return [_summary(record) for record in RunStore().list(limit=limit)]


@router.get("/runs/{run_id}", response_model=RunRecord)
def get_run(run_id: str):
    record = RunStore().get(run_id)
    if record is None:
        raise HTTPException(404, "Run not found")
    return record


@router.get("/runs/{run_id}/ir", response_model=PolicyIR)
def get_ir(run_id: str):
    record = RunStore().get(run_id)
    if record is None or record.ir is None:
        raise HTTPException(404, "PolicyIR not found")
    return record.ir


@router.post("/runs/{run_id}/revise", response_model=RunRecord)
def revise_run(run_id: str, body: ReviseBody):
    try:
        return _coordinator().revise(run_id, body.instruction)
    except KeyError:
        raise HTTPException(404, "Run not found") from None
    except ValueError as error:
        raise HTTPException(400, str(error)) from error


@router.post("/runs/{run_id}/scenarios", response_model=RunRecord)
def attach_scenarios(run_id: str, suite: ScenarioSuite):
    """Person 3 posts their ScenarioSuite here."""
    try:
        return _coordinator().attach_suite(run_id, suite)
    except KeyError:
        raise HTTPException(404, "Run not found") from None
    except ValueError as error:
        raise HTTPException(400, str(error)) from error


@router.get("/runs/{run_id}/scenarios", response_model=ScenarioSuite)
def get_scenarios(run_id: str):
    record = RunStore().get(run_id)
    if record is None or record.suite is None:
        raise HTTPException(404, "ScenarioSuite not found")
    return record.suite


@router.get("/runs/{run_id}/mirofish", response_model=MiroFishPack)
def get_mirofish_pack(run_id: str):
    record = RunStore().get(run_id)
    if record is None or record.mirofish is None:
        raise HTTPException(404, "MiroFish pack not found — compile PolicyIR first")
    return record.mirofish


@router.get("/runs/{run_id}/mirofish/seed.md")
def get_mirofish_seed(run_id: str):
    record = RunStore().get(run_id)
    if record is None or record.mirofish is None:
        raise HTTPException(404, "MiroFish seed not found")
    return PlainTextResponse(
        record.mirofish.seed_markdown,
        media_type="text/markdown",
        headers={"Content-Disposition": f'attachment; filename="{record.mirofish.seed_filename}"'},
    )


@router.post("/runs/{run_id}/mirofish", response_model=RunRecord)
def build_or_launch_mirofish(run_id: str, launch: bool = False):
    """Rebuild the MiroFish seed/prompt. Pass launch=true to POST into a running MiroFish."""
    try:
        return _coordinator().attach_mirofish(run_id, launch=launch)
    except KeyError:
        raise HTTPException(404, "Run not found") from None
    except ValueError as error:
        raise HTTPException(400, str(error)) from error


@router.get("/runs/{run_id}/evaluation", response_model=EvaluationReport)
def get_evaluation(run_id: str):
    record = RunStore().get(run_id)
    if record is None or record.evaluation is None:
        raise HTTPException(404, "EvaluationReport not found — rehearse first")
    return record.evaluation


@router.get("/runs/{run_id}/effectiveness", response_model=PolicyEffectivenessReport)
def get_effectiveness(run_id: str):
    record = RunStore().get(run_id)
    if record is None or record.effectiveness is None:
        raise HTTPException(404, "Effectiveness report not found — rehearse first")
    return record.effectiveness


@router.post("/runs/{run_id}/rehearse", response_model=RunRecord)
def rehearse_run(run_id: str, swarm: bool = True):
    """Person 3: grade fuzz agents and optionally run the MiroFish swarm, then score 0–100."""
    try:
        return _coordinator().rehearse(run_id, swarm=swarm)
    except KeyError:
        raise HTTPException(404, "Run not found") from None
    except ValueError as error:
        raise HTTPException(400, str(error)) from error
