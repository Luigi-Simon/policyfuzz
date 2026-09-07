"""Drive MiroFish past ontology: graph build → simulate → capture talk."""

from __future__ import annotations

import time
from typing import Any, Callable

import httpx

from app.contracts.mirofish import MiroFishLaunch, MiroFishPack
from app.services.mirofish_bridge import launch_mirofish

SleepFn = Callable[[float], None]


class SwarmError(RuntimeError):
    pass


def run_swarm(
    pack: MiroFishPack,
    *,
    policy_filename: str,
    policy_bytes: bytes,
    base_url: str,
    timeout: float = 120.0,
    swarm_timeout: float = 900.0,
    poll_seconds: float = 5.0,
    max_rounds: int = 8,
    platform: str = "twitter",
    live_agents: int = 12,
    use_llm_profiles: bool = False,
    client: httpx.Client | None = None,
    sleep: SleepFn = time.sleep,
) -> tuple[MiroFishLaunch, dict[str, Any]]:
    """Full rehearsal. Returns (launch metadata, capture dict for scoring)."""
    owns_client = client is None
    http = client or httpx.Client(timeout=timeout)
    deadline = time.monotonic() + swarm_timeout
    try:
        launch = pack.launch if pack.launch.ok and pack.launch.project_id else launch_mirofish(
            pack,
            policy_filename=policy_filename,
            policy_bytes=policy_bytes,
            base_url=base_url,
            timeout=timeout,
            client=http,
        )
        if not launch.ok or not launch.project_id:
            raise SwarmError(launch.error or "MiroFish ontology launch failed")
        project_id = launch.project_id
        graph_id = _existing_graph(http, base_url, project_id) or _build_graph(
            http, base_url, project_id, deadline, poll_seconds, sleep
        )
        simulation_id = _create_and_prepare(
            http,
            base_url,
            project_id,
            graph_id,
            deadline,
            poll_seconds,
            sleep,
            live_agents=live_agents,
            use_llm_profiles=use_llm_profiles,
        )
        _start_and_wait(http, base_url, simulation_id, max_rounds, platform, deadline, poll_seconds, sleep)
        capture = _capture(http, base_url, simulation_id)
        capture["project_id"] = project_id
        capture["graph_id"] = graph_id
        capture["simulation_id"] = simulation_id
        launch.mirofish_url = base_url.rstrip("/")
        return launch, capture
    finally:
        if owns_client:
            http.close()


def _existing_graph(http: httpx.Client, base_url: str, project_id: str) -> str | None:
    try:
        project = _get(http, base_url, f"/api/graph/project/{project_id}")
    except SwarmError:
        return None
    data = project.get("data") or {}
    graph_id = data.get("graph_id")
    status = str(data.get("status") or "")
    if graph_id and status in {"graph_completed", "completed", "ready"}:
        return str(graph_id)
    return None


def _build_graph(
    http: httpx.Client,
    base_url: str,
    project_id: str,
    deadline: float,
    poll_seconds: float,
    sleep: SleepFn,
) -> str:
    payload = _post(http, base_url, "/api/graph/build", json={"project_id": project_id})
    data = payload.get("data") or {}
    task_id = data.get("task_id")
    graph_id = data.get("graph_id")
    if task_id:
        result = _poll_task(http, base_url, task_id, deadline, poll_seconds, sleep)
        graph_id = (result or {}).get("graph_id") or graph_id
    if not graph_id:
        project = _get(http, base_url, f"/api/graph/project/{project_id}")
        graph_id = (project.get("data") or {}).get("graph_id")
    if not graph_id:
        raise SwarmError("MiroFish graph build finished without a graph_id")
    return str(graph_id)


def _create_and_prepare(
    http: httpx.Client,
    base_url: str,
    project_id: str,
    graph_id: str,
    deadline: float,
    poll_seconds: float,
    sleep: SleepFn,
    live_agents: int = 12,
    use_llm_profiles: bool = False,
) -> str:
    created = _post(
        http,
        base_url,
        "/api/simulation/create",
        json={"project_id": project_id, "graph_id": graph_id, "enable_twitter": True, "enable_reddit": False},
    )
    simulation_id = (created.get("data") or {}).get("simulation_id")
    if not simulation_id:
        raise SwarmError("MiroFish create simulation returned no simulation_id")
    prepared = _post(
        http,
        base_url,
        "/api/simulation/prepare",
        json={
            "simulation_id": simulation_id,
            "use_llm_for_profiles": use_llm_profiles,
            "parallel_profile_count": 2,
            "max_agents": live_agents,
        },
    )
    data = prepared.get("data") or {}
    if data.get("already_prepared") or data.get("status") in {"ready", "completed"}:
        return str(simulation_id)
    task_id = data.get("task_id")
    if task_id:
        _poll_until(
            lambda: _post(
                http,
                base_url,
                "/api/simulation/prepare/status",
                json={"task_id": task_id, "simulation_id": simulation_id},
            ),
            done=lambda body: (body.get("data") or {}).get("status") in {"ready", "completed"},
            failed=lambda body: (body.get("data") or {}).get("status") == "failed",
            deadline=deadline,
            poll_seconds=poll_seconds,
            sleep=sleep,
            label="prepare",
        )
    return str(simulation_id)


def _start_and_wait(
    http: httpx.Client,
    base_url: str,
    simulation_id: str,
    max_rounds: int,
    platform: str,
    deadline: float,
    poll_seconds: float,
    sleep: SleepFn,
) -> None:
    _post(
        http,
        base_url,
        "/api/simulation/start",
        json={
            "simulation_id": simulation_id,
            "platform": platform,
            "max_rounds": max_rounds,
            "enable_graph_memory_update": False,
        },
    )
    terminal = {"completed", "stopped", "failed"}

    def poll() -> dict[str, Any]:
        return _get(http, base_url, f"/api/simulation/{simulation_id}/run-status")

    _poll_until(
        poll,
        done=lambda body: (body.get("data") or {}).get("runner_status") in terminal,
        failed=lambda body: (body.get("data") or {}).get("runner_status") == "failed",
        deadline=deadline,
        poll_seconds=poll_seconds,
        sleep=sleep,
        label="simulation",
    )


def _capture(http: httpx.Client, base_url: str, simulation_id: str) -> dict[str, Any]:
    posts = _get(http, base_url, f"/api/simulation/{simulation_id}/posts", params={"limit": 80})
    comments = _get(http, base_url, f"/api/simulation/{simulation_id}/comments", params={"limit": 80})
    actions = _get(http, base_url, f"/api/simulation/{simulation_id}/actions", params={"limit": 120})
    stats = _get(http, base_url, f"/api/simulation/{simulation_id}/agent-stats")
    post_rows, post_duplicates = _deduplicate_messages(_list_payload(posts))
    comment_rows, comment_duplicates = _deduplicate_messages(_list_payload(comments))
    return {
        "posts": post_rows,
        "comments": comment_rows,
        "actions": _list_payload(actions),
        "duplicate_messages_rejected": post_duplicates + comment_duplicates,
        "agent_stats": (stats.get("data") or stats),
    }


def _deduplicate_messages(rows: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], int]:
    """Keep the first copy of each non-empty message before exposing it publicly."""
    kept: list[dict[str, Any]] = []
    seen: set[str] = set()
    rejected = 0
    for row in rows:
        text = str(row.get("content") or row.get("text") or "").strip()
        if not text:
            kept.append(row)
            continue
        if text in seen:
            rejected += 1
            continue
        seen.add(text)
        kept.append(row)
    return kept, rejected


def _poll_task(
    http: httpx.Client,
    base_url: str,
    task_id: str,
    deadline: float,
    poll_seconds: float,
    sleep: SleepFn,
) -> dict[str, Any] | None:
    def poll() -> dict[str, Any]:
        return _get(http, base_url, f"/api/graph/task/{task_id}")

    body = _poll_until(
        poll,
        done=lambda item: (item.get("data") or {}).get("status") in {"completed", "failed"},
        failed=lambda item: (item.get("data") or {}).get("status") == "failed",
        deadline=deadline,
        poll_seconds=poll_seconds,
        sleep=sleep,
        label="graph-build",
    )
    data = body.get("data") or {}
    if data.get("status") == "failed":
        raise SwarmError(data.get("error") or "MiroFish graph build failed")
    return data.get("result")


def _poll_until(
    poll: Callable[[], dict[str, Any]],
    *,
    done: Callable[[dict[str, Any]], bool],
    failed: Callable[[dict[str, Any]], bool],
    deadline: float,
    poll_seconds: float,
    sleep: SleepFn,
    label: str,
) -> dict[str, Any]:
    last: dict[str, Any] = {}
    while time.monotonic() < deadline:
        last = poll()
        if failed(last):
            raise SwarmError(f"MiroFish {label} failed: {last}")
        if done(last):
            return last
        sleep(poll_seconds)
    raise SwarmError(f"Timed out waiting for MiroFish {label}")


def _post(http: httpx.Client, base_url: str, path: str, **kwargs: Any) -> dict[str, Any]:
    response = http.post(_url(base_url, path), **kwargs)
    return _parse(response, path)


def _get(http: httpx.Client, base_url: str, path: str, **kwargs: Any) -> dict[str, Any]:
    response = http.get(_url(base_url, path), **kwargs)
    return _parse(response, path)


def _parse(response: httpx.Response, path: str) -> dict[str, Any]:
    try:
        payload = response.json() if response.content else {}
    except ValueError:
        payload = {}
    if not response.is_success:
        raise SwarmError(f"{path} HTTP {response.status_code}: {payload or response.text[:300]}")
    if isinstance(payload, dict) and payload.get("success") is False:
        raise SwarmError(str(payload.get("error") or payload))
    return payload if isinstance(payload, dict) else {"data": payload}


def _list_payload(payload: dict[str, Any]) -> list[dict[str, Any]]:
    data = payload.get("data") if isinstance(payload, dict) else payload
    if isinstance(data, list):
        return [item for item in data if isinstance(item, dict)]
    if isinstance(data, dict):
        for key in ("posts", "comments", "actions", "items"):
            value = data.get(key)
            if isinstance(value, list):
                return [item for item in value if isinstance(item, dict)]
    return []


def _url(base_url: str, path: str) -> str:
    return base_url.rstrip("/") + path
