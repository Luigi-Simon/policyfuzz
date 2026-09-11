"""Server-owned live configuration and client lifetime; fixture mode needs no keys."""

from contextlib import AsyncExitStack
from pathlib import Path
from typing import Literal

from pydantic import AliasChoices, Field, SecretStr

from app.core.config import Settings

from .fixtures import FixtureSandboxService
from .workflow import WorkflowOrchestrator, WorkflowUnavailable
from .workflow_fixture import FixtureWorkflowJudge
from .workflow_models import WorkflowHealth


class V2Settings(Settings):
    llm_model: str | None = Field(
        default=None, validation_alias=AliasChoices("LLM_MODEL", "LLM_MODEL_NAME")
    )
    openai_api_key: SecretStr | None = Field(
        default=None,
        repr=False,
        validation_alias=AliasChoices("OPENAI_API_KEY", "LLM_API_KEY"),
    )
    mirofish_base_url: str = Field(
        default="http://127.0.0.1:5002", validation_alias="MIROFISH_BASE_URL"
    )
    judge_response_format: Literal["json_schema", "json_object"] = Field(
        default="json_schema", validation_alias="JUDGE_RESPONSE_FORMAT"
    )
    judge_model: str | None = Field(default=None, validation_alias="JUDGE_MODEL")
    judge_timeout_seconds: int = Field(
        default=150, ge=1, le=600, validation_alias="JUDGE_TIMEOUT_SECONDS"
    )
    judge_max_repairs: int = Field(
        default=2, ge=0, le=2, validation_alias="JUDGE_MAX_REPAIRS"
    )

    @property
    def live_available(self):
        return bool(self.llm_model and self.openai_api_key and self.mirofish_base_url)


class WorkflowRuntime:
    def __init__(self, settings):
        self.settings = settings
        self._resources = AsyncExitStack()
        self._sandbox = self._judge = None
        self.orchestrator = WorkflowOrchestrator(
            sandbox_factory=self.sandbox,
            judge_factory=self.judge,
            judge_timeout_seconds=settings.judge_timeout_seconds + 5,
            diagnostics_path=Path(__file__).resolve().parents[2]
            / "cache"
            / "v2-diagnostics.sqlite",
        )

    def _require_live(self):
        if not self.settings.live_available:
            raise WorkflowUnavailable(
                "Live Sandbox and Judge services are not configured."
            )

    async def health(self, *, client=None):
        import httpx

        configured = self.settings.live_available
        engine = "not_checked"
        if configured:

            async def check(http):
                response = await http.get(
                    self.settings.mirofish_base_url.rstrip("/")
                    + "/api/policyfuzz/v2/health",
                    timeout=2,
                )
                response.raise_for_status()
                body = response.json()
                return body.get("success") is True and body.get("data") == {
                    "service": "policyfuzz_v2",
                    "status": "ok",
                }

            try:
                if client is not None:
                    reachable = await check(client)
                else:
                    async with httpx.AsyncClient() as http:
                        reachable = await check(http)
                engine = "reachable" if reachable else "unavailable"
            except (httpx.HTTPError, ValueError, TypeError, AttributeError):
                engine = "unavailable"
        return WorkflowHealth(
            live_configured=configured,
            mirofish=engine,
            provider="configured_not_checked" if configured else "not_configured",
            detail="Backend is responsive. Engine reachability does not prove simulation progress. Provider readiness is not tested; no model call was made.",
        )

    async def run(self, request):
        if request.mode == "live":
            self._require_live()
        return await self.orchestrator.run(request)

    def sandbox(self, request):
        if request.mode == "fixture":
            return FixtureSandboxService(request.fixture_name)
        self._require_live()
        if self._sandbox is None:
            from .sandbox.language import OpenAILanguageTools
            from .sandbox.service import MiroFishSandboxService
            from .sandbox.transport import MiroFishClient

            transport = MiroFishClient(base_url=self.settings.mirofish_base_url)
            self._resources.push_async_callback(transport.close)
            language = OpenAILanguageTools(
                model=self.settings.llm_model,
                api_key=self.settings.openai_api_key.get_secret_value(),
                base_url=self.settings.llm_base_url,
                timeout_seconds=self.settings.llm_timeout_seconds,
            )
            self._resources.push_async_callback(language.close)
            self._sandbox = MiroFishSandboxService(transport, language)
        return self._sandbox

    def judge(self, mode):
        if mode == "fixture":
            return FixtureWorkflowJudge()
        self._require_live()
        if self._judge is None:
            from .judge.client import OpenAIJudgeClient
            from .judge.service import JudgeAgentService

            judge_settings = self.settings.model_copy(
                update={
                    "llm_model": self.settings.judge_model or self.settings.llm_model
                }
            )
            client = OpenAIJudgeClient.from_settings(
                judge_settings, response_format=self.settings.judge_response_format
            )
            self._resources.push_async_callback(client.aclose)
            self._judge = JudgeAgentService(
                client,
                max_repairs=self.settings.judge_max_repairs,
                timeout_seconds=self.settings.judge_timeout_seconds,
            )
        return self._judge

    async def close(self):
        await self._resources.aclose()
        self._sandbox = self._judge = None
