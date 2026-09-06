"""Local DTOs for the sidecar policy-engine rehearsal service.

These are feature-owned transfer objects, not shared ``app.domain.models``.
Person 1 maps them into RunView / public contracts once those are frozen.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True, slots=True)
class AudienceSegmentInput:
    id: str
    label: str = ""
    weight: float = 1.0
    attributes: dict[str, Any] = field(default_factory=dict)

    def to_payload(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "label": self.label or self.id,
            "weight": self.weight,
            "attributes": dict(self.attributes),
        }


@dataclass(frozen=True, slots=True)
class RehearsalRequest:
    """Inputs Person 1 can pass when asking the engine to fuzz+score a policy."""

    policy_text: str
    seed_text: str = ""
    population_size: int = 20
    locale: str = ""
    groups: tuple[str, ...] = ()
    segments: tuple[AudienceSegmentInput, ...] = ()
    policy_filename: str = "policy.txt"


@dataclass(frozen=True, slots=True)
class RevisionHintView:
    rule_ids: tuple[str, ...]
    action: str
    summary: str


@dataclass(frozen=True, slots=True)
class EffectivenessView:
    score: int
    justification: str
    recommended_actions: tuple[RevisionHintView, ...]
    swarm_used: bool
    metrics: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class RehearsalResult:
    """Engine run snapshot safe for Person 1 orchestration."""

    engine_run_id: str
    status: str
    policy_id: str | None
    policy_revision: int | None
    rule_count: int
    scenario_count: int
    score: int | None
    effectiveness: EffectivenessView | None
    error: str | None = None
    raw: dict[str, Any] = field(default_factory=dict, repr=False)
