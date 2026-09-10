import json
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
