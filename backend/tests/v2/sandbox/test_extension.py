import json
import sqlite3
import threading
from concurrent.futures import ThreadPoolExecutor

import pytest

from app.v2.contracts import make_example_request, request_fingerprint
from app.v2.sandbox.extension import JobRegistry, build_roster_config


def people(count=3):
    return [
        {
            "display_name": f"Rider {i}",
            "description": f"Safety-conscious worker {i}.",
            "opening_statement": "How will the service operate?",
        }
        for i in range(count)
    ]


class Runtime:
    def __init__(self):
        self.prepares = self.starts = self.stops = 0
        self.state = None

    def prepare(self, request, personas):
        self.prepares += 1
        return "sim_000000000001"

    def start(self, simulation_id, rounds):
        self.starts += 1
        self.state = "running"

    def status(self, simulation_id):
        return self.state

    def stop(self, simulation_id):
        self.stops += 1
        self.state = "stopped"


def test_persistent_idempotent_prepare_start_and_restart(tmp_path):
    runtime = Runtime()
    request = make_example_request().model_dump(mode="json")
    registry = JobRegistry(tmp_path / "jobs.sqlite", runtime)
    fp = request_fingerprint(make_example_request())
    first = registry.prepare(fp, request, people())
    second = registry.prepare(fp, request, people())
    assert first == second and runtime.prepares == 1
    registry.start(fp)
    restarted = JobRegistry(tmp_path / "jobs.sqlite", runtime)
    restarted.start(fp)
    assert runtime.starts == 1
    assert restarted.lookup(fp)["status"] == "running"


@pytest.mark.parametrize("terminal", ["completed", "failed", "stopped"])
def test_lookup_persists_terminal_status_and_survives_engine_restart(
    tmp_path, terminal
):
    runtime = Runtime()
    path = tmp_path / "jobs.sqlite"
    registry = JobRegistry(path, runtime)
    request = make_example_request()
    fp = request_fingerprint(request)
    registry.prepare(fp, request.model_dump(mode="json"), people())
    registry.start(fp)
    runtime.state = terminal
    assert registry.lookup(fp)["status"] == terminal
    with sqlite3.connect(path) as db:
        payload = json.loads(db.execute("SELECT payload FROM jobs").fetchone()[0])
    assert payload["status"] == terminal
    runtime.status = lambda _: (_ for _ in ()).throw(RuntimeError("Engine offline"))
    assert JobRegistry(path, runtime).lookup(fp)["status"] == terminal


def test_stale_poll_cannot_overwrite_concurrent_cancellation(tmp_path):
    runtime = Runtime()
    path = tmp_path / "jobs.sqlite"
    registry = JobRegistry(path, runtime)
    other = JobRegistry(path, runtime)
    request = make_example_request()
    fp = request_fingerprint(request)
    registry.prepare(fp, request.model_dump(mode="json"), people())
    registry.start(fp)
    polled, release = threading.Event(), threading.Event()

    def delayed_status(_):
        if threading.current_thread().name.startswith("poll"):
            polled.set()
            assert release.wait(3)
            return "running"
        return runtime.state

    runtime.status = delayed_status
    with ThreadPoolExecutor(max_workers=1, thread_name_prefix="poll") as pool:
        future = pool.submit(registry.lookup, fp)
        assert polled.wait(3)
        other.stop(fp)
        release.set()
        assert future.result(timeout=3)["status"] == "cancelled"
    assert registry.lookup(fp)["status"] == "cancelled"


def test_concurrent_requests_launch_one_job(tmp_path):
    runtime = Runtime()
    registry = JobRegistry(tmp_path / "jobs.sqlite", runtime)
    request = make_example_request()
    fp = request_fingerprint(request)
    with ThreadPoolExecutor(max_workers=4) as executor:
        list(
            executor.map(
                lambda _: registry.prepare(
                    fp, request.model_dump(mode="json"), people()
                ),
                range(8),
            )
        )
        list(executor.map(lambda _: registry.start(fp), range(8)))
    assert runtime.prepares == runtime.starts == 1


def test_ambiguous_prepare_is_never_relaunched(tmp_path):
    runtime = Runtime()

    def lost_response(*args):
        runtime.prepares += 1
        raise RuntimeError("Disconnected after creation")

    runtime.prepare = lost_response
    registry = JobRegistry(tmp_path / "jobs.sqlite", runtime)
    request = make_example_request()
    fp = request_fingerprint(request)
    with pytest.raises(RuntimeError):
        registry.prepare(fp, request.model_dump(mode="json"), people())
    registry.prepare(fp, request.model_dump(mode="json"), people())
    assert runtime.prepares == 1
    assert registry.lookup(fp)["status"] == "prepare_uncertain"


def test_stop_before_prepare_prevents_a_late_launch(tmp_path):
    runtime = Runtime()
    registry = JobRegistry(tmp_path / "jobs.sqlite", runtime)
    request = make_example_request()
    fp = request_fingerprint(request)
    registry.stop(fp)
    with pytest.raises(ValueError):
        registry.prepare(fp, request.model_dump(mode="json"), people())
    assert runtime.prepares == 0


def test_roster_controls_native_profiles_and_every_round():
    request = make_example_request().model_dump(mode="json")
    request["personality_seed"] = "Practical nurses and cautious wheelchair users"
    profiles, config = build_roster_config(request, people(), "sim_1", "proj_1")
    assert len(profiles) == len(config["agent_configs"]) == 3
    assert config["time_config"]["agents_per_hour_min"] == 3
    assert config["time_config"]["total_simulation_hours"] == request["max_rounds"]
    for profile in profiles:
        assert request["personality_seed"] in profile["persona"]
        assert request["policy_text"] in profile["persona"]
        assert "test_budget" not in profile["persona"]
        assert "expected_verdict" not in profile["persona"]
    assert "scenario-late-shift" in json.dumps(config)


def test_native_progress_reconciles_completed_rounds_and_forced_stop(tmp_path):
    from types import SimpleNamespace

    from app.v2.sandbox.extension import reconcile_progress

    data = {
        "status": "running",
        "completed_rounds": 1,
        "active_round": 2,
        "actions_count": 12,
        "updated_at": "2026-09-11T01:01:15+08:00",
        "error": None,
        "rounds": [
            {
                "round": 1,
                "started_at": "start",
                "completed_at": "end",
                "actions_count": 10,
            }
        ],
    }
    (tmp_path / "policyfuzz_progress.json").write_text(json.dumps(data))
    (tmp_path / "env_status.json").write_text(
        json.dumps({"status": "running", "other": "preserved"})
    )
    state = SimpleNamespace(
        runner_status=SimpleNamespace(value="stopped"),
        current_round=0,
        twitter_actions_count=0,
        rounds=[],
        completed_at="2026-09-11T01:04:09+08:00",
    )
    reconcile_progress(state, tmp_path, lambda **kw: SimpleNamespace(**kw))
    assert state.current_round == 1 and state.twitter_current_round == 1
    assert state.twitter_actions_count == 12 and not state.twitter_running
    assert not state.twitter_completed and state.rounds[0].twitter_actions == 10
    assert state.updated_at == state.completed_at
    assert json.loads((tmp_path / "env_status.json").read_text())["status"] == "stopped"
    assert (
        json.loads((tmp_path / "env_status.json").read_text())["other"] == "preserved"
    )
