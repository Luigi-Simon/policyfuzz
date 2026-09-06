"""Shared contracts for all five roles.

Person 2 produces PolicyIR.
Person 3 consumes PolicyIR + SeedSpec, produces ScenarioSuite, grades it,
optionally runs the MiroFish swarm, and writes PolicyEffectivenessReport.
Person 4 may override the evaluator plugin; the default lives in Person 3.
Person 1 orchestrates via RunState.
"""

from app.contracts.common import Citation, JsonDict, new_id, now_iso
from app.contracts.effectiveness import (
    AgentInteraction,
    PolicyEffectivenessReport,
    RevisionHint,
)
from app.contracts.evaluation import EvaluationReport, Finding, TraceStep
from app.contracts.mirofish import MiroFishLaunch, MiroFishPack
from app.contracts.policy import (
    ActionSpec,
    ActorType,
    AttributeSchema,
    CompiledIndex,
    Obligation,
    PolicyDocument,
    PolicyIR,
    Predicate,
    Rule,
    ValueType,
)
from app.contracts.run import RunRecord, RunStatus, SeedSpec
from app.contracts.scenario import (
    ExpectedOutcome,
    Scenario,
    ScenarioKind,
    ScenarioSuite,
)

__all__ = [
    "ActionSpec",
    "ActorType",
    "AgentInteraction",
    "AttributeSchema",
    "Citation",
    "CompiledIndex",
    "EvaluationReport",
    "PolicyEffectivenessReport",
    "RevisionHint",
    "ExpectedOutcome",
    "Finding",
    "JsonDict",
    "MiroFishLaunch",
    "MiroFishPack",
    "Obligation",
    "PolicyDocument",
    "PolicyIR",
    "Predicate",
    "Rule",
    "RunRecord",
    "RunStatus",
    "Scenario",
    "ScenarioKind",
    "ScenarioSuite",
    "SeedSpec",
    "TraceStep",
    "ValueType",
    "new_id",
    "now_iso",
]
