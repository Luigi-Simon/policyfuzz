"""Offline native OASIS regression: run with MiroFish's Python environment.

Uses synthetic, deterministic participant actions, never a model or provider.
All native files/logs stay in a temporary directory.
"""

import asyncio
import importlib.util
import json
import os
import sqlite3
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def load(name):
    path = ROOT / "backend/app/v2/sandbox" / f"{name}.py"
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


async def check(directory):
    from oasis.environment.env import OasisEnv
    from oasis.environment.env_action import LLMAction
    from oasis.social_platform.platform import Platform
    from oasis.social_platform.typing import ActionType

    load("peer_feed").install_peer_feed(Platform)
    guard = load("native_guard")
    database = str(Path(directory) / "native.db")
    platform = Platform(database, recsys_type="random")
    platform.sandbox_clock.time_step = 0
    env = OasisEnv(None, platform, database_path=database, semaphore=4)
    progress = guard.NativeProgress(directory, 2)
    guard.guard_environment(env, progress, action_timeout=5, step_timeout=15)
    env.platform_task = asyncio.create_task(platform.running())

    class Participant:
        def __init__(self, index):
            self.social_agent_id = index

        async def call(self, action, message=None):
            key = await env.channel.write_to_receive_queue(
                (self.social_agent_id, message, action)
            )
            _, _, result = await env.channel.read_from_send_queue(key)
            assert result["success"], result
            return result

        async def perform_action_by_llm(self):
            # The native dispatcher, channel, clock and SQLite are real. Only
            # model decisions are replaced with deterministic synthetic actions.
            feed = await self.call(ActionType.REFRESH)
            post = feed["posts"][0]
            if self.social_agent_id == 0 and platform.sandbox_clock.time_step == 1:
                await self.call(
                    ActionType.QUOTE_POST,
                    (post["post_id"], "Synthetic proposal about schedules."),
                )
            else:
                await self.call(
                    ActionType.CREATE_COMMENT,
                    (post["post_id"], "Synthetic question about safeguards."),
                )

    try:
        for index in range(10):
            assert (
                await platform.sign_up(
                    index,
                    (f"user_{index}", f"Participant {index}", "Synthetic test persona"),
                )
            )["success"]
            assert (await platform.create_post(index, f"Synthetic opening {index}"))[
                "success"
            ]
        platform.sandbox_clock.time_step = 1
        participants = {Participant(i): LLMAction() for i in range(10)}
        for _ in range(2):
            await env.step(participants)
        assert progress.data["completed_rounds"] == 2
        assert progress.data["actions_count"] == 20
        with sqlite3.connect(database) as db:
            counts = {
                name: db.execute("SELECT COUNT(*) FROM " + name).fetchone()[0]
                for name in ("user", "post", "comment")
            }
            assert counts == {"user": 10, "post": 11, "comment": 19}, counts
        await env.close()
        progress.finish("completed")
        print(
            json.dumps(
                {
                    "mode": "offline_native",
                    "completed_rounds": 2,
                    "completed_actions": 20,
                    "counts": counts,
                    "model_calls": 0,
                }
            )
        )
    finally:
        if not env.platform_task.done():
            env.platform_task.cancel()
        await asyncio.gather(env.platform_task, return_exceptions=True)
        platform.db.close()


if __name__ == "__main__":
    with tempfile.TemporaryDirectory(prefix="policyfuzz-native-check-") as directory:
        os.chdir(directory)
        asyncio.run(check(directory))
