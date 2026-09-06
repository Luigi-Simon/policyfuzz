"""Explicitly scripted workflow stage fakes for offline tests only.

These fakes never derive policy meaning, findings, metrics, or verdicts. Every
call consumes one caller-supplied typed result, exception, or callback.
"""

from __future__ import annotations

import inspect
from collections import deque
from collections.abc import Awaitable, Callable, Iterable
from typing import Any

from pydantic import BaseModel

from app.domain.models import (
    AnalyzeFindingsRequest,
    ApplyRevisionRequest,
    AssembleSuiteRequest,
    CompareRevisionRequest,
    ComparisonBundle,
    CompilePolicyRequest,
    CreateRunRequest,
    EvaluatePolicyRequest,
    EvaluationReport,
    FindingReport,
    GenerateInitialScenariosRequest,
    GenerateTargetedScenariosRequest,
    MetricsReport,
    MetricsRequest,
    PatchApplicationResult,
    PolicyCompilation,
    PolicyDocument,
    ProposeRevisionRequest,
    PublicError,
    RevisionProposal,
    ScenarioBatch,
    ScenarioSuite,
)
from app.workflow.errors import WorkflowError

type ScriptCallback[RequestT: BaseModel, ResultT: BaseModel] = Callable[
    [RequestT], ResultT | Awaitable[ResultT]
]
type ScriptOutcome[RequestT: BaseModel, ResultT: BaseModel] = (
    ResultT | Exception | ScriptCallback[RequestT, ResultT]
)

_SCRIPT_ERROR = PublicError(
    code="INTERNAL_ERROR",
    message="The workflow could not complete.",
    retryable=False,
)


def _script_error() -> WorkflowError:
    return WorkflowError(_SCRIPT_ERROR.model_copy(deep=True))


class _Script[RequestT: BaseModel, ResultT: BaseModel]:
    """Consume a validated finite script without manufacturing a fallback."""

    def __init__(
        self,
        request_type: type[RequestT],
        result_type: type[ResultT],
        outcomes: Iterable[ScriptOutcome[RequestT, ResultT]],
    ) -> None:
        self._request_type = request_type
        self._result_type = result_type
        self._outcomes: deque[ScriptOutcome[RequestT, ResultT]] = deque()
        self.requests: list[RequestT] = []
        for outcome in outcomes:
            self.queue(outcome)

    @property
    def calls(self) -> int:
        return len(self.requests)

    def queue(self, outcome: ScriptOutcome[RequestT, ResultT]) -> None:
        if isinstance(outcome, self._result_type):
            validated = self._result_type.model_validate(outcome).model_copy(deep=True)
            self._outcomes.append(validated)
            return
        if isinstance(outcome, Exception) or callable(outcome):
            self._outcomes.append(outcome)
            return
        raise TypeError(
            "scripted outcome must be a typed result, exception, or callback"
        )

    def begin(
        self, request: RequestT
    ) -> tuple[RequestT, ScriptOutcome[RequestT, ResultT]]:
        snapshot = self._request_type.model_validate(request).model_copy(deep=True)
        self.requests.append(snapshot)
        if not self._outcomes:
            raise _script_error() from None
        return snapshot.model_copy(deep=True), self._outcomes.popleft()

    def validate_result(self, result: Any) -> ResultT:
        return self._result_type.model_validate(result).model_copy(deep=True)

    def run_sync(self, request: RequestT) -> ResultT:
        snapshot, outcome = self.begin(request)
        if isinstance(outcome, Exception):
            raise outcome
        result = outcome(snapshot) if callable(outcome) else outcome
        if inspect.isawaitable(result):
            if inspect.iscoroutine(result):
                result.close()
            raise _script_error() from None
        return self.validate_result(result)

    async def run_async(self, request: RequestT) -> ResultT:
        snapshot, outcome = self.begin(request)
        if isinstance(outcome, Exception):
            raise outcome
        result = outcome(snapshot) if callable(outcome) else outcome
        if inspect.isawaitable(result):
            result = await result
        return self.validate_result(result)


class FakePolicyCompiler:
    """Test-only finite script implementing ``PolicyCompiler``."""

    def __init__(
        self,
        outcomes: Iterable[
            PolicyCompilation
            | Exception
            | Callable[
                [CompilePolicyRequest],
                PolicyCompilation | Awaitable[PolicyCompilation],
            ]
        ] = (),
    ) -> None:
        self._script = _Script(CompilePolicyRequest, PolicyCompilation, outcomes)
        self.requests = self._script.requests

    @property
    def calls(self) -> int:
        return self._script.calls

    def queue(
        self,
        outcome: PolicyCompilation
        | Exception
        | Callable[
            [CompilePolicyRequest], PolicyCompilation | Awaitable[PolicyCompilation]
        ],
    ) -> None:
        self._script.queue(outcome)

    async def compile(self, request: CompilePolicyRequest) -> PolicyCompilation:
        return await self._script.run_async(request)


class FakeEvaluationEngine:
    """Test-only finite script implementing ``EvaluationEngine``."""

    def __init__(
        self,
        outcomes: Iterable[
            EvaluationReport
            | Exception
            | Callable[
                [EvaluatePolicyRequest], EvaluationReport | Awaitable[EvaluationReport]
            ]
        ] = (),
    ) -> None:
        self._script = _Script(EvaluatePolicyRequest, EvaluationReport, outcomes)
        self.requests = self._script.requests

    @property
    def calls(self) -> int:
        return self._script.calls

    def queue(
        self,
        outcome: EvaluationReport
        | Exception
        | Callable[
            [EvaluatePolicyRequest], EvaluationReport | Awaitable[EvaluationReport]
        ],
    ) -> None:
        self._script.queue(outcome)

    def evaluate(self, request: EvaluatePolicyRequest) -> EvaluationReport:
        return self._script.run_sync(request)


class FakeFindingAnalyzer:
    """Test-only finite script implementing ``FindingAnalyzer``."""

    def __init__(
        self,
        outcomes: Iterable[
            FindingReport
            | Exception
            | Callable[
                [AnalyzeFindingsRequest], FindingReport | Awaitable[FindingReport]
            ]
        ] = (),
    ) -> None:
        self._script = _Script(AnalyzeFindingsRequest, FindingReport, outcomes)
        self.requests = self._script.requests

    @property
    def calls(self) -> int:
        return self._script.calls

    def queue(
        self,
        outcome: FindingReport
        | Exception
        | Callable[[AnalyzeFindingsRequest], FindingReport | Awaitable[FindingReport]],
    ) -> None:
        self._script.queue(outcome)

    def analyze(self, request: AnalyzeFindingsRequest) -> FindingReport:
        return self._script.run_sync(request)


class FakeRevisionPlanner:
    """Test-only finite script implementing ``RevisionPlanner``."""

    def __init__(
        self,
        outcomes: Iterable[
            RevisionProposal
            | Exception
            | Callable[
                [ProposeRevisionRequest],
                RevisionProposal | Awaitable[RevisionProposal],
            ]
        ] = (),
    ) -> None:
        self._script = _Script(ProposeRevisionRequest, RevisionProposal, outcomes)
        self.requests = self._script.requests

    @property
    def calls(self) -> int:
        return self._script.calls

    def queue(
        self,
        outcome: RevisionProposal
        | Exception
        | Callable[
            [ProposeRevisionRequest], RevisionProposal | Awaitable[RevisionProposal]
        ],
    ) -> None:
        self._script.queue(outcome)

    async def propose(self, request: ProposeRevisionRequest) -> RevisionProposal:
        return await self._script.run_async(request)


class FakeRevisionApplier:
    """Test-only finite script implementing ``RevisionApplier``."""

    def __init__(
        self,
        outcomes: Iterable[
            PatchApplicationResult
            | Exception
            | Callable[
                [ApplyRevisionRequest],
                PatchApplicationResult | Awaitable[PatchApplicationResult],
            ]
        ] = (),
    ) -> None:
        self._script = _Script(ApplyRevisionRequest, PatchApplicationResult, outcomes)
        self.requests = self._script.requests

    @property
    def calls(self) -> int:
        return self._script.calls

    def queue(
        self,
        outcome: PatchApplicationResult
        | Exception
        | Callable[
            [ApplyRevisionRequest],
            PatchApplicationResult | Awaitable[PatchApplicationResult],
        ],
    ) -> None:
        self._script.queue(outcome)

    def apply_revision(self, request: ApplyRevisionRequest) -> PatchApplicationResult:
        return self._script.run_sync(request)


class FakeRegressionAnalyzer:
    """Test-only finite script implementing ``RegressionAnalyzer``."""

    def __init__(
        self,
        outcomes: Iterable[
            ComparisonBundle
            | Exception
            | Callable[
                [CompareRevisionRequest],
                ComparisonBundle | Awaitable[ComparisonBundle],
            ]
        ] = (),
    ) -> None:
        self._script = _Script(CompareRevisionRequest, ComparisonBundle, outcomes)
        self.requests = self._script.requests

    @property
    def calls(self) -> int:
        return self._script.calls

    def queue(
        self,
        outcome: ComparisonBundle
        | Exception
        | Callable[
            [CompareRevisionRequest], ComparisonBundle | Awaitable[ComparisonBundle]
        ],
    ) -> None:
        self._script.queue(outcome)

    def compare(self, request: CompareRevisionRequest) -> ComparisonBundle:
        return self._script.run_sync(request)


class FakeScenarioPlanner:
    """Test-only independent finite scripts implementing ``ScenarioPlanner``."""

    def __init__(
        self,
        *,
        initial: Iterable[
            ScenarioBatch
            | Exception
            | Callable[
                [GenerateInitialScenariosRequest],
                ScenarioBatch | Awaitable[ScenarioBatch],
            ]
        ] = (),
        targeted: Iterable[
            ScenarioBatch
            | Exception
            | Callable[
                [GenerateTargetedScenariosRequest],
                ScenarioBatch | Awaitable[ScenarioBatch],
            ]
        ] = (),
        suites: Iterable[
            ScenarioSuite
            | Exception
            | Callable[[AssembleSuiteRequest], ScenarioSuite | Awaitable[ScenarioSuite]]
        ] = (),
    ) -> None:
        self._initial = _Script(GenerateInitialScenariosRequest, ScenarioBatch, initial)
        self._targeted = _Script(
            GenerateTargetedScenariosRequest, ScenarioBatch, targeted
        )
        self._suites = _Script(AssembleSuiteRequest, ScenarioSuite, suites)
        self.initial_requests = self._initial.requests
        self.targeted_requests = self._targeted.requests
        self.suite_requests = self._suites.requests

    @property
    def initial_calls(self) -> int:
        return self._initial.calls

    @property
    def targeted_calls(self) -> int:
        return self._targeted.calls

    @property
    def assembly_calls(self) -> int:
        return self._suites.calls

    def queue_initial(
        self,
        outcome: ScenarioBatch
        | Exception
        | Callable[
            [GenerateInitialScenariosRequest],
            ScenarioBatch | Awaitable[ScenarioBatch],
        ],
    ) -> None:
        self._initial.queue(outcome)

    def queue_targeted(
        self,
        outcome: ScenarioBatch
        | Exception
        | Callable[
            [GenerateTargetedScenariosRequest],
            ScenarioBatch | Awaitable[ScenarioBatch],
        ],
    ) -> None:
        self._targeted.queue(outcome)

    def queue_suite(
        self,
        outcome: ScenarioSuite
        | Exception
        | Callable[[AssembleSuiteRequest], ScenarioSuite | Awaitable[ScenarioSuite]],
    ) -> None:
        self._suites.queue(outcome)

    async def generate_initial(
        self, request: GenerateInitialScenariosRequest
    ) -> ScenarioBatch:
        return await self._initial.run_async(request)

    async def generate_targeted(
        self, request: GenerateTargetedScenariosRequest
    ) -> ScenarioBatch:
        return await self._targeted.run_async(request)

    def assemble_suite(self, request: AssembleSuiteRequest) -> ScenarioSuite:
        return self._suites.run_sync(request)


class FakeMetrics:
    """Test-only finite script for the injected deterministic metrics callable."""

    def __init__(
        self,
        outcomes: Iterable[
            MetricsReport
            | Exception
            | Callable[[MetricsRequest], MetricsReport | Awaitable[MetricsReport]]
        ] = (),
    ) -> None:
        self._script = _Script(MetricsRequest, MetricsReport, outcomes)
        self.requests = self._script.requests

    @property
    def calls(self) -> int:
        return self._script.calls

    def queue(
        self,
        outcome: MetricsReport
        | Exception
        | Callable[[MetricsRequest], MetricsReport | Awaitable[MetricsReport]],
    ) -> None:
        self._script.queue(outcome)

    def __call__(self, request: MetricsRequest) -> MetricsReport:
        return self._script.run_sync(request)


class FakeIngest:
    """Test-only finite script for the injected policy ingestion callable."""

    def __init__(
        self,
        outcomes: Iterable[
            PolicyDocument
            | Exception
            | Callable[[CreateRunRequest], PolicyDocument | Awaitable[PolicyDocument]]
        ] = (),
    ) -> None:
        self._script = _Script(CreateRunRequest, PolicyDocument, outcomes)
        self.requests = self._script.requests

    @property
    def calls(self) -> int:
        return self._script.calls

    def queue(
        self,
        outcome: PolicyDocument
        | Exception
        | Callable[[CreateRunRequest], PolicyDocument | Awaitable[PolicyDocument]],
    ) -> None:
        self._script.queue(outcome)

    def __call__(self, request: CreateRunRequest) -> PolicyDocument:
        return self._script.run_sync(request)


__all__ = [
    "FakeEvaluationEngine",
    "FakeFindingAnalyzer",
    "FakeIngest",
    "FakeMetrics",
    "FakePolicyCompiler",
    "FakeRegressionAnalyzer",
    "FakeRevisionApplier",
    "FakeRevisionPlanner",
    "FakeScenarioPlanner",
]
