"""Bound native OASIS waits and record progress without importing either app."""

import asyncio
import json
from datetime import UTC, datetime
from pathlib import Path


def now():
    return datetime.now(UTC).isoformat()


class NativeProgress:
    def __init__(self, directory, total_rounds):
        self.directory = Path(directory)
        self.data = {
            "status": "starting",
            "total_rounds": total_rounds,
            "active_round": 0,
            "completed_rounds": 0,
            "actions_count": 0,
            "pending_agents": [],
            "rounds": [],
            "error": None,
            "updated_at": now(),
            "completed_at": None,
        }
        self.save()

    def save(self):
        self.data["updated_at"] = now()
        path = self.directory / "policyfuzz_progress.json"
        temporary = path.with_suffix(".tmp")
        temporary.write_text(json.dumps(self.data), encoding="utf-8")
        temporary.replace(path)

    def record(self, **event):
        path = self.directory / "twitter/actions.jsonl"
        path.parent.mkdir(exist_ok=True)
        with path.open("a", encoding="utf-8") as output:
            output.write(json.dumps(dict(timestamp=now(), **event)) + "\n")

    def start_round(self, number):
        self.data.update(status="running", active_round=number)
        self.round_started_at = now()
        self.round_start_actions = self.data["actions_count"]
        self.record(event_type="round_start", round=number)
        self.save()

    def finish_round(self, number):
        self.data["completed_rounds"] = number
        self.data["rounds"].append(
            {
                "round": number,
                "started_at": self.round_started_at,
                "completed_at": now(),
                "actions_count": self.data["actions_count"] - self.round_start_actions,
            }
        )
        self.record(event_type="round_end", round=number, simulated_hours=number)
        self.save()

    def action(self, agent_id, action_type, action_info, step):
        # Seed openings and feed reads are not completed participant actions.
        action_type = getattr(action_type, "value", action_type)
        step = int(step) if step is not None else None
        if (
            step is None
            or step < 1
            or action_type not in {"create_post", "create_comment", "quote_post"}
        ):
            return
        self.data["actions_count"] += 1
        self.record(
            round=step,
            agent_id=agent_id,
            agent_name=f"Participant {agent_id + 1}",
            action_type=action_type,
            action_args=action_info,
            success=True,
        )
        self.save()

    def finish(self, status, error=None):
        self.data.update(
            status=status,
            error=error or self.data["error"],
            completed_at=now(),
            pending_agents=[],
        )
        if status == "completed":
            self.record(
                event_type="simulation_end",
                total_rounds=self.data["completed_rounds"],
                total_actions=self.data["actions_count"],
            )
        else:
            self.record(
                event_type="simulation_stopped"
                if status == "stopped"
                else "simulation_failed",
                error=self.data["error"],
            )
        self.save()


def guard_environment(env, progress, *, action_timeout=60, step_timeout=180):
    """Instrument only this owned subprocess's environment; no native edits."""
    original_step, original_reset = env.step, env.reset
    original_trace = env.platform.pl_utils._record_trace
    inflight = set()

    def trace(user_id, action_type, action_info, current_time=None):
        result = original_trace(user_id, action_type, action_info, current_time)
        progress.action(user_id, action_type, action_info, current_time)
        return result

    async def perform(agent):
        task = asyncio.current_task()
        inflight.add(task)
        agent_id = agent.social_agent_id
        try:
            # Queued agents receive their own full execution budget.
            async with env.llm_semaphore:
                progress.data["pending_agents"].append(agent_id)
                progress.save()
                try:
                    async with asyncio.timeout(action_timeout):
                        return await agent.perform_action_by_llm()
                except TimeoutError:
                    code = f"native_agent_timeout:{agent_id}"
                    progress.data["error"] = code
                    raise TimeoutError(code) from None
                finally:
                    progress.data["pending_agents"].remove(agent_id)
                    progress.save()
        finally:
            inflight.discard(task)

    async def guarded(operation):
        task = asyncio.create_task(operation)
        try:
            # reset() creates platform_task before signing up participants.
            await asyncio.sleep(0)
            platform = getattr(env, "platform_task", None)
            tasks = {task, platform} if platform else {task}
            done, _ = await asyncio.wait(
                tasks, timeout=step_timeout, return_when=asyncio.FIRST_COMPLETED
            )
            if platform in done:
                code = "native_platform_stopped"
                if not platform.cancelled() and platform.exception() is not None:
                    code = (
                        f"native_platform_failed:{type(platform.exception()).__name__}"
                    )
                progress.data["error"] = code
                raise RuntimeError(code)
            if task not in done:
                progress.data["error"] = "native_step_timeout"
                raise TimeoutError("native_step_timeout")
            return await task
        finally:
            # gather in upstream OASIS leaves sibling actions running after an
            # exception. Cancel our tracked actions as well as the step itself.
            remaining = {task, *inflight}
            for pending in remaining:
                if not pending.done():
                    pending.cancel()
            await asyncio.gather(*remaining, return_exceptions=True)

    async def reset():
        return await guarded(original_reset())

    async def step(actions):
        number = int(env.platform.sandbox_clock.get_time_step())
        if number > 0:
            progress.start_round(number)
        result = await guarded(original_step(actions))
        if number > 0:
            progress.finish_round(number)
        return result

    env.platform.pl_utils._record_trace = trace
    env._perform_llm_action = perform
    env.reset, env.step = reset, step
