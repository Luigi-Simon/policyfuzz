"""Person 3 implements this. Integration will call it if registered."""

from __future__ import annotations

from abc import ABC, abstractmethod

from app.contracts.policy import PolicyIR
from app.contracts.run import SeedSpec
from app.contracts.scenario import ScenarioSuite


class ScenarioDesigner(ABC):
    """PolicyIR + seed → ScenarioSuite.

    Register via SCENARIO_DESIGNER=your.module:YourClass
    or POST the suite to /v1/runs/{run_id}/scenarios.
    """

    @abstractmethod
    def generate(self, ir: PolicyIR, seed: SeedSpec) -> ScenarioSuite:
        raise NotImplementedError
