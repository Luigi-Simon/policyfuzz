"""Native MiroFish/OASIS runner wrapper: schedule the exact roster each round."""

import asyncio
import importlib.util
import os
import random
import signal
import sqlite3
import sys
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
    guard_spec = importlib.util.spec_from_file_location(
        "policyfuzz_native_guard", Path(__file__).with_name("native_guard.py")
    )
    guard = importlib.util.module_from_spec(guard_spec)
    guard_spec.loader.exec_module(guard)
    # Some local MiroFish forks add conflict missions. Seed personas must remain
    # independent of Metric findings, so disable that optional injection here.
    if hasattr(native, "inject_conflict_directives"):
        native.inject_conflict_directives = lambda *args, **kwargs: None

    class ExplicitRosterRunner(native.TwitterSimulationRunner):
        AVAILABLE_ACTIONS: ClassVar = [
            native.ActionType.CREATE_COMMENT,
            native.ActionType.QUOTE_POST,
        ]

        def _get_active_agents_for_round(self, env, current_hour, round_num):
            agents = list(env.agent_graph.get_agents())
            if len(agents) != self.config["policyfuzz_v2"]["configured_count"]:
                raise RuntimeError("OASIS roster differs from configured count")
            return agents

        async def run(self, max_rounds=None):
            settings = self.config["policyfuzz_v2"]
            seed = settings.get("random_seed")
            if seed is not None:
                random.seed(seed)
            self.wait_for_commands = False
            rounds = min(
                max_rounds or 20, self.config["time_config"]["total_simulation_hours"]
            )
            progress = guard.NativeProgress(self.simulation_dir, rounds)
            original_make = native.oasis.make

            def make(*args, **kwargs):
                env = original_make(*args, **kwargs)
                guard.guard_environment(
                    env,
                    progress,
                    action_timeout=settings.get("action_timeout_seconds", 60),
                    step_timeout=settings.get("step_timeout_seconds", 180),
                )
                return env

            native.oasis.make = make
            status, error = "failed", None
            try:
                await super().run(max_rounds=max_rounds)
                if progress.data["completed_rounds"] != rounds:
                    raise RuntimeError("native_incomplete_rounds")
                status = "completed"
            except asyncio.CancelledError:
                status = "stopped"
                raise
            except Exception as exc:
                error = (
                    progress.data["error"]
                    or f"native_runner_failed:{type(exc).__name__}"
                )
                raise
            finally:
                native.oasis.make = original_make
                env = getattr(self, "env", None)
                if env is not None:
                    try:
                        async with asyncio.timeout(3):
                            if not env.platform_task.done():
                                await env.close()
                    except Exception:  # noqa: BLE001 - always clean up a failed native environment
                        env.platform_task.cancel()
                    finally:
                        await asyncio.gather(env.platform_task, return_exceptions=True)
                        try:
                            env.platform.db.close()
                        except sqlite3.Error:
                            pass
                handler = getattr(self, "ipc_handler", None)
                if handler:
                    handler.update_status(
                        "stopped" if status == "completed" else status
                    )
                progress.finish(status, error)

    native.TwitterSimulationRunner = ExplicitRosterRunner

    async def run_main():
        loop, task = asyncio.get_running_loop(), asyncio.current_task()
        previous = {
            sig: signal.getsignal(sig) for sig in (signal.SIGTERM, signal.SIGINT)
        }
        registered = set()
        # The upstream handler only signals its interview loop; cancellation
        # must reach an active step so pending agents and SQLite can be closed.
        for sig in (signal.SIGTERM, signal.SIGINT):
            try:
                loop.add_signal_handler(sig, task.cancel)
                registered.add(sig)
            except NotImplementedError:  # Windows event loops use signal.signal.
                signal.signal(sig, lambda *_: loop.call_soon_threadsafe(task.cancel))
        try:
            await native.main()
        except asyncio.CancelledError:
            pass
        finally:
            for sig in (signal.SIGTERM, signal.SIGINT):
                if sig in registered:
                    loop.remove_signal_handler(sig)
                signal.signal(sig, previous[sig])

    asyncio.run(run_main())


if __name__ == "__main__":
    main()
