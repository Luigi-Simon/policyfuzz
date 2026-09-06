"""Structural workflow stage contracts.

Runtime protocol checks verify only that required attributes are present. Static
type checking enforces the request and result annotations declared here.
"""

from typing import Protocol, runtime_checkable

from app.domain.models import (
    AnalyzeFindingsRequest,
    ApplyRevisionRequest,
    AssembleSuiteRequest,
    CompareRevisionRequest,
    ComparisonBundle,
    CompilePolicyRequest,
    EvaluatePolicyRequest,
    EvaluationReport,
    FindingReport,
    GenerateInitialScenariosRequest,
    GenerateTargetedScenariosRequest,
    LLMRequest,
    LLMResponse,
    PatchApplicationResult,
    PolicyCompilation,
    ProposeRevisionRequest,
    RevisionProposal,
    ScenarioBatch,
    ScenarioSuite,
)


@runtime_checkable
class LLMClient(Protocol):
    async def complete_json(self, request: LLMRequest) -> LLMResponse: ...


@runtime_checkable
class PolicyCompiler(Protocol):
    async def compile(self, request: CompilePolicyRequest) -> PolicyCompilation: ...


@runtime_checkable
class RevisionPlanner(Protocol):
    async def propose(self, request: ProposeRevisionRequest) -> RevisionProposal: ...


@runtime_checkable
class EvaluationEngine(Protocol):
    def evaluate(self, request: EvaluatePolicyRequest) -> EvaluationReport: ...


@runtime_checkable
class ScenarioPlanner(Protocol):
    async def generate_initial(
        self, request: GenerateInitialScenariosRequest
    ) -> ScenarioBatch: ...

    async def generate_targeted(
        self, request: GenerateTargetedScenariosRequest
    ) -> ScenarioBatch: ...

    def assemble_suite(self, request: AssembleSuiteRequest) -> ScenarioSuite: ...


@runtime_checkable
class FindingAnalyzer(Protocol):
    def analyze(self, request: AnalyzeFindingsRequest) -> FindingReport: ...


@runtime_checkable
class RevisionApplier(Protocol):
    def apply_revision(
        self, request: ApplyRevisionRequest
    ) -> PatchApplicationResult: ...


@runtime_checkable
class RegressionAnalyzer(Protocol):
    def compare(self, request: CompareRevisionRequest) -> ComparisonBundle: ...


__all__ = [
    "EvaluationEngine",
    "FindingAnalyzer",
    "LLMClient",
    "PolicyCompiler",
    "RegressionAnalyzer",
    "RevisionApplier",
    "RevisionPlanner",
    "ScenarioPlanner",
]
