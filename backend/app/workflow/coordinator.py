"""Bounded, injected orchestration; no specialist internals or provider calls."""

import asyncio
from collections.abc import Callable
from datetime import timedelta
from uuid import uuid4

from pydantic import ValidationError

from app.core.artifacts import (
    complete_payload_projection,
    make_artifact_envelope,
    semantic_payload_projection,
)
from app.core.errors import to_public_error
from app.core.hashing import canonical_sha256
from app.domain.models import (
    AnalyzeFindingsRequest,
    ApplyRevisionRequest,
    ArtifactRef,
    AssembleSuiteRequest,
    Assertion,
    CompareRevisionRequest,
    CompilePolicyRequest,
    ConfirmContractRequest,
    ConfirmRevisionRequest,
    ContractConfirmation,
    CreateRunRequest,
    CreateRunResponse,
    EvaluatePolicyRequest,
    Finding,
    FindingReport,
    FindingsConfirmation,
    GenerateInitialScenariosRequest,
    GenerateTargetedScenariosRequest,
    Invariant,
    InvariantSummary,
    MetricsReport,
    MetricsRequest,
    PatchApplicationResult,
    PolicyCompilation,
    PolicyContract,
    PolicyDocument,
    PolicyIR,
    ProposeRevisionRequest,
    PublicError,
    RevisionConfirmation,
    RevisionOperationSummary,
    RuleSummary,
    RunManifest,
    RunMode,
    RunRecord,
    RunView,
    ScenarioBatch,
    SelectFindingsRequest,
    Severity,
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
from app.workflow.errors import (
    InvalidRunCommandError,
    InvalidRunStateError,
    StaleArtifactError,
    WorkflowError,
)
from app.workflow.state_machine import allowed_actions, transition_to
from app.workflow.store import RunStore
from app.workflow.types import Clock, StoredRun
from app.workflow.validation import (
    input_hashes,
    minimum_coverage,
    require,
    reviewable,
    validate_batch,
    validate_comparison,
    validate_evaluation,
    validate_findings,
    validate_metrics,
    validate_proposal,
    validate_suite,
)
from app.workflow.views import to_run_view


def digest(payload):
    return canonical_sha256(complete_payload_projection(payload))


def semantic(payload):
    return canonical_sha256(semantic_payload_projection(payload))


def rule_summary(rule):
    return RuleSummary(
        rule_id=rule.rule_id,
        revision=rule.revision,
        description=rule.description,
        when=rule.when,
        effects=rule.effects,
        overrides=rule.overrides,
        citations=(rule.provenance,),
        confidence_percent=rule.confidence_percent,
    )


class RunCoordinator:
    def __init__(
        self,
        *,
        store: RunStore,
        clock: Clock,
        policy_compiler: PolicyCompiler,
        scenario_planner: ScenarioPlanner,
        evaluation_engine: EvaluationEngine,
        finding_analyzer: FindingAnalyzer,
        revision_planner: RevisionPlanner,
        revision_applier: RevisionApplier,
        regression_analyzer: RegressionAnalyzer,
        ingest: Callable[[CreateRunRequest], PolicyDocument],
        metrics: Callable[[MetricsRequest], MetricsReport],
        manifest_factory: Callable[[str, RunMode], RunManifest],
        draft_severity: Severity,
        mode: RunMode = "live",
        run_id_factory: Callable[[], str] | None = None,
        cached_loader: Callable[[CreateRunRequest], RunRecord] | None = None,
        recording_demo: bool = False,
    ) -> None:
        self.store, self.clock = store, clock
        self.policy_compiler, self.scenario_planner = policy_compiler, scenario_planner
        self.evaluation_engine, self.finding_analyzer = (
            evaluation_engine,
            finding_analyzer,
        )
        self.revision_planner, self.revision_applier = (
            revision_planner,
            revision_applier,
        )
        self.regression_analyzer = regression_analyzer
        self.ingest, self.metrics, self.manifest_factory = (
            ingest,
            metrics,
            manifest_factory,
        )
        if draft_severity not in {"low", "medium", "high", "critical"} or mode not in {
            "live",
            "cached",
        }:
            raise InvalidRunCommandError()
        self.draft_severity, self.mode = draft_severity, mode
        self.run_id_factory = run_id_factory or (lambda: str(uuid4()))
        self.cached_loader = cached_loader
        if not isinstance(recording_demo, bool) or (
            recording_demo and mode != "cached"
        ):
            raise InvalidRunCommandError()
        self.recording_demo = recording_demo
        self._tasks: dict[str, set[asyncio.Task]] = {}
        self._used_ids: set[str] = set()

    def _command(self, model, command):
        try:
            return model.model_validate(command)
        except (ValueError, TypeError):
            raise InvalidRunCommandError() from None

    async def create_run(self, command: CreateRunRequest) -> CreateRunResponse:
        command = self._command(CreateRunRequest, command)
        if self.recording_demo and (
            command.source_type != "bundled_sample"
            or command.sample_id != "development-policy"
        ):
            raise InvalidRunCommandError()
        if self.mode == "cached" and not self.recording_demo:
            return await self._create_cached(command)
        run_id = self.run_id_factory()
        if run_id in self._used_ids:
            raise InvalidRunCommandError()
        self._used_ids.add(run_id)
        manifest = RunManifest.model_validate(self.manifest_factory(run_id, self.mode))
        if manifest.run_id != run_id or manifest.mode != self.mode:
            raise InvalidRunCommandError()
        now = self.clock.wall_now()
        record = StoredRun(
            run_id=run_id,
            stage="queued",
            manifest=manifest,
            created_at=now,
            expires_at=now + timedelta(seconds=3600),
            source_request=command,
        )
        record = self._append(record, "run_manifest", manifest)
        await self.store.create(record)
        return CreateRunResponse(run_id=run_id)

    def _append(self, record, kind, payload):
        if kind == "scenario_suite":
            require(
                not any(a.artifact_type == "scenario_suite" for a in record.artifacts)
            )
        parents = tuple(
            ArtifactRef(
                artifact_type=a.artifact_type,
                artifact_sha256=a.artifact_sha256,
                semantic_sha256=a.semantic_sha256,
            )
            for a in record.artifacts
        )
        envelope = make_artifact_envelope(
            artifact_type=kind,
            payload=payload,
            parent_refs=parents,
            run_manifest_id=record.manifest.manifest_id,
        )
        return record.model_copy(update={"artifacts": record.artifacts + (envelope,)})

    async def _move(self, record, stage, *, artifacts=(), **changes):
        def change(current):
            result = current.model_copy(update=changes)
            for kind, payload in artifacts:
                result = self._append(result, kind, payload)
            artifact = result.artifacts[-1] if artifacts else None
            reference = (
                ArtifactRef(
                    artifact_type=artifact.artifact_type,
                    artifact_sha256=artifact.artifact_sha256,
                    semantic_sha256=artifact.semantic_sha256,
                )
                if artifact
                else None
            )
            return transition_to(result, stage, clock=self.clock, artifact=reference)

        return await self.store.mutate(record.run_id, record.version, change)

    async def _at(self, run_id, stage):
        record = await self.store.get(run_id)
        if record.stage != stage:
            raise InvalidRunStateError(
                current_stage=record.stage,
                allowed_actions=allowed_actions(record.stage),
            )
        return record

    async def _failure(self, record, error):
        if isinstance(error, WorkflowError):
            public = error.public_error
        elif isinstance(error, (ValueError, TypeError, ValidationError)):
            public = PublicError(
                code="MALFORMED_MODEL_OUTPUT",
                message="A workflow stage returned invalid evidence.",
            )
        else:
            public = to_public_error(error)
        # Always replace free text, even a stage-supplied PublicError.
        public = PublicError(
            code=public.code,
            message="The workflow could not complete this stage.",
            retryable=public.retryable,
        )
        try:
            await self._move(
                record,
                "failed",
                error=public,
                pending_confirmation=None,
                source_request=None,
            )
        except WorkflowError:
            pass  # Deleted/expired/superseded records must never be recreated.

    async def start(self, run_id: str) -> None:
        record = await self._at(run_id, "queued")
        record = await self._move(record, "ingesting")
        task = asyncio.current_task()
        self._tasks.setdefault(run_id, set()).add(task)
        try:
            document = PolicyDocument.model_validate(self.ingest(record.source_request))
            record = await self._move(
                record,
                "extracting",
                artifacts=(("policy_document", document),),
                source_request=None,
            )
            compilation = PolicyCompilation.model_validate(
                await self.policy_compiler.compile(
                    CompilePolicyRequest(document=document)
                )
            )
            policy = compilation.policy
            if (
                policy.document_sha256 != document.document_sha256
                or policy.kind != "compiled_baseline"
                or policy.review_status != "provisional"
                or not 3 <= len(compilation.invariant_drafts) <= 5
            ):
                raise ValueError("invalid provisional compilation")
            policy = PolicyIR.model_validate(
                policy.model_copy(
                    update={
                        "unsupported_clauses": tuple(
                            c.model_copy(update={"review_status": "provisional"})
                            for c in policy.unsupported_clauses
                        )
                    }
                )
            )
            invariants = tuple(
                InvariantSummary(
                    invariant_id=i.invariant_id,
                    description=i.description,
                    when=i.when,
                    assertion=i.assertion,
                    severity=self.draft_severity,
                )
                for i in compilation.invariant_drafts
            )
            dimensions = frozenset(
                [i.assertion.dimension for i in invariants]
                + [e.dimension for r in policy.rules for e in r.effects]
            )
            pending = ContractConfirmation(
                baseline_policy_id=policy.policy_id,
                baseline_policy_sha256=digest(policy),
                document_sha256=document.document_sha256,
                rules=tuple(rule_summary(r) for r in policy.rules),
                invariants=invariants,
                required_dimensions=dimensions,
            )
            record = await self._move(
                record,
                "awaiting_contract",
                artifacts=(("policy_ir", policy),),
                pending_confirmation=pending,
            )
        except asyncio.CancelledError:
            await self._failure(record, RuntimeError())
            raise
        except Exception as exc:  # noqa: BLE001 - contain all injected stage failures
            await self._failure(record, exc)
        finally:
            self._tasks.get(run_id, set()).discard(task)
            if not self._tasks.get(run_id):
                self._tasks.pop(run_id, None)

    async def confirm_contract(
        self, run_id: str, command: ConfirmContractRequest
    ) -> RunView:
        command = self._command(ConfirmContractRequest, command)
        record = await self._at(run_id, "awaiting_contract")
        if command.decision == "reject":
            await self._move(record, "contract_rejected", pending_confirmation=None)
            return await self.get_run(run_id)
        pending = record.pending_confirmation
        if (
            command.baseline_policy_id != pending.baseline_policy_id
            or command.baseline_policy_sha256 != pending.baseline_policy_sha256
        ):
            raise StaleArtifactError()
        return await self._baseline(record, command)

    async def get_run(self, run_id: str) -> RunView:
        return to_run_view(await self.store.get(run_id))

    async def delete_run(self, run_id: str) -> None:
        await self.store.delete(run_id)
        for task in self._tasks.pop(run_id, set()):
            if task is not asyncio.current_task():
                task.cancel()

    @staticmethod
    def _payload(record, kind, *, first=False):
        artifacts = record.artifacts if first else reversed(record.artifacts)
        return next(a.payload for a in artifacts if a.artifact_type == kind)

    def _evaluate(self, record, policy, contract, suite):
        request = EvaluatePolicyRequest(
            policy=policy,
            contract=contract,
            suite=suite,
            inputs=input_hashes(policy, contract, suite, record.manifest),
            engine_version=record.manifest.engine_version,
        )
        return validate_evaluation(self.evaluation_engine.evaluate(request), request)

    def _assemble(self, record, policy, contract, candidates):
        request = AssembleSuiteRequest(
            suite_id="suite-" + record.run_id,
            document_sha256=policy.document_sha256,
            policy_contract_sha256=digest(contract),
            rule_set_sha256=semantic(policy),
            engine_version=record.manifest.engine_version,
            seed=record.manifest.random_seed,
            candidates=candidates,
        )
        suite = validate_suite(
            self.scenario_planner.assemble_suite(request),
            policy,
            contract,
            record.manifest,
            suite_id=request.suite_id,
            candidate_count=len(candidates),
        )
        for scenario in suite.scenarios:
            sources = tuple(
                c
                for c in candidates
                if c.facts == scenario.facts and c.partition == scenario.partition
            )
            require(bool(sources))
            require(set(scenario.origins) <= {o for c in sources for o in c.origins})
            require(
                all(
                    a in tuple(a for c in sources for a in c.assertions)
                    for a in scenario.assertions
                )
            )
            require(
                set(scenario.target_rule_ids)
                <= {r for c in sources for r in c.target_rule_ids}
            )
            require(
                set(scenario.target_invariant_ids)
                <= {i for c in sources for i in c.target_invariant_ids}
            )
            require(scenario.protected == any(c.protected for c in sources))
        statistics = suite.statistics
        require(statistics.rejected_count == len(statistics.rejections))
        require(
            statistics.duplicate_count
            == sum(r.reason_code == "duplicate" for r in statistics.rejections)
        )
        if statistics.generated_count:
            require(
                statistics.generated_count
                == len(suite.scenarios) + statistics.rejected_count
            )
        else:
            require(not statistics.rejections)
        # ScenarioBatch contains accepted candidates only. Rejected generator
        # IDs first arrive here in the frozen statistics; they are not required
        # to masquerade as accepted inputs. Public projection keeps unknown IDs
        # out of visible evidence and retains their aggregate rejection count.
        return suite

    async def _baseline(self, record, command):
        policy = self._payload(record, "policy_ir")
        policy = PolicyIR.model_validate(
            policy.model_copy(
                update={
                    "review_status": "session_confirmed",
                    "unsupported_clauses": tuple(
                        c.model_copy(update={"review_status": "session_confirmed"})
                        for c in policy.unsupported_clauses
                    ),
                }
            )
        )
        invariants = tuple(
            Invariant(
                invariant_id=i.invariant_id,
                description=i.description,
                when=i.when,
                assertion=Assertion(
                    **i.assertion.model_dump(),
                    origin="session_confirmed",
                    source_invariant_id=i.invariant_id,
                ),
                severity=i.severity,
            )
            for i in command.invariants
        )
        contract = PolicyContract(
            contract_id="contract-"
            + canonical_sha256(
                {
                    "invariants": invariants,
                    "required_dimensions": command.required_dimensions,
                }
            ),
            invariants=invariants,
            required_dimensions=command.required_dimensions,
        )
        record = await self._move(
            record,
            "generating_initial_tests",
            artifacts=(("policy_ir", policy), ("policy_contract", contract)),
            pending_confirmation=None,
        )
        task = asyncio.current_task()
        self._tasks.setdefault(record.run_id, set()).add(task)
        try:
            initial = validate_batch(
                await self.scenario_planner.generate_initial(
                    GenerateInitialScenariosRequest(
                        policy=policy,
                        contract=contract,
                        seed=record.manifest.random_seed,
                        scenario_budget=10,
                    )
                ),
                10,
                policy,
                contract,
            )
            record = await self._move(record, "provisional_execution")
            candidates = initial.candidates
            suite = self._assemble(record, policy, contract, candidates)
            report = self._evaluate(record, policy, contract, suite)
            if not minimum_coverage(report):
                record = await self._move(
                    record,
                    "targeting_coverage",
                    artifacts=(("coverage_snapshot", report.coverage),),
                )
                budget = min(5, 15 - len(suite.scenarios))
                targeted = validate_batch(
                    await self.scenario_planner.generate_targeted(
                        GenerateTargetedScenariosRequest(
                            policy=policy,
                            contract=contract,
                            seed=record.manifest.random_seed,
                            scenario_budget=budget,
                            existing_candidates=candidates,
                            coverage=report.coverage,
                            targeted_cycle=1,
                        )
                    ),
                    budget,
                    policy,
                    contract,
                )
                # Bound the full assembly input too, including rejected initial candidates.
                candidates = candidates + targeted.candidates
                validate_batch(
                    ScenarioBatch(candidates=candidates), 15, policy, contract
                )
                suite = self._assemble(record, policy, contract, candidates)
                report = self._evaluate(record, policy, contract, suite)
            if not minimum_coverage(report):
                await self._move(
                    record,
                    "coverage_limit_exceeded",
                    artifacts=(("coverage_snapshot", report.coverage),),
                )
                return await self.get_run(record.run_id)
            record = await self._move(
                record, "freezing_suite", artifacts=(("scenario_suite", suite),)
            )
            record = await self._move(record, "baseline_execution")
            report = self._evaluate(record, policy, contract, suite)
            if not minimum_coverage(report):
                raise ValueError("frozen coverage changed")
            record = await self._move(
                record, "analyzing", artifacts=(("evaluation_report", report),)
            )
            findings = validate_findings(
                self.finding_analyzer.analyze(
                    AnalyzeFindingsRequest(
                        policy=policy, contract=contract, suite=suite, evaluation=report
                    )
                ),
                report,
                policy,
                contract,
            )
            metrics = validate_metrics(
                self.metrics(MetricsRequest(evaluation=report, findings=findings)),
                report,
                findings,
            )
            visible = reviewable(findings, suite)
            pending = (
                FindingsConfirmation(finding_ids=tuple(f.finding_id for f in visible))
                if visible
                else None
            )
            record = await self._move(
                record,
                "awaiting_finding_review" if visible else "completed_no_findings",
                artifacts=(("finding_report", findings), ("metrics_report", metrics)),
                pending_confirmation=pending,
            )
        except asyncio.CancelledError:
            await self._failure(record, RuntimeError())
            raise
        except Exception as exc:  # noqa: BLE001 - contain all injected stage failures
            await self._failure(record, exc)
        finally:
            self._tasks.get(record.run_id, set()).discard(task)
            if not self._tasks.get(record.run_id):
                self._tasks.pop(record.run_id, None)
        return await self.get_run(record.run_id)

    async def select_findings(
        self, run_id: str, command: SelectFindingsRequest
    ) -> RunView:
        command = self._command(SelectFindingsRequest, command)
        record = await self._at(run_id, "awaiting_finding_review")
        suite = self._payload(record, "scenario_suite")
        policy = self._payload(record, "policy_ir")
        contract = self._payload(record, "policy_contract")
        report = self._payload(record, "finding_report")
        visible = {f.finding_id: f for f in reviewable(report, suite)}
        if {d.finding_id for d in command.decisions} != visible.keys():
            raise InvalidRunCommandError()
        decisions = {d.finding_id: d for d in command.decisions}
        invariants = {i.invariant_id: i for i in contract.invariants}
        updated = []
        for finding in report.findings:
            decision = decisions.get(finding.finding_id)
            if decision is None:
                updated.append(finding)
                continue
            changes = {
                "review_status": "accepted"
                if decision.decision == "accept"
                else "rejected"
            }
            if decision.decision == "reject":
                if decision.reviewer_severity is not None:
                    raise InvalidRunCommandError()
            elif finding.invariant_id is not None:
                severity = invariants[finding.invariant_id].severity
                if (
                    decision.reviewer_severity is not None
                    and decision.reviewer_severity != severity
                ):
                    raise InvalidRunCommandError()
                changes.update(severity=severity, severity_origin="session_invariant")
            elif finding.finding_type in {"structural_gap", "conflict"}:
                if decision.reviewer_severity is None:
                    raise InvalidRunCommandError()
                changes.update(
                    severity=decision.reviewer_severity,
                    severity_origin="session_reviewer",
                )
            elif decision.reviewer_severity is not None:
                raise InvalidRunCommandError()
            updated.append(Finding.model_validate(finding.model_copy(update=changes)))
        reviewed = FindingReport.model_validate(
            report.model_copy(update={"findings": tuple(updated)})
        )
        accepted = tuple(
            f
            for f in reviewed.findings
            if f.review_status == "accepted" and f.finding_id in visible
        )
        record = await self._move(
            record,
            "drafting_revision" if accepted else "completed_no_revision",
            artifacts=(("finding_report", reviewed),),
            finding_decisions=command.decisions,
            decision_at=self.clock.wall_now(),
            pending_confirmation=None,
        )
        if not accepted:
            return await self.get_run(run_id)
        task = asyncio.current_task()
        self._tasks.setdefault(run_id, set()).add(task)
        try:
            # Trusted deterministic stage receives the full canonical suite. Its model
            # adapter must remove holdout cases and gold answers before an LLM call.
            request = ProposeRevisionRequest(
                policy=policy,
                contract=contract,
                suite=suite,
                findings=reviewed.model_copy(update={"findings": accepted}),
                decisions=tuple(d for d in command.decisions if d.decision == "accept"),
                document_sha256=policy.document_sha256,
                rule_set_sha256=semantic(policy),
                policy_contract_sha256=digest(contract),
                suite_sha256=digest(suite),
            )
            proposal = validate_proposal(
                await self.revision_planner.propose(request), request
            )
            rules = {r.rule_id: r for r in policy.rules}
            pending = RevisionConfirmation(
                proposal_id=proposal.proposal_id,
                operations=tuple(
                    RevisionOperationSummary(
                        operation=op,
                        before=None
                        if op.kind == "add_rule"
                        else rule_summary(rules[op.rule_id]),
                    )
                    for op in proposal.operations
                ),
                draft_policy_wording=proposal.draft_policy_wording,
            )
            record = await self._move(
                record,
                "awaiting_revision_confirmation",
                artifacts=(("revision_proposal", proposal),),
                pending_confirmation=pending,
            )
        except asyncio.CancelledError:
            await self._failure(record, RuntimeError())
            raise
        except Exception as exc:  # noqa: BLE001 - contain all injected stage failures
            await self._failure(record, exc)
        finally:
            self._tasks.get(run_id, set()).discard(task)
            if not self._tasks.get(run_id):
                self._tasks.pop(run_id, None)
        return await self.get_run(run_id)

    async def confirm_revision(
        self, run_id: str, command: ConfirmRevisionRequest
    ) -> RunView:
        command = self._command(ConfirmRevisionRequest, command)
        record = await self._at(run_id, "awaiting_revision_confirmation")
        proposal = self._payload(record, "revision_proposal")
        if command.proposal_id != proposal.proposal_id:
            raise StaleArtifactError()
        if command.decision == "reject":
            await self._move(record, "revision_rejected", pending_confirmation=None)
            return await self.get_run(run_id)
        policy = self._payload(record, "policy_ir")
        contract = self._payload(record, "policy_contract")
        suite = self._payload(record, "scenario_suite")
        before = self._payload(record, "evaluation_report")
        before_findings = self._payload(record, "finding_report")
        record = await self._move(
            record, "applying_revision", pending_confirmation=None
        )
        try:
            result = PatchApplicationResult.model_validate(
                self.revision_applier.apply_revision(
                    ApplyRevisionRequest(
                        policy=policy,
                        contract=contract,
                        suite=suite,
                        proposal=proposal,
                        confirmed_at=self.clock.wall_now(),
                    )
                )
            )
            require(result.proposal_id == proposal.proposal_id)
            if not result.applied:
                raise WorkflowError(result.error)
            revised = result.revised_policy
            require(
                revised.document_sha256 == policy.document_sha256
                and revised.review_status == "session_confirmed"
                and revised.kind == "structured_revision"
            )
            record = await self._move(
                record, "retesting", artifacts=(("policy_ir", revised),)
            )
            after = self._evaluate(record, revised, contract, suite)
            after_findings = validate_findings(
                self.finding_analyzer.analyze(
                    AnalyzeFindingsRequest(
                        policy=revised, contract=contract, suite=suite, evaluation=after
                    )
                ),
                after,
                revised,
                contract,
            )
            comparison_request = CompareRevisionRequest(
                baseline_policy=policy,
                revised_policy=revised,
                contract=contract,
                suite=suite,
                proposal=proposal,
                baseline_evaluation=before,
                revised_evaluation=after,
                baseline_findings=before_findings,
                revised_findings=after_findings,
            )
            comparison = validate_comparison(
                self.regression_analyzer.compare(comparison_request), comparison_request
            )
            record = await self._move(
                record,
                "complete",
                artifacts=(
                    ("evaluation_report", after),
                    ("finding_report", after_findings),
                    ("comparison_bundle", comparison),
                    ("metrics_report", comparison.revised_metrics),
                ),
            )
        except asyncio.CancelledError:
            await self._failure(record, RuntimeError())
            raise
        except Exception as exc:  # noqa: BLE001 - contain all injected stage failures
            await self._failure(record, exc)
        return await self.get_run(run_id)

    async def _create_cached(self, command):
        from app.workflow.validation import validate_cached_record

        if command.source_type != "bundled_sample":
            raise InvalidRunCommandError()
        if self.cached_loader is None:
            raise WorkflowError(
                PublicError(
                    code="PROVIDER_UNAVAILABLE",
                    message="Recorded demonstration is unavailable.",
                )
            )
        try:
            record = validate_cached_record(self.cached_loader(command))
        except Exception:  # noqa: BLE001 - cache loader is an injected trust boundary
            raise WorkflowError(
                PublicError(
                    code="HASH_MISMATCH",
                    message="Recorded demonstration could not be validated.",
                )
            ) from None
        run_id = self.run_id_factory()
        if run_id == record.run_id or run_id in self._used_ids:
            raise InvalidRunCommandError()
        from app.workflow.cache_replay import rebase_cached_record

        try:
            record = rebase_cached_record(record, run_id)
        except Exception:  # noqa: BLE001 - validate the complete replay graph before storage
            raise WorkflowError(
                PublicError(
                    code="HASH_MISMATCH",
                    message="Recorded demonstration could not be validated.",
                )
            ) from None
        self._used_ids.add(run_id)
        await self.store.create(record)
        return CreateRunResponse(run_id=run_id)
