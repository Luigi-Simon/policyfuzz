"""Orchestrates ingest → extract → compile → Person 3 fuzz / grade / swarm."""

from __future__ import annotations

from typing import Any

from app.config import Settings, get_settings
from app.contracts.common import now_iso
from app.contracts.mirofish import MiroFishLaunch
from app.contracts.run import RunRecord, SeedSpec
from app.contracts.scenario import ScenarioSuite
from app.llm import LLMAdapter
from app.plugins.evaluator import Evaluator
from app.plugins.loader import PluginError, load_plugin
from app.plugins.scenario_designer import ScenarioDesigner
from app.services.effectiveness import synthesize_effectiveness
from app.services.evaluate import RuleEvaluator
from app.services.extract import extract_policy_ir
from app.services.fuzz import FuzzDesigner
from app.services.ingest import ingest_bytes
from app.services.mirofish_bridge import build_mirofish_pack, launch_mirofish
from app.services.mirofish_runner import SwarmError, run_swarm
from app.services.revise import revise_policy_ir
from app.store import RunStore


class Coordinator:
    def __init__(
        self,
        store: RunStore | None = None,
        settings: Settings | None = None,
        llm: LLMAdapter | None = None,
        designer: ScenarioDesigner | None = None,
        evaluator: Evaluator | None = None,
    ):
        self.settings = settings or get_settings()
        self.store = store or RunStore(self.settings)
        self.llm = llm or LLMAdapter(self.settings)
        self.designer = designer if designer is not None else self._load_designer()
        self.evaluator = evaluator if evaluator is not None else self._load_evaluator()

    def _load_designer(self) -> ScenarioDesigner:
        if self.settings.scenario_designer:
            plugin = load_plugin(self.settings.scenario_designer)
            if not isinstance(plugin, ScenarioDesigner):
                raise PluginError(f"{self.settings.scenario_designer} is not a ScenarioDesigner")
            return plugin
        return FuzzDesigner(max_agents=self.settings.max_swarm_agents)

    def _load_evaluator(self) -> Evaluator:
        if self.settings.evaluator:
            plugin = load_plugin(self.settings.evaluator)
            if not isinstance(plugin, Evaluator):
                raise PluginError(f"{self.settings.evaluator} is not an Evaluator")
            return plugin
        return RuleEvaluator()

    def create_run(
        self,
        *,
        filename: str,
        payload: bytes,
        seed: SeedSpec | None = None,
        provenance: dict[str, str] | None = None,
    ) -> RunRecord:
        record = RunRecord(seed=self._cap_seed(seed or SeedSpec()))
        if provenance is not None:
            record.extra["policyfuzz_confirmation"] = dict(provenance)
        self.store.save(record)
        self.store.save_source_bytes(record.run_id, filename, payload)
        try:
            record.touch("ingesting", "Reading source document")
            self.store.save(record)
            record.document = ingest_bytes(filename, payload)

            record.touch("extracting", "Extracting cited rules")
            self.store.save(record)
            record.ir = extract_policy_ir(record.document, llm=self.llm)

            record.touch("compiling", "Compiling PolicyIR index")
            self.store.save(record)

            self._generate_scenarios(record)
            self._attach_mirofish(record, auto_launch=False)
            self._evaluate(record)
            self._score(record)

            if self.settings.mirofish_auto_swarm and self.settings.mirofish_base_url:
                self._run_swarm(record)
            elif self.settings.mirofish_auto_launch:
                self._attach_mirofish(record, auto_launch=True)
                self._score(record)

            self.store.save(record)
            return record
        except Exception as error:
            record.touch("failed", "Pipeline failed")
            record.error = str(error)
            self.store.save(record)
            return record

    def revise(self, run_id: str, instruction: str) -> RunRecord:
        record = self._require(run_id)
        if record.ir is None:
            raise ValueError("Run has no PolicyIR to revise")
        record.touch("extracting", "Revising PolicyIR")
        self.store.save(record)
        record.ir = revise_policy_ir(record.ir, instruction, llm=self.llm)
        record.suite = None
        record.evaluation = None
        record.effectiveness = None
        self._generate_scenarios(record)
        self._attach_mirofish(record, auto_launch=False)
        self._evaluate(record)
        self._score(record)
        record.error = None
        self.store.save(record)
        return record

    def attach_suite(self, run_id: str, suite: ScenarioSuite) -> RunRecord:
        record = self._require(run_id)
        if record.ir is None:
            raise ValueError("Compile PolicyIR before attaching scenarios")
        if suite.policy_id != record.ir.policy_id:
            raise ValueError("ScenarioSuite.policy_id does not match this run's PolicyIR")
        suite.policy_revision = record.ir.revision
        if suite.scenarios:
            suite.scenarios = suite.scenarios[: self.settings.max_swarm_agents]
            suite.population_size = min(
                suite.population_size or len(suite.scenarios),
                self.settings.max_swarm_agents,
            )
        record.suite = suite
        record.evaluation = None
        record.effectiveness = None
        self._attach_mirofish(record, auto_launch=self.settings.mirofish_auto_launch)
        self._evaluate(record)
        self._score(record)
        self.store.save(record)
        return record

    def rehearse(self, run_id: str, *, swarm: bool = True) -> RunRecord:
        """Person 3 entry: fuzz (if needed), grade, optionally run MiroFish, score."""
        record = self._require(run_id)
        if record.ir is None:
            raise ValueError("Compile PolicyIR before rehearsing")
        record.touch("rehearsing", "Person 3 rehearsing policy")
        self.store.save(record)
        if record.suite is None:
            self._generate_scenarios(record)
        self._attach_mirofish(record, auto_launch=False)
        self._evaluate(record)
        if swarm:
            if not self.settings.mirofish_base_url:
                record.error = "MIROFISH_BASE_URL is not set — scored from fuzz tests only"
                self._score(record)
            else:
                self._run_swarm(record)
        else:
            self._score(record)
        self.store.save(record)
        return record

    def _cap_seed(self, seed: SeedSpec) -> SeedSpec:
        if seed.population_size:
            seed.population_size = min(int(seed.population_size), self.settings.max_swarm_agents)
        else:
            seed.population_size = self.settings.max_swarm_agents
        return seed

    def _generate_scenarios(self, record: RunRecord) -> None:
        assert record.ir is not None
        record.touch("generating_scenarios", "Person 3 generating fuzz agents")
        self.store.save(record)
        record.suite = self.designer.generate(record.ir, record.seed)
        if record.suite.scenarios:
            record.suite.scenarios = record.suite.scenarios[: self.settings.max_swarm_agents]
            record.suite.population_size = min(
                record.suite.population_size or len(record.suite.scenarios),
                self.settings.max_swarm_agents,
            )

    def attach_mirofish(self, run_id: str, *, launch: bool = False) -> RunRecord:
        record = self._require(run_id)
        if record.ir is None:
            raise ValueError("Compile PolicyIR before building a MiroFish pack")
        self._attach_mirofish(record, auto_launch=launch)
        self.store.save(record)
        return record

    def _attach_mirofish(self, record: RunRecord, *, auto_launch: bool) -> None:
        assert record.ir is not None
        pack = build_mirofish_pack(
            record.ir,
            record.seed,
            record.suite,
            max_agents=self.settings.max_swarm_agents,
        )
        if auto_launch:
            if self.settings.mirofish_base_url:
                policy_name, policy_bytes = self._policy_bytes(record, pack)
                pack.launch = launch_mirofish(
                    pack,
                    policy_filename=policy_name,
                    policy_bytes=policy_bytes,
                    base_url=self.settings.mirofish_base_url,
                    timeout=self.settings.mirofish_timeout_seconds,
                )
            else:
                pack.launch = MiroFishLaunch(
                    attempted=True,
                    ok=False,
                    error="MIROFISH_BASE_URL is not set",
                    at=now_iso(),
                )
        record.mirofish = pack

    def _run_swarm(self, record: RunRecord) -> None:
        assert record.ir is not None
        self._attach_mirofish(record, auto_launch=False)
        assert record.mirofish is not None
        record.touch("rehearsing", "Running MiroFish swarm (≤12 live agents)")
        self.store.save(record)
        try:
            policy_name, policy_bytes = self._policy_bytes(record, record.mirofish)
            launch, capture = run_swarm(
                record.mirofish,
                policy_filename=policy_name,
                policy_bytes=policy_bytes,
                base_url=self.settings.mirofish_base_url,
                timeout=self.settings.mirofish_timeout_seconds,
                swarm_timeout=self.settings.mirofish_swarm_timeout_seconds,
                poll_seconds=self.settings.mirofish_poll_seconds,
                max_rounds=self.settings.mirofish_max_rounds,
                platform=self.settings.mirofish_platform,
                live_agents=self.settings.mirofish_live_agents,
                use_llm_profiles=self.settings.mirofish_use_llm_profiles,
            )
            record.mirofish.launch = launch
            record.extra["swarm"] = _trim_swarm(capture)
            record.error = None
        except (SwarmError, Exception) as error:
            record.mirofish.launch = MiroFishLaunch(
                attempted=True,
                ok=False,
                error=str(error),
                mirofish_url=self.settings.mirofish_base_url or None,
                at=now_iso(),
            )
            record.error = f"Swarm failed: {error}"
        self._score(record)

    def _evaluate(self, record: RunRecord) -> None:
        assert record.ir is not None
        if record.suite is None:
            return
        record.touch("evaluating", "Grading fuzz scenarios")
        self.store.save(record)
        record.evaluation = self.evaluator.evaluate(record.ir, record.suite)

    def _score(self, record: RunRecord) -> None:
        assert record.ir is not None
        if record.evaluation is None:
            if record.suite is None:
                record.touch("compiled", "PolicyIR ready")
                return
            self._evaluate(record)
        assert record.evaluation is not None
        record.effectiveness = synthesize_effectiveness(
            record.ir,
            record.evaluation,
            swarm=record.extra.get("swarm") if isinstance(record.extra.get("swarm"), dict) else None,
            llm=self.llm,
        )
        if record.mirofish and record.mirofish.launch.ok:
            record.touch("completed", f"Rehearsal complete — score {record.effectiveness.score}/100")
        else:
            record.touch(
                "completed",
                f"Fuzz rehearsal complete — score {record.effectiveness.score}/100",
            )

    def _policy_bytes(self, record: RunRecord, pack) -> tuple[str, bytes]:
        policy_name = record.document.filename if record.document else "policy.txt"
        policy_bytes = (
            record.document.text.encode("utf-8")
            if record.document
            else pack.seed_markdown.encode("utf-8")
        )
        return policy_name, policy_bytes

    def _require(self, run_id: str) -> RunRecord:
        record = self.store.get(run_id)
        if record is None:
            raise KeyError(run_id)
        return record


def _trim_swarm(capture: dict[str, Any]) -> dict[str, Any]:
    posts = (capture.get("posts") or [])[:80]
    comments = (capture.get("comments") or [])[:80]
    actions = (capture.get("actions") or [])[:120]
    interaction_verified = bool(comments)
    return {
        "project_id": capture.get("project_id"),
        "graph_id": capture.get("graph_id"),
        "simulation_id": capture.get("simulation_id"),
        "posts": posts,
        "comments": comments,
        "actions": actions,
        "duplicate_messages_rejected": int(capture.get("duplicate_messages_rejected") or 0),
        "interaction_verified": interaction_verified,
        "interaction_status": "verified" if interaction_verified else "posts_only",
        "agent_stats": capture.get("agent_stats"),
    }
