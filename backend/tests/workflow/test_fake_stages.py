"""Behavioral tests for finite, test-only workflow stage fakes."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

import pytest
from pydantic import ValidationError

from app.domain.models import (
    AssembleSuiteRequest,
    CompilePolicyRequest,
    CoverageSnapshot,
    CreateRunRequest,
    EvaluatePolicyRequest,
    EvaluationReport,
    GenerateInitialScenariosRequest,
    GenerateTargetedScenariosRequest,
    MetricsReport,
    MetricsRequest,
    PolicyCompilation,
    PolicyDocument,
    PolicyPage,
    ScenarioBatch,
)
from app.domain.protocols import (
    EvaluationEngine,
    FindingAnalyzer,
    PolicyCompiler,
    RegressionAnalyzer,
    RevisionApplier,
    RevisionPlanner,
    ScenarioPlanner,
)
from app.workflow.errors import WorkflowError
from app.workflow.fake_stages import (
    FakeEvaluationEngine,
    FakeFindingAnalyzer,
    FakeIngest,
    FakeMetrics,
    FakePolicyCompiler,
    FakeRegressionAnalyzer,
    FakeRevisionApplier,
    FakeRevisionPlanner,
    FakeScenarioPlanner,
)
from tests.domain.factories import (
    HASH,
    make_inputs,
    make_policy,
    make_policy_contract,
    make_scenario_candidate,
    make_scenario_suite,
)


def _document(title: str = "Synthetic") -> PolicyDocument:
    return PolicyDocument(
        document_id="document-1",
        title=title,
        source_type="bundled_sample",
        pages=(PolicyPage(page=1, text="Meals capped", start=0, end=12),),
        document_sha256=HASH,
    )


def _compile_request(title: str = "Synthetic") -> CompilePolicyRequest:
    return CompilePolicyRequest(document=_document(title))


def _evaluation_request() -> EvaluatePolicyRequest:
    return EvaluatePolicyRequest(
        policy=make_policy(),
        contract=make_policy_contract(),
        suite=make_scenario_suite(),
        inputs=make_inputs(),
        engine_version="1.0",
    )


def _evaluation_report(report_id: str = "evaluation-1") -> EvaluationReport:
    return EvaluationReport(
        report_id=report_id,
        inputs=make_inputs(),
        engine_version="1.0",
        results=(),
        coverage=CoverageSnapshot(),
    )


@pytest.mark.asyncio
async def test_async_fake_consumes_results_and_callbacks_in_script_order() -> None:
    first = PolicyCompilation(policy=make_policy(policy_id="policy-first"))

    async def second(request: CompilePolicyRequest) -> PolicyCompilation:
        return PolicyCompilation(
            policy=make_policy(policy_id=f"policy-{request.document.title.lower()}")
        )

    fake = FakePolicyCompiler((first, second))

    returned_first = await fake.compile(_compile_request("First"))
    returned_second = await fake.compile(_compile_request("Second"))

    assert returned_first.policy.policy_id == "policy-first"
    assert returned_second.policy.policy_id == "policy-second"
    assert [request.document.title for request in fake.requests] == ["First", "Second"]
    assert fake.calls == 2
    assert returned_first is not first
    assert returned_first.policy is not first.policy


@pytest.mark.asyncio
async def test_queue_copies_typed_results_before_the_caller_can_replace_nested_data() -> (
    None
):
    compilation = PolicyCompilation(policy=make_policy(policy_id="queued-policy"))
    fake = FakePolicyCompiler()
    fake.queue(compilation)
    object.__setattr__(compilation, "policy", make_policy(policy_id="mutated-policy"))

    returned = await fake.compile(_compile_request())

    assert returned.policy.policy_id == "queued-policy"


@pytest.mark.asyncio
async def test_request_history_is_a_deep_snapshot_independent_of_the_input() -> None:
    request = _compile_request("Original")
    fake = FakePolicyCompiler((PolicyCompilation(policy=make_policy()),))

    await fake.compile(request)
    object.__setattr__(request, "document", _document("Changed"))

    assert fake.requests[0].document.title == "Original"
    assert fake.requests[0] is not request
    assert fake.requests[0].document is not request.document


@pytest.mark.asyncio
async def test_invalid_request_is_not_recorded_and_does_not_consume_the_script() -> (
    None
):
    expected = PolicyCompilation(policy=make_policy())
    fake = FakePolicyCompiler((expected,))

    with pytest.raises(ValidationError):
        await fake.compile(_document())  # type: ignore[arg-type]

    assert fake.requests == []
    assert await fake.compile(_compile_request()) == expected


@pytest.mark.asyncio
async def test_exhaustion_is_a_fixed_safe_workflow_error() -> None:
    fake = FakePolicyCompiler()

    with pytest.raises(WorkflowError) as exc_info:
        await fake.compile(_compile_request("secret sentinel"))

    assert exc_info.value.public_error.code == "INTERNAL_ERROR"
    assert "secret sentinel" not in str(exc_info.value)
    assert fake.calls == 1


@pytest.mark.asyncio
async def test_scripted_exception_is_raised_without_wrapping_or_replacement() -> None:
    scripted = RuntimeError("test-only-stage-failure")
    fake = FakePolicyCompiler((scripted,))

    with pytest.raises(RuntimeError) as exc_info:
        await fake.compile(_compile_request())

    assert exc_info.value is scripted


@pytest.mark.asyncio
async def test_callback_result_is_revalidated_as_the_declared_public_model() -> None:
    fake = FakePolicyCompiler((lambda _request: _document(),))

    with pytest.raises(ValidationError):
        await fake.compile(_compile_request())


def test_sync_fake_accepts_sync_callback_and_rejects_awaitable_callback_result() -> (
    None
):
    request = _evaluation_request()
    expected = _evaluation_report("sync-result")
    fake = FakeEvaluationEngine((lambda captured: expected,))

    returned = fake.evaluate(request)

    assert returned == expected
    assert returned is not expected

    async def invalid_async_callback(
        _request: EvaluatePolicyRequest,
    ) -> EvaluationReport:
        return expected

    fake.queue(invalid_async_callback)
    with pytest.raises(WorkflowError) as exc_info:
        fake.evaluate(request)
    assert exc_info.value.public_error.code == "INTERNAL_ERROR"


@pytest.mark.asyncio
async def test_scenario_planner_keeps_three_finite_scripts_and_histories_separate() -> (
    None
):
    other_hash = "b" * 64
    initial_batch = ScenarioBatch(candidates=(make_scenario_candidate(),))
    targeted_batch = ScenarioBatch(
        candidates=(make_scenario_candidate(candidate_id="candidate-targeted"),)
    )
    expected_suite = make_scenario_suite()
    planner = FakeScenarioPlanner()
    planner.queue_initial(initial_batch)
    planner.queue_targeted(targeted_batch)
    planner.queue_suite(
        lambda request: expected_suite.model_copy(
            update={
                "document_sha256": request.document_sha256,
                "policy_contract_sha256": request.policy_contract_sha256,
                "rule_set_sha256": request.rule_set_sha256,
                "engine_version": request.engine_version,
                "seed": request.seed,
            }
        )
    )
    initial_request = GenerateInitialScenariosRequest(
        policy=make_policy(), contract=make_policy_contract(), seed=41
    )
    targeted_request = GenerateTargetedScenariosRequest(
        policy=make_policy(),
        contract=make_policy_contract(),
        seed=42,
        existing_candidates=initial_batch.candidates,
        coverage=CoverageSnapshot(),
    )
    suite_request = AssembleSuiteRequest(
        suite_id="suite-1",
        document_sha256=other_hash,
        policy_contract_sha256=other_hash,
        rule_set_sha256=other_hash,
        engine_version="dynamic-engine",
        seed=43,
        candidates=initial_batch.candidates + targeted_batch.candidates,
    )

    assert await planner.generate_initial(initial_request) == initial_batch
    assert await planner.generate_targeted(targeted_request) == targeted_batch
    assembled = planner.assemble_suite(suite_request)
    assert assembled.seed == 43
    assert assembled.document_sha256 == other_hash
    assert assembled.policy_contract_sha256 == other_hash
    assert assembled.rule_set_sha256 == other_hash
    assert assembled.engine_version == "dynamic-engine"
    assert planner.initial_requests == [initial_request]
    assert planner.targeted_requests == [targeted_request]
    assert planner.suite_requests == [suite_request]
    assert (planner.initial_calls, planner.targeted_calls, planner.assembly_calls) == (
        1,
        1,
        1,
    )


def test_callable_helpers_use_typed_requests_results_and_finite_scripts() -> None:
    metrics_request = MetricsRequest(
        evaluation=_evaluation_report(),
        findings={"report_id": "findings-1", "inputs": make_inputs(), "findings": ()},
    )
    metrics = MetricsReport(
        inputs=make_inputs(),
        scenario_count=0,
        effect_states={},
        assertions={},
        unique_finding_count=0,
        coverage=CoverageSnapshot(),
    )
    fake_metrics = FakeMetrics((metrics,))
    create_request = CreateRunRequest(
        source_type="bundled_sample", title="Sample", sample_id="sample-1"
    )
    document = _document()
    fake_ingest = FakeIngest((document,))

    assert fake_metrics(metrics_request) == metrics
    assert fake_metrics.requests == [metrics_request]
    assert fake_ingest(create_request) == document
    assert fake_ingest.requests == [create_request]
    assert fake_metrics.calls == fake_ingest.calls == 1


@pytest.mark.parametrize(
    ("factory", "protocol"),
    [
        (FakePolicyCompiler, PolicyCompiler),
        (FakeEvaluationEngine, EvaluationEngine),
        (FakeFindingAnalyzer, FindingAnalyzer),
        (FakeRevisionPlanner, RevisionPlanner),
        (FakeRevisionApplier, RevisionApplier),
        (FakeRegressionAnalyzer, RegressionAnalyzer),
        (FakeScenarioPlanner, ScenarioPlanner),
    ],
)
def test_every_stage_fake_matches_its_runtime_protocol(
    factory: Callable[..., Any], protocol: type[Any]
) -> None:
    assert isinstance(factory(), protocol)


def test_queue_rejects_non_result_non_exception_non_callback() -> None:
    fake = FakePolicyCompiler()

    with pytest.raises(TypeError, match="scripted outcome"):
        fake.queue(_document())
