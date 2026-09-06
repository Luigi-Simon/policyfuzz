"""Fuzz-test grading: pass / fail / ambiguous per scenario, with witness traces.

Person 3 produces this from PolicyIR + ScenarioSuite and hands failures back
to Person 2's repair agent. Person 4 may still register a custom EVALUATOR.
"""

from typing import Literal

from pydantic import BaseModel, Field

from app.contracts.common import JsonDict, new_id, now_iso

Verdict = Literal["pass", "fail", "ambiguous", "error"]


class TraceStep(BaseModel):
    rule_id: str
    matched: bool
    detail: str = ""


class Finding(BaseModel):
    finding_id: str = Field(default_factory=lambda: new_id("fnd"))
    scenario_id: str
    verdict: Verdict
    rule_ids: list[str] = Field(default_factory=list)
    summary: str
    traces: list[TraceStep] = Field(default_factory=list)


class EvaluationReport(BaseModel):
    """Person 4 output. Integration stores it if an evaluator plugin is registered."""

    schema_version: str = "1.0.0"
    report_id: str = Field(default_factory=lambda: new_id("eval"))
    policy_id: str
    policy_revision: int
    suite_id: str
    findings: list[Finding] = Field(default_factory=list)
    metrics: JsonDict = Field(default_factory=dict)
    created_at: str = Field(default_factory=now_iso)
