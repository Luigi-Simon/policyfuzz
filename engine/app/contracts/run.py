from typing import Literal

from pydantic import BaseModel, Field

from app.contracts.common import JsonDict, new_id, now_iso
from app.contracts.effectiveness import PolicyEffectivenessReport
from app.contracts.evaluation import EvaluationReport
from app.contracts.mirofish import MiroFishPack
from app.contracts.policy import PolicyDocument, PolicyIR
from app.contracts.scenario import ScenarioSuite

RunStatus = Literal[
    "pending",
    "ingesting",
    "extracting",
    "compiling",
    "compiled",
    "generating_scenarios",
    "scenarios_ready",
    "evaluating",
    "rehearsing",
    "completed",
    "failed",
]


class AudienceSegment(BaseModel):
    """One injectable audience slice (not tied to any jurisdiction)."""

    id: str
    label: str = ""
    weight: float = 1.0
    attributes: JsonDict = Field(default_factory=dict)


class SeedSpec(BaseModel):
    """Population / personality seed for person 3.

    Integration stores this with the run. Person 3 reads it from GET /v1/runs/{id}.
    Prefer `segments` for structured audience injection; `text` remains freeform notes
    for MiroFish prose. `groups` is a shorthand that still works without segments.
    """

    text: str = ""
    population_size: int | None = None
    groups: list[str] = Field(default_factory=list)
    segments: list[AudienceSegment] = Field(default_factory=list)
    locale: str = ""


class RunRecord(BaseModel):
    run_id: str = Field(default_factory=lambda: new_id("run"))
    status: RunStatus = "pending"
    message: str = ""
    error: str | None = None
    seed: SeedSpec = Field(default_factory=SeedSpec)
    document: PolicyDocument | None = None
    ir: PolicyIR | None = None
    suite: ScenarioSuite | None = None
    evaluation: EvaluationReport | None = None
    effectiveness: PolicyEffectivenessReport | None = None
    mirofish: MiroFishPack | None = None
    extra: JsonDict = Field(default_factory=dict)
    created_at: str = Field(default_factory=now_iso)
    updated_at: str = Field(default_factory=now_iso)

    def touch(self, status: RunStatus | None = None, message: str | None = None) -> None:
        if status is not None:
            self.status = status
        if message is not None:
            self.message = message
        self.updated_at = now_iso()
