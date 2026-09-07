"""Person 3 product output: policy effectiveness for the UI and Person 2 repair."""

from typing import Literal

from pydantic import BaseModel, Field

from app.contracts.common import JsonDict, new_id, now_iso

RevisionAction = Literal["clarify", "tighten", "carve_out", "add_rule", "communicate"]


class AgentInteraction(BaseModel):
    """One notable swarm moment used to justify the score."""

    agent: str
    platform: str = ""
    kind: str = "post"
    text: str
    why_significant: str = ""


class RevisionHint(BaseModel):
    """Smallest useful change for Person 2's repair agent / the human editor."""

    rule_ids: list[str] = Field(default_factory=list)
    action: RevisionAction
    summary: str


class PolicyEffectivenessReport(BaseModel):
    """0–100 score of how well the inputted policy would work, plus why."""

    schema_version: str = "1.0.0"
    report_id: str = Field(default_factory=lambda: new_id("eff"))
    policy_id: str
    policy_revision: int
    score: int = Field(ge=0, le=100)
    justification: str
    highlights: list[AgentInteraction] = Field(default_factory=list)
    recommended_actions: list[RevisionHint] = Field(default_factory=list)
    swarm_used: bool = False
    interaction_verified: bool = False
    metrics: JsonDict = Field(default_factory=dict)
    created_at: str = Field(default_factory=now_iso)
