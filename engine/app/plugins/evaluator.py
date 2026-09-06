"""Person 4 may override this. Person 3 ships RuleEvaluator as the default."""

from __future__ import annotations

from abc import ABC, abstractmethod

from app.contracts.evaluation import EvaluationReport
from app.contracts.policy import PolicyIR
from app.contracts.scenario import ScenarioSuite


class Evaluator(ABC):
    """PolicyIR + ScenarioSuite → EvaluationReport.

    Default implementation is Person 3's RuleEvaluator.
    Override via EVALUATOR=your.module:YourClass.
    """

    @abstractmethod
    def evaluate(self, ir: PolicyIR, suite: ScenarioSuite) -> EvaluationReport:
        raise NotImplementedError
