from typing import Any, Literal

from pydantic import BaseModel, Field

from app.contracts.common import JsonDict, new_id, now_iso

ScenarioKind = Literal["normal", "boundary", "adversarial", "targeted"]
ExpectedOutcome = Literal["compliant", "violation", "exception", "ambiguous"]


class Scenario(BaseModel):
    """One test case against PolicyIR.

    `facts` must be fillable from PolicyIR.actor_types / actions / index.fact_fields
    so person 4 can evaluate predicates without extra interpretation.
    """

    scenario_id: str = Field(default_factory=lambda: new_id("scn"))
    kind: ScenarioKind
    title: str
    narrative: str = ""
    facts: JsonDict = Field(default_factory=dict)
    targeted_rule_ids: list[str] = Field(default_factory=list)
    expected_outcome: ExpectedOutcome | None = None
    notes: str = ""


class ScenarioSuite(BaseModel):
    """Person 3 output: PolicyIR + seed → ScenarioSuite."""

    schema_version: str = "1.0.0"
    suite_id: str = Field(default_factory=lambda: new_id("suite"))
    policy_id: str
    policy_revision: int
    seed: str
    population_size: int | None = None
    scenarios: list[Scenario] = Field(default_factory=list)
    created_at: str = Field(default_factory=now_iso)

    def by_kind(self) -> dict[str, list[Scenario]]:
        grouped: dict[str, list[Scenario]] = {
            "normal": [],
            "boundary": [],
            "adversarial": [],
            "targeted": [],
        }
        for scenario in self.scenarios:
            grouped.setdefault(scenario.kind, []).append(scenario)
        return grouped
