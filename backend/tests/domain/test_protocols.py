import inspect
from typing import get_type_hints

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
from app.domain.protocols import (
    EvaluationEngine,
    FindingAnalyzer,
    LLMClient,
    PolicyCompiler,
    RegressionAnalyzer,
    RevisionApplier,
    RevisionPlanner,
    ScenarioPlanner,
)


class CompleteFake:
    async def complete_json(self, request: LLMRequest) -> LLMResponse:
        return LLMResponse(output={"operation": request.operation})


class CompilerFake:
    async def compile(self, request: CompilePolicyRequest) -> PolicyCompilation:
        raise LookupError(request.document.document_id)


class RevisionPlannerFake:
    async def propose(self, request: ProposeRevisionRequest) -> RevisionProposal:
        raise LookupError(request.document_sha256)


class EvaluationFake:
    def evaluate(self, request: EvaluatePolicyRequest) -> EvaluationReport:
        raise LookupError(request.engine_version)


class ScenarioPlannerFake:
    async def generate_initial(
        self, request: GenerateInitialScenariosRequest
    ) -> ScenarioBatch:
        return ScenarioBatch(candidates=())

    async def generate_targeted(
        self, request: GenerateTargetedScenariosRequest
    ) -> ScenarioBatch:
        return ScenarioBatch(candidates=request.existing_candidates)

    def assemble_suite(self, request: AssembleSuiteRequest) -> ScenarioSuite:
        raise LookupError(request.suite_id)


class FindingFake:
    def analyze(self, request: AnalyzeFindingsRequest) -> FindingReport:
        raise LookupError(request.policy.policy_id)


class ApplierFake:
    def apply_revision(self, request: ApplyRevisionRequest) -> PatchApplicationResult:
        raise LookupError(request.proposal.proposal_id)


class RegressionFake:
    def compare(self, request: CompareRevisionRequest) -> ComparisonBundle:
        raise LookupError(request.proposal.proposal_id)


def test_runtime_protocols_accept_complete_structural_fakes() -> None:
    assert isinstance(CompleteFake(), LLMClient)
    assert isinstance(CompilerFake(), PolicyCompiler)
    assert isinstance(RevisionPlannerFake(), RevisionPlanner)
    assert isinstance(EvaluationFake(), EvaluationEngine)
    assert isinstance(ScenarioPlannerFake(), ScenarioPlanner)
    assert isinstance(FindingFake(), FindingAnalyzer)
    assert isinstance(ApplierFake(), RevisionApplier)
    assert isinstance(RegressionFake(), RegressionAnalyzer)
    assert not isinstance(object(), LLMClient)


def test_protocol_methods_have_exact_request_and_result_annotations() -> None:
    expected = {
        (LLMClient, "complete_json"): (LLMRequest, LLMResponse, True),
        (PolicyCompiler, "compile"): (CompilePolicyRequest, PolicyCompilation, True),
        (RevisionPlanner, "propose"): (ProposeRevisionRequest, RevisionProposal, True),
        (EvaluationEngine, "evaluate"): (
            EvaluatePolicyRequest,
            EvaluationReport,
            False,
        ),
        (ScenarioPlanner, "generate_initial"): (
            GenerateInitialScenariosRequest,
            ScenarioBatch,
            True,
        ),
        (ScenarioPlanner, "generate_targeted"): (
            GenerateTargetedScenariosRequest,
            ScenarioBatch,
            True,
        ),
        (ScenarioPlanner, "assemble_suite"): (
            AssembleSuiteRequest,
            ScenarioSuite,
            False,
        ),
        (FindingAnalyzer, "analyze"): (AnalyzeFindingsRequest, FindingReport, False),
        (RevisionApplier, "apply_revision"): (
            ApplyRevisionRequest,
            PatchApplicationResult,
            False,
        ),
        (RegressionAnalyzer, "compare"): (
            CompareRevisionRequest,
            ComparisonBundle,
            False,
        ),
    }

    for (protocol, method_name), (
        request_type,
        result_type,
        is_async,
    ) in expected.items():
        method = getattr(protocol, method_name)
        hints = get_type_hints(method)
        signature = inspect.signature(method)
        assert tuple(signature.parameters) == ("self", "request")
        assert hints == {"request": request_type, "return": result_type}
        assert inspect.iscoroutinefunction(method) is is_async


def test_scenario_batch_is_an_unbounded_candidate_transport_shape() -> None:
    batch = ScenarioBatch(candidates=())
    assert batch.candidates == ()
    assert set(type(batch).model_fields) == {"schema_version", "candidates"}
