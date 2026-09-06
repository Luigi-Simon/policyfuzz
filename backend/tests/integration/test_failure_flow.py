import asyncio

import pytest

from app.core.errors import LLMTransportError
from app.domain.models import ConfirmRevisionRequest, LLMError
from app.workflow.errors import RunNotFoundError, WorkflowError
from app.workflow.fake_stages import (
    FakeEvaluationEngine,
    FakePolicyCompiler,
    FakeRevisionPlanner,
)
from tests.workflow.coordinator_fixtures import (
    baseline,
    compilation,
    evaluate,
    harness,
    request,
    revision_harness,
    selection,
)


@pytest.mark.asyncio
@pytest.mark.parametrize("tamper", ["inputs", "trace", "coverage", "cases"])
async def test_tampered_evaluation_fails_without_authoritative_artifacts(tamper):
    def invalid(value):
        result = evaluate(value)
        if tamper == "inputs":
            return result.model_copy(
                update={
                    "inputs": result.inputs.model_copy(
                        update={"policy_sha256": "0" * 64}
                    )
                }
            )
        if tamper == "trace":
            return result.model_copy(
                update={
                    "results": (
                        result.results[0].model_copy(
                            update={
                                "trace": result.results[0].trace.model_copy(
                                    update={"trace_sha256": "0" * 64}
                                )
                            }
                        ),
                    )
                    + result.results[1:]
                }
            )
        if tamper == "coverage":
            return result.model_copy(
                update={"coverage": result.coverage.model_copy(update={"evidence": ()})}
            )
        return result.model_copy(update={"results": result.results[:-1]})

    coordinator, fakes = harness(evaluation_engine=FakeEvaluationEngine([invalid]))
    view = await baseline(coordinator)
    assert view.stage == "failed"
    record = await fakes.store.get(view.run_id)
    assert not any(a.artifact_type == "evaluation_report" for a in record.artifacts)


@pytest.mark.asyncio
async def test_zero_drafts_fail_safely():
    coordinator, _fakes = harness(
        policy_compiler=FakePolicyCompiler(
            [lambda c: compilation(c).model_copy(update={"invariant_drafts": ()})]
        )
    )
    created = await coordinator.create_run(request())
    await coordinator.start(created.run_id)
    view = await coordinator.get_run(created.run_id)
    assert view.stage == "failed" and view.error.code == "MALFORMED_MODEL_OUTPUT"
    assert "Untrusted rationale" not in view.model_dump_json()


@pytest.mark.asyncio
async def test_later_provider_failure_preserves_completed_baseline():
    coordinator, fakes = revision_harness(
        revision_planner=FakeRevisionPlanner(
            [RuntimeError("raw_prompt PRIVATE provider_api_key")]
        )
    )
    view = await baseline(coordinator)
    before = await fakes.store.get(view.run_id)
    view = await coordinator.select_findings(view.run_id, selection())
    after = await fakes.store.get(view.run_id)
    assert view.stage == "failed" and view.baseline_metrics is not None
    assert all(a in after.artifacts for a in before.artifacts)
    assert "PRIVATE" not in view.model_dump_json()


@pytest.mark.asyncio
async def test_provider_failure_preserves_safe_diagnostic_classification():
    coordinator, _fakes = harness(
        policy_compiler=FakePolicyCompiler(
            [
                LLMTransportError(
                    LLMError(code="authentication", operation="policy_extraction")
                )
            ]
        )
    )

    created = await coordinator.create_run(request())
    await coordinator.start(created.run_id)
    view = await coordinator.get_run(created.run_id)

    assert view.stage == "failed"
    assert view.error is not None
    assert view.error.code == "PROVIDER_UNAVAILABLE"
    assert view.error.error_id == "provider-authentication"
    assert view.error.retryable is False


@pytest.mark.asyncio
@pytest.mark.parametrize("action", ["delete", "expire"])
async def test_late_compilation_cannot_resurrect_deleted_or_expired_run(action):
    entered, release = asyncio.Event(), asyncio.Event()

    async def paused(value):
        entered.set()
        await release.wait()
        return compilation(value)

    coordinator, fakes = harness(policy_compiler=FakePolicyCompiler([paused]))
    created = await coordinator.create_run(request())
    task = asyncio.create_task(coordinator.start(created.run_id))
    await asyncio.wait_for(entered.wait(), 1)
    if action == "delete":
        await coordinator.delete_run(created.run_id)
    else:
        fakes.clock.tick = 3601
    release.set()
    await asyncio.gather(task, return_exceptions=True)
    with pytest.raises(RunNotFoundError):
        await fakes.store.get(created.run_id)


@pytest.mark.asyncio
async def test_duplicate_start_claims_before_compiler_await():
    entered, release = asyncio.Event(), asyncio.Event()

    async def paused(value):
        entered.set()
        await release.wait()
        return compilation(value)

    coordinator, fakes = harness(policy_compiler=FakePolicyCompiler([paused]))
    created = await coordinator.create_run(request())
    task = asyncio.create_task(coordinator.start(created.run_id))
    await asyncio.wait_for(entered.wait(), 1)
    with pytest.raises(WorkflowError):
        await coordinator.start(created.run_id)
    release.set()
    await task
    assert fakes.policy_compiler.calls == 1


@pytest.mark.asyncio
@pytest.mark.parametrize("tamper", ["suite", "proposal", "comparison"])
async def test_tampered_later_anchors_cannot_complete(tamper):
    from app.workflow.fake_stages import FakeRegressionAnalyzer, FakeScenarioPlanner
    from tests.workflow.coordinator_fixtures import assemble, batch, compare, proposal

    options = {}
    if tamper == "suite":
        options["scenario_planner"] = FakeScenarioPlanner(
            initial=[batch],
            suites=[
                lambda r: assemble(r).model_copy(update={"content_sha256": "0" * 64})
            ],
        )
    if tamper == "proposal":
        options["revision_planner"] = FakeRevisionPlanner(
            [lambda r: proposal(r).model_copy(update={"suite_sha256": "0" * 64})]
        )
    if tamper == "comparison":
        options["regression_analyzer"] = FakeRegressionAnalyzer(
            [
                lambda r: compare(r).model_copy(
                    update={
                        "baseline_inputs": r.baseline_evaluation.inputs.model_copy(
                            update={"engine_sha256": "0" * 64}
                        )
                    }
                )
            ]
        )
    coordinator, _fakes = revision_harness(**options)
    view = await baseline(coordinator)
    if tamper != "suite":
        view = await coordinator.select_findings(view.run_id, selection())
    if tamper == "comparison":
        view = await coordinator.confirm_revision(
            view.run_id,
            ConfirmRevisionRequest(proposal_id="proposal", decision="confirm"),
        )
    assert view.stage == "failed"


@pytest.mark.asyncio
async def test_stage_cannot_supply_authoritative_reviewer_severity():
    from app.workflow.fake_stages import FakeFindingAnalyzer
    from tests.workflow.coordinator_fixtures import one_finding

    def forged(value):
        report = one_finding(value)
        finding = report.findings[0].model_copy(
            update={
                "severity": "critical",
                "severity_origin": "session_reviewer",
                "review_status": "accepted",
            }
        )
        return report.model_copy(update={"findings": (finding,)})

    coordinator, _fakes = harness(finding_analyzer=FakeFindingAnalyzer([forged]))
    view = await baseline(coordinator)
    assert view.stage == "failed"


@pytest.mark.asyncio
async def test_invalid_suite_can_not_substitute_candidate_facts():
    from app.workflow.fake_stages import FakeScenarioPlanner
    from tests.workflow.coordinator_fixtures import assemble, batch, digest

    def substitute(value):
        suite = assemble(value)
        scenario = suite.scenarios[0]
        scenario = scenario.model_copy(
            update={"facts": scenario.facts.model_copy(update={"amount_minor": 999999})}
        )
        suite = suite.model_copy(
            update={"scenarios": (scenario,) + suite.scenarios[1:]}
        )
        return suite.model_copy(update={"content_sha256": digest(suite)})

    coordinator, _fakes = harness(
        scenario_planner=FakeScenarioPlanner(initial=[batch], suites=[substitute])
    )
    view = await baseline(coordinator)
    assert view.stage == "failed"


@pytest.mark.asyncio
async def test_comparison_counts_must_match_frozen_transition_evidence():
    from app.workflow.fake_stages import FakeRegressionAnalyzer
    from tests.workflow.coordinator_fixtures import compare

    def forged(value):
        result = compare(value)
        acceptance = result.acceptance.model_copy(
            update={
                "zero_protected_regressions": False,
                "patch_accepted": False,
                "counts": result.acceptance.counts.model_copy(
                    update={"protected_regressions": 7}
                ),
            }
        )
        return result.model_copy(update={"acceptance": acceptance})

    coordinator, _fakes = revision_harness(
        regression_analyzer=FakeRegressionAnalyzer([forged])
    )
    view = await baseline(coordinator)
    await coordinator.select_findings(view.run_id, selection())
    view = await coordinator.confirm_revision(
        view.run_id, ConfirmRevisionRequest(proposal_id="proposal", decision="confirm")
    )
    assert view.stage == "failed"


@pytest.mark.asyncio
async def test_applier_safe_failure_keeps_baseline_without_retesting():
    from app.domain.models import PatchApplicationResult, PublicError
    from app.workflow.fake_stages import FakeRevisionApplier

    failure = PatchApplicationResult(
        proposal_id="proposal",
        applied=False,
        error=PublicError(code="REVISION_INVALID", message="raw private reason"),
    )
    coordinator, fakes = revision_harness(
        revision_applier=FakeRevisionApplier([failure])
    )
    view = await baseline(coordinator)
    await coordinator.select_findings(view.run_id, selection())
    view = await coordinator.confirm_revision(
        view.run_id, ConfirmRevisionRequest(proposal_id="proposal", decision="confirm")
    )
    assert view.stage == "failed" and view.error.code == "REVISION_INVALID"
    assert view.baseline_metrics is not None
    assert "raw private reason" not in view.model_dump_json()
    assert fakes.evaluation_engine.calls == 2
    summaries = tuple(event.action_summary for event in view.events)
    assert "Revision application started." in summaries
    assert "Confirmed revision applied." not in summaries


@pytest.mark.asyncio
@pytest.mark.parametrize("citation_id", ["unknown-citation", "citation"])
async def test_stage_trace_rejects_unknown_or_substituted_citation(citation_id):
    from hashlib import sha256

    from app.domain.models import SourceSpan, TextRuleProvenance
    from tests.workflow.coordinator_fixtures import digest

    sentinel = "SYNTHETIC_HOLDOUT_CITATION_SENTINEL"

    def substituted(value):
        result = evaluate(value)
        span = SourceSpan(
            page=1,
            start=0,
            end=len(sentinel),
            quote=sentinel,
            quote_sha256=sha256(sentinel.encode()).hexdigest(),
        )
        provenance = TextRuleProvenance(citation_id=citation_id, span=span)
        first = result.results[0]
        trace = first.trace.model_copy(update={"source_citations": (provenance,)})
        trace = trace.model_copy(update={"trace_sha256": digest(trace)})
        return result.model_copy(
            update={
                "results": (first.model_copy(update={"trace": trace}),)
                + result.results[1:]
            }
        )

    coordinator, _fakes = harness(
        evaluation_engine=FakeEvaluationEngine([substituted, substituted])
    )
    view = await baseline(coordinator)
    assert view.stage == "failed"
    assert sentinel not in view.model_dump_json()
