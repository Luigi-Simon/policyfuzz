import httpx

from app.contracts.mirofish import MiroFishPack
from app.services.mirofish_runner import run_swarm


def test_run_swarm_walks_ontology_build_prepare_start_capture():
    calls: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        path = request.url.path
        calls.append(f"{request.method} {path}")
        if path.endswith("/ontology/generate"):
            return httpx.Response(200, json={"success": True, "data": {"project_id": "proj_1"}})
        if path.endswith("/build"):
            return httpx.Response(
                200,
                json={"success": True, "data": {"task_id": "task_1", "graph_id": "graph_1"}},
            )
        if path.endswith("/task/task_1"):
            return httpx.Response(
                200,
                json={"success": True, "data": {"status": "completed", "result": {"graph_id": "graph_1"}}},
            )
        if path.endswith("/create"):
            return httpx.Response(200, json={"success": True, "data": {"simulation_id": "sim_1"}})
        if path.endswith("/prepare") and request.method == "POST":
            return httpx.Response(
                200,
                json={"success": True, "data": {"simulation_id": "sim_1", "status": "ready", "already_prepared": True}},
            )
        if path.endswith("/start"):
            return httpx.Response(200, json={"success": True, "data": {"runner_status": "running"}})
        if path.endswith("/run-status"):
            return httpx.Response(
                200,
                json={"success": True, "data": {"runner_status": "completed", "current_round": 8}},
            )
        if path.endswith("/posts"):
            return httpx.Response(
                200,
                json={"success": True, "data": {"posts": [{"user_name": "Aisha", "content": "This is unfair"}]}},
            )
        if path.endswith("/comments"):
            return httpx.Response(200, json={"success": True, "data": {"comments": []}})
        if path.endswith("/actions"):
            return httpx.Response(200, json={"success": True, "data": {"actions": [{"agent_name": "Aisha", "content": "post"}]}})
        if path.endswith("/agent-stats"):
            return httpx.Response(200, json={"success": True, "data": {"count": 8}})
        return httpx.Response(404, json={"success": False, "error": path})

    transport = httpx.MockTransport(handler)
    client = httpx.Client(transport=transport, base_url="http://mirofish.test")
    pack = MiroFishPack(seed_markdown="# seed", simulation_requirement="talk", population_size=8, agent_count=8)
    launch, capture = run_swarm(
        pack,
        policy_filename="policy.txt",
        policy_bytes=b"hello",
        base_url="http://mirofish.test",
        client=client,
        sleep=lambda _: None,
        poll_seconds=0,
        swarm_timeout=30,
    )
    assert launch.ok
    assert launch.project_id == "proj_1"
    assert capture["simulation_id"] == "sim_1"
    assert capture["posts"][0]["user_name"] == "Aisha"
    assert any(path.endswith("/ontology/generate") for path in (c.split(" ", 1)[1] for c in calls))
    assert any("/api/simulation/start" in c for c in calls)
