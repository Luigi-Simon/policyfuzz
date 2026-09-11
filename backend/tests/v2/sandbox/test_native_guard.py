import asyncio
import json
from types import SimpleNamespace

import pytest

from app.v2.sandbox.native_guard import NativeProgress, guard_environment


class Environment:
    def __init__(self):
        self.llm_semaphore = asyncio.Semaphore(1)
        self.platform = SimpleNamespace(
            sandbox_clock=SimpleNamespace(get_time_step=lambda: "1"),
            pl_utils=SimpleNamespace(_record_trace=lambda *args, **kwargs: None),
        )
        self.platform_task = asyncio.create_task(asyncio.Event().wait())
        self.cancelled = False

    async def _perform_llm_action(self, agent):
        return await agent.perform_action_by_llm()

    async def step(self, actions):
        try:
            await asyncio.gather(
                *(self._perform_llm_action(agent) for agent in actions)
            )
        finally:
            self.cancelled = True

    async def reset(self):
        return None

    async def close(self):
        self.platform_task.cancel()
        await asyncio.gather(self.platform_task, return_exceptions=True)


@pytest.mark.asyncio
async def test_platform_crash_cancels_waiting_agents_without_hanging(tmp_path):
    env = Environment()
    progress = NativeProgress(tmp_path, 2)
    guard_environment(env, progress, action_timeout=0.5, step_timeout=1)
    started = asyncio.Event()

    class Agent:
        social_agent_id = 2

        async def perform_action_by_llm(self):
            started.set()
            await asyncio.Event().wait()

    task = asyncio.create_task(env.step({Agent(): None}))
    await started.wait()
    env.platform_task.cancel()
    with pytest.raises(RuntimeError, match="native_platform_stopped"):
        await asyncio.wait_for(task, 0.2)
    assert env.cancelled
    assert not progress.data["pending_agents"]


@pytest.mark.asyncio
async def test_hanging_action_is_bounded_and_identified(tmp_path):
    env = Environment()
    progress = NativeProgress(tmp_path, 2)
    guard_environment(env, progress, action_timeout=0.01, step_timeout=1)

    class Agent:
        social_agent_id = 7

        async def perform_action_by_llm(self):
            await asyncio.Event().wait()

    with pytest.raises(TimeoutError, match="native_agent_timeout:7"):
        await env.step({Agent(): None})
    assert progress.data["error"] == "native_agent_timeout:7"
    await env.close()


@pytest.mark.asyncio
async def test_progress_counts_real_actions_and_only_finished_rounds(tmp_path):
    progress = NativeProgress(tmp_path, 2)
    env = Environment()
    guard_environment(env, progress, action_timeout=0.1, step_timeout=1)
    progress.start_round(1)
    env.platform.pl_utils._record_trace(1, "create_comment", {"comment_id": 4}, 1)
    env.platform.pl_utils._record_trace(1, "refresh", {"posts": []}, 1)
    progress.finish_round(1)
    progress.start_round(2)
    env.platform.pl_utils._record_trace(2, "quote_post", {"new_post_id": 9}, 2)
    progress.finish("stopped")
    saved = json.loads((tmp_path / "policyfuzz_progress.json").read_text())
    assert saved["completed_rounds"] == 1 and saved["active_round"] == 2
    assert saved["actions_count"] == 2 and saved["status"] == "stopped"
    assert saved["updated_at"] and saved["completed_at"]
    records = [
        json.loads(x)
        for x in (tmp_path / "twitter/actions.jsonl").read_text().splitlines()
    ]
    assert len([r for r in records if "action_type" in r]) == 2
    assert not any(r.get("event_type") == "simulation_end" for r in records)
    await env.close()


@pytest.mark.asyncio
async def test_action_queue_does_not_spend_timeout_while_waiting_for_semaphore(
    tmp_path,
):
    env = Environment()
    progress = NativeProgress(tmp_path, 1)
    guard_environment(env, progress, action_timeout=0.1, step_timeout=1)

    class Agent:
        def __init__(self, agent_id):
            self.social_agent_id = agent_id

        async def perform_action_by_llm(self):
            await asyncio.sleep(0.06)

    await env.step({Agent(1): None, Agent(2): None, Agent(3): None})
    assert progress.data["pending_agents"] == []
    await env.close()


@pytest.mark.asyncio
async def test_caller_cancellation_cleans_running_and_queued_agents(tmp_path):
    env = Environment()
    progress = NativeProgress(tmp_path, 1)
    guard_environment(env, progress, action_timeout=5, step_timeout=10)
    entered = asyncio.Event()

    class Agent:
        def __init__(self, number):
            self.social_agent_id = number

        async def perform_action_by_llm(self):
            entered.set()
            await asyncio.Event().wait()

    task = asyncio.create_task(env.step({Agent(1): None, Agent(2): None}))
    await entered.wait()
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await asyncio.wait_for(task, 0.2)
    assert progress.data["pending_agents"] == []
    assert progress.data["completed_rounds"] == 0
    await env.close()
