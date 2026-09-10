"""Native MiroFish/OASIS runner wrapper: schedule the exact roster each round."""

import asyncio
import importlib.util
import json
import os
import random
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import ClassVar


def main():
    root = Path(os.environ["POLICYFUZZ_MIROFISH_ROOT"])
    source = root / "backend/scripts/run_twitter_simulation.py"
    spec = importlib.util.spec_from_file_location("mirofish_native_twitter", source)
    native = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = native
    spec.loader.exec_module(native)
    from oasis.social_platform.platform import Platform

    # Load without importing PolicyFuzz's app package into MiroFish's process.
    peer_spec = importlib.util.spec_from_file_location(
        "policyfuzz_peer_feed", Path(__file__).with_name("peer_feed.py")
    )
    peer_feed = importlib.util.module_from_spec(peer_spec)
    peer_spec.loader.exec_module(peer_feed)
    peer_feed.install_peer_feed(Platform)
    # Some local MiroFish forks add conflict missions. Seed personas must remain
    # independent of Metric findings, so disable that optional injection here.
    if hasattr(native, "inject_conflict_directives"):
        native.inject_conflict_directives = lambda *args, **kwargs: None

    class ExplicitRosterRunner(native.TwitterSimulationRunner):
        AVAILABLE_ACTIONS: ClassVar = [
            native.ActionType.CREATE_COMMENT,
            native.ActionType.QUOTE_POST,
        ]

        def _record(self, **event):
            path = Path(self.simulation_dir) / "twitter/actions.jsonl"
            path.parent.mkdir(exist_ok=True)
            with path.open("a", encoding="utf-8") as output:
                output.write(
                    json.dumps({"timestamp": datetime.now(UTC).isoformat(), **event})
                    + "\n"
                )

        def _get_active_agents_for_round(self, env, current_hour, round_num):
            if round_num:
                self._record(
                    event_type="round_end", round=round_num, simulated_hours=round_num
                )
            self._record(
                event_type="round_start",
                round=round_num + 1,
                simulated_hour=current_hour,
            )
            agents = list(env.agent_graph.get_agents())
            if len(agents) != self.config["policyfuzz_v2"]["configured_count"]:
                raise RuntimeError("OASIS roster differs from configured count")
            return agents

        async def run(self, max_rounds=None):
            seed = self.config["policyfuzz_v2"].get("random_seed")
            if seed is not None:
                random.seed(seed)
            # Let the native runner exit after its rounds. The extension does not
            # use its interactive interview server, which can otherwise stay alive.
            self.wait_for_commands = False
            await super().run(max_rounds=max_rounds)
            rounds = min(
                max_rounds or 20, self.config["time_config"]["total_simulation_hours"]
            )
            self._record(event_type="round_end", round=rounds, simulated_hours=rounds)
            self._record(event_type="simulation_end", total_rounds=rounds)

    native.TwitterSimulationRunner = ExplicitRosterRunner
    native.setup_signal_handlers()
    asyncio.run(native.main())


if __name__ == "__main__":
    main()
