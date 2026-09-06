"""Application ownership and production graphs built from frozen stage protocols."""

from collections.abc import Awaitable, Callable
from contextvars import ContextVar
from dataclasses import dataclass
from pathlib import Path
from typing import TypeVar

from app.core.config import Settings
from app.core.errors import LLMConfigurationError
from app.core.hashing import canonical_sha256
from app.core.llm import RetryingLLMClient
from app.domain.models import (
    AssembleSuiteRequest,
    CreateRunRequest,
    GenerateInitialScenariosRequest,
    GenerateTargetedScenariosRequest,
    GenerationConfig,
    LLMRequest,
    LLMResponse,
    PromptHash,
    RunManifest,
    RunMode,
    RunRecord,
    ScenarioBatch,
    ScenarioSuite,
)
from app.domain.protocols import LLMClient, ScenarioPlanner
from app.workflow.coordinator import RunCoordinator
from app.workflow.errors import InvalidRunCommandError
from app.workflow.store import RunStore
from app.workflow.task_runner import AsyncTaskRunner, TaskRunner
from app.workflow.types import Clock, SystemClock

T = TypeVar("T")
_ROOT = Path(__file__).resolve().parents[2]
_FEATURES = Path(__file__).resolve().parent / "features"


class _UnavailableLLM:
    async def complete_json(self, request: LLMRequest) -> LLMResponse:
        raise LLMConfigurationError()


class ScopedScenarioPlanner:
    """Bind a stateful specialist to one stored run, never to the whole server."""

    def __init__(self, factory: Callable[[RunManifest], ScenarioPlanner]):
        self.factory = factory
        self._instances: dict[str, ScenarioPlanner] = {}
        self._current: ContextVar[ScenarioPlanner] = ContextVar("scenario_planner")

    def discard(self, run_id: str) -> None:
        self._instances.pop(run_id, None)

    def clear(self) -> None:
        self._instances.clear()

    async def execute(
        self, manifest: RunManifest, work: Callable[[], Awaitable[T]]
    ) -> T:
        if manifest.run_id not in self._instances:
            self._instances[manifest.run_id] = self.factory(manifest)
        token = self._current.set(self._instances[manifest.run_id])
        try:
            return await work()
        finally:
            self._current.reset(token)

    async def generate_initial(
        self, request: GenerateInitialScenariosRequest
    ) -> ScenarioBatch:
        return await self._current.get().generate_initial(request)

    async def generate_targeted(
        self, request: GenerateTargetedScenariosRequest
    ) -> ScenarioBatch:
        return await self._current.get().generate_targeted(request)

    def assemble_suite(self, request: AssembleSuiteRequest) -> ScenarioSuite:
        return self._current.get().assemble_suite(request)


@dataclass
class AppContainer:
    coordinator: RunCoordinator
    task_runner: TaskRunner
    settings: Settings
    engine_version: str
    close_provider: Callable[[], Awaitable[None]] | None = None
    scenario_scope: ScopedScenarioPlanner | None = None
    validate_create: Callable[[CreateRunRequest], None] | None = None

    @property
    def provider_configured(self) -> bool:
        return _provider_is_configured(self.settings)

    async def execute(self, run_id: str, work: Callable[[], Awaitable[T]]) -> T:
        if self.scenario_scope is None:
            return await work()
        record = await self.coordinator.store.get(run_id)
        return await self.scenario_scope.execute(record.manifest, work)

    async def aclose(self) -> None:
        try:
            await self.coordinator.store.aclose()
            await self.task_runner.aclose()
        finally:
            if self.scenario_scope is not None:
                self.scenario_scope.clear()
            if self.close_provider is not None:
                close, self.close_provider = self.close_provider, None
                await close()


def make_manifest_factory(
    settings: Settings, clock: Clock
) -> Callable[[str, RunMode], RunManifest]:
    """Commit source content under repository-relative names, never local paths."""
    from app.features.evaluation.engine import ENGINE_VERSION
    from app.features.fuzzing import exploratory_prompt_commitment

    engine_files = (
        "assertions.py",
        "compliance.py",
        "engine.py",
        "errors.py",
        "findings.py",
        "metrics.py",
        "patches.py",
        "predicates.py",
        "regression.py",
        "resolution.py",
        "rule_validation.py",
        "signatures.py",
    )
    engine_hash = canonical_sha256(
        {
            name: (_FEATURES / "evaluation" / name).read_text(encoding="utf-8")
            for name in engine_files
        }
    )
    prompt_hashes = tuple(
        PromptHash(
            prompt_name=name,
            prompt_sha256=canonical_sha256(
                {"source": (_FEATURES / path).read_text(encoding="utf-8")}
            ),
        )
        for name, path in (
            ("policy_prompt_source_v1", "policy/prompts.py"),
            ("revision_prompt_source_v1", "policy/revision.py"),
        )
    ) + (exploratory_prompt_commitment(),)

    def factory(run_id: str, mode: RunMode) -> RunManifest:
        return RunManifest(
            manifest_id="manifest-" + run_id,
            run_id=run_id,
            engine_version=ENGINE_VERSION,
            engine_sha256=engine_hash,
            prompt_hashes=prompt_hashes,
            provider=settings.llm_provider,
            model_identifier=settings.llm_model or "unconfigured",
            generation_config=GenerationConfig(),
            random_seed=42,
            started_at=clock.wall_now(),
            mode=mode,
        )

    return factory


def _provider_is_configured(settings: Settings) -> bool:
    if not settings.llm_model:
        return False
    if settings.llm_provider == "openai":
        return bool(settings.openai_api_key)
    return bool(settings.aws_region)


def build_container(
    settings: Settings | None = None,
    *,
    llm: LLMClient | None = None,
    clock: Clock | None = None,
    cached_loader: Callable[[CreateRunRequest], RunRecord] | None = None,
    cache_path: Path | None = None,
) -> AppContainer:
    from app.features.evaluation.engine import (
        ENGINE_VERSION,
        DeterministicEvaluationEngine,
    )
    from app.features.evaluation.findings import DeterministicFindingAnalyzer
    from app.features.evaluation.metrics import compute_metrics
    from app.features.evaluation.patches import DeterministicRevisionApplier
    from app.features.evaluation.regression import DeterministicRegressionAnalyzer
    from app.features.fuzzing import DefaultScenarioPlanner
    from app.features.policy.compiler import LLMPolicyCompiler
    from app.features.policy.ingest import ingest_policy_text, load_bundled_policy
    from app.features.policy.revision import LLMRevisionPlanner

    settings = settings if settings is not None else Settings()
    clock = clock if clock is not None else SystemClock()
    close_provider = None
    configured = _provider_is_configured(settings)
    supplied_llm = llm is not None
    if llm is None and settings.app_mode == "live" and configured:
        if settings.llm_provider == "openai":
            from app.core.llm_openai import OpenAILLMClient

            adapter = OpenAILLMClient.from_settings(settings)
        else:
            from app.core.llm_bedrock import BedrockLLMClient

            adapter = BedrockLLMClient.from_settings(settings)
        close_provider = adapter.aclose
        llm = adapter
    if llm is None:
        llm = _UnavailableLLM()
    if not isinstance(llm, RetryingLLMClient):
        llm = RetryingLLMClient(llm)

    sample_path = _ROOT / "samples" / "policies" / "development-policy.txt"

    def validate(command: CreateRunRequest) -> None:
        if (
            command.source_type == "bundled_sample"
            and command.sample_id != "development-policy"
        ):
            raise InvalidRunCommandError()
        if settings.app_mode == "live" and not configured and not supplied_llm:
            raise LLMConfigurationError()

    def ingest(command: CreateRunRequest):
        validate(command)
        if command.source_type == "bundled_sample":
            return load_bundled_policy(sample_path)
        return ingest_policy_text(
            title=command.title, text=command.text, source_type=command.source_type
        )

    if cached_loader is None:
        path = (
            cache_path
            if cache_path is not None
            else _ROOT / "samples" / "cached-demo" / "run-record.json"
        )
        if path.is_file():

            def cached_loader(command):
                return RunRecord.model_validate_json(path.read_bytes())

    scope = ScopedScenarioPlanner(
        lambda manifest: DefaultScenarioPlanner(llm, manifest=manifest)
    )
    store = RunStore(clock, ttl_seconds=settings.run_ttl_seconds)
    runner = AsyncTaskRunner(store, clock, cleanup=scope.discard)
    coordinator = RunCoordinator(
        store=store,
        clock=clock,
        policy_compiler=LLMPolicyCompiler(llm),
        scenario_planner=scope,
        evaluation_engine=DeterministicEvaluationEngine(),
        finding_analyzer=DeterministicFindingAnalyzer(),
        revision_planner=LLMRevisionPlanner(llm),
        revision_applier=DeterministicRevisionApplier(),
        regression_analyzer=DeterministicRegressionAnalyzer(),
        ingest=ingest,
        metrics=compute_metrics,
        manifest_factory=make_manifest_factory(settings, clock),
        draft_severity="medium",
        mode=settings.app_mode,
        cached_loader=cached_loader,
    )
    return AppContainer(
        coordinator=coordinator,
        task_runner=runner,
        settings=settings,
        engine_version=ENGINE_VERSION,
        close_provider=close_provider,
        scenario_scope=scope,
        validate_create=validate,
    )
