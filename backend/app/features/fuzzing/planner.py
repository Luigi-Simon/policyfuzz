"""Bounded adaptive implementation of the frozen ScenarioPlanner protocol."""

from __future__ import annotations

from app.core.artifacts import complete_payload_projection
from app.core.hashing import canonical_sha256
from app.domain.models import (
    AssembleSuiteRequest,
    GenerateInitialScenariosRequest,
    GenerateTargetedScenariosRequest,
    RunManifest,
    Scenario,
    ScenarioBatch,
    ScenarioCandidate,
    ScenarioRejection,
    ScenarioSuite,
    SuiteStatistics,
)
from app.domain.protocols import LLMClient
from app.features.fuzzing.canonicalize import (
    canonicalize_with_rejections,
    fact_sha256,
    materialize_scenario,
    scenario_semantic_sha256,
)
from app.features.fuzzing.constants import (
    INITIAL_EXPLORATORY_REQUEST,
    INITIAL_SCENARIO_BUDGET,
    MAX_SCENARIOS,
    MAX_TARGETED_SCENARIOS,
)
from app.features.fuzzing.exploratory import generate_exploratory_candidates
from app.features.fuzzing.synthesis import (
    build_initial_mechanical_candidates,
    build_targeted_mechanical_candidates,
    conditions_satisfied,
)

_CATEGORY_PRIORITY = {"normal": 0, "adversarial": 1, "boundary": 2}


class CoverageLimitExceededError(RuntimeError):
    """The caller attempted more than the single permitted adaptation cycle."""

    def __init__(self) -> None:
        super().__init__("COVERAGE_LIMIT_EXCEEDED")


class DefaultScenarioPlanner:
    """Per-run planner combining deterministic and optional scripted exploration."""

    def __init__(
        self, llm: LLMClient | None = None, *, manifest: RunManifest | None = None
    ) -> None:
        if (llm is None) != (manifest is None):
            raise ValueError("llm and manifest must be supplied together")
        self._llm = llm
        self._manifest = (
            RunManifest.model_validate(manifest) if manifest is not None else None
        )
        self._initial_called = False
        self._targeted_called = False
        self._rejections: list[ScenarioRejection] = []
        self._generated_count = 0
        self._duplicate_count = 0

    def _record(self, result) -> ScenarioBatch:
        self._rejections.extend(result.rejections)
        self._generated_count += result.generated_count
        self._duplicate_count += result.duplicate_count
        return result.batch

    @staticmethod
    def _attach_applicable_invariants(
        candidates: tuple[ScenarioCandidate, ...], request
    ) -> tuple[ScenarioCandidate, ...]:
        """Freeze Python-sourced confirmed assertions matched by each fact vector."""

        enriched: list[ScenarioCandidate] = []
        for candidate in candidates:
            assertions = {item.assertion_id: item for item in candidate.assertions}
            target_ids = set(candidate.target_invariant_ids)
            matched = tuple(
                item
                for item in request.contract.invariants
                if conditions_satisfied(item.when, candidate.facts)
            )
            for invariant in matched:
                existing = assertions.get(invariant.assertion.assertion_id)
                if existing is not None and existing != invariant.assertion:
                    raise ValueError("conflicting confirmed invariant assertion")
                assertions[invariant.assertion.assertion_id] = invariant.assertion
                target_ids.add(invariant.invariant_id)
            enriched.append(
                ScenarioCandidate.model_validate(
                    candidate.model_copy(
                        update={
                            "origins": candidate.origins
                            | (frozenset({"session"}) if matched else frozenset()),
                            "target_invariant_ids": tuple(sorted(target_ids)),
                            "assertions": tuple(
                                assertions[key] for key in sorted(assertions)
                            ),
                            "protected": candidate.protected or bool(matched),
                        }
                    )
                )
            )
        return tuple(enriched)

    async def generate_initial(
        self, request: GenerateInitialScenariosRequest
    ) -> ScenarioBatch:
        request = GenerateInitialScenariosRequest.model_validate(request)
        if self._initial_called:
            raise CoverageLimitExceededError()
        self._initial_called = True
        capacity = min(request.scenario_budget, INITIAL_SCENARIO_BUDGET)
        rule_ids = frozenset(rule.rule_id for rule in request.policy.rules)
        invariant_ids = frozenset(
            item.invariant_id for item in request.contract.invariants
        )
        mechanical = build_initial_mechanical_candidates(
            request.policy, request.contract, seed=request.seed
        )
        exploratory: tuple[ScenarioCandidate, ...] = ()
        if self._llm is not None and self._manifest is not None:
            exploratory = await generate_exploratory_candidates(
                self._llm,
                operation="scenario_generation",
                policy=request.policy,
                contract=request.contract,
                manifest=self._manifest,
                requested_rule_ids=rule_ids,
                requested_invariant_ids=invariant_ids,
                existing_scenarios=(),
                used_fact_sha256s=frozenset(),
                count=min(INITIAL_EXPLORATORY_REQUEST, capacity),
                seed=request.seed,
            )
        result = canonicalize_with_rejections(
            kind="initial",
            candidates=self._attach_applicable_invariants(
                mechanical + exploratory, request
            ),
            prior_rejections=(),
            policy=request.policy,
            contract=request.contract,
            capacity=capacity,
            requested_rule_ids=rule_ids,
            requested_invariant_ids=invariant_ids,
        )
        return self._record(result)

    async def generate_targeted(
        self, request: GenerateTargetedScenariosRequest
    ) -> ScenarioBatch:
        request = GenerateTargetedScenariosRequest.model_validate(request)
        if self._targeted_called:
            raise CoverageLimitExceededError()
        self._targeted_called = True
        capacity = min(
            request.scenario_budget,
            MAX_TARGETED_SCENARIOS,
            max(0, MAX_SCENARIOS - len(request.existing_candidates)),
        )
        known_rules = {rule.rule_id for rule in request.policy.rules}
        known_invariants = {item.invariant_id for item in request.contract.invariants}
        rule_ids = frozenset(request.coverage.missing_rule_ids) & known_rules
        invariant_ids = (
            frozenset(request.coverage.missing_invariant_ids) & known_invariants
        )
        if capacity == 0 or (not rule_ids and not invariant_ids):
            return ScenarioBatch(candidates=())
        used = frozenset(
            fact_sha256(item.facts) for item in request.existing_candidates
        )
        mechanical = build_targeted_mechanical_candidates(
            request.policy,
            request.contract,
            rule_ids=rule_ids,
            invariant_ids=invariant_ids,
            seed=request.seed,
        )
        exploratory: tuple[ScenarioCandidate, ...] = ()
        if self._llm is not None and self._manifest is not None:
            exploratory = await generate_exploratory_candidates(
                self._llm,
                operation="targeted_scenario_generation",
                policy=request.policy,
                contract=request.contract,
                manifest=self._manifest,
                requested_rule_ids=rule_ids,
                requested_invariant_ids=invariant_ids,
                existing_scenarios=tuple(
                    materialize_scenario(item) for item in request.existing_candidates
                ),
                used_fact_sha256s=used,
                count=capacity,
                seed=request.seed,
            )
        result = canonicalize_with_rejections(
            kind="targeted",
            candidates=self._attach_applicable_invariants(
                mechanical + exploratory, request
            ),
            prior_rejections=(),
            policy=request.policy,
            contract=request.contract,
            capacity=capacity,
            requested_rule_ids=rule_ids,
            requested_invariant_ids=invariant_ids,
            used_fact_sha256s=used,
        )
        return self._record(result)

    @staticmethod
    def _merge_same_scenario(
        left: ScenarioCandidate, right: ScenarioCandidate
    ) -> ScenarioCandidate:
        return left.model_copy(
            update={
                "category": max(
                    (left.category, right.category),
                    key=_CATEGORY_PRIORITY.__getitem__,
                ),
                "origins": left.origins | right.origins,
            }
        )

    def assemble_suite(self, request: AssembleSuiteRequest) -> ScenarioSuite:
        """Materialize, sort and hash the complete bounded suite projection."""

        request = AssembleSuiteRequest.model_validate(request)
        groups: dict[str, list[ScenarioCandidate]] = {}
        local_rejections: list[ScenarioRejection] = []
        for candidate in request.candidates:
            validated = ScenarioCandidate.model_validate(candidate)
            groups.setdefault(scenario_semantic_sha256(validated), []).append(validated)
        canonical: list[ScenarioCandidate] = []
        assembly_duplicates = 0
        for semantic_hash in sorted(groups):
            group = sorted(groups[semantic_hash], key=lambda item: item.candidate_id)
            merged = group[0]
            for duplicate in group[1:]:
                merged = self._merge_same_scenario(merged, duplicate)
                assembly_duplicates += 1
                local_rejections.append(
                    ScenarioRejection(
                        candidate_id=duplicate.candidate_id,
                        reason_code="duplicate",
                        duplicate_of="candidate-" + semantic_hash,
                    )
                )
            canonical.append(merged)
        canonical.sort(
            key=lambda item: (
                -int(item.protected),
                -_CATEGORY_PRIORITY[item.category],
                scenario_semantic_sha256(item),
            )
        )
        overflow = canonical[MAX_SCENARIOS:]
        canonical = canonical[:MAX_SCENARIOS]
        local_rejections.extend(
            ScenarioRejection(
                candidate_id=item.candidate_id,
                reason_code="budget_exceeded",
            )
            for item in overflow
        )
        scenarios: tuple[Scenario, ...] = tuple(
            sorted(
                (materialize_scenario(item) for item in canonical),
                key=lambda item: item.scenario_id,
            )
        )
        if not scenarios:
            raise ValueError("a frozen suite requires at least one scenario")
        rejections = tuple(
            sorted(
                (*self._rejections, *local_rejections),
                key=lambda item: (
                    item.candidate_id,
                    item.reason_code,
                    item.duplicate_of or "",
                ),
            )
        )
        generated_count = self._generated_count or len(request.candidates)
        suite = ScenarioSuite(
            suite_id=request.suite_id,
            content_sha256="0" * 64,
            seed=request.seed,
            document_sha256=request.document_sha256,
            policy_contract_sha256=request.policy_contract_sha256,
            rule_set_sha256=request.rule_set_sha256,
            engine_version=request.engine_version,
            scenarios=scenarios,
            statistics=SuiteStatistics(
                generated_count=generated_count,
                rejected_count=len(rejections),
                duplicate_count=self._duplicate_count + assembly_duplicates,
                rejections=rejections,
            ),
        )
        return ScenarioSuite.model_validate(
            suite.model_copy(
                update={
                    "content_sha256": canonical_sha256(
                        complete_payload_projection(suite)
                    )
                }
            )
        )
