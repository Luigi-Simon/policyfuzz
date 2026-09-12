from app.services.extract import heuristic_extract
from app.services.ingest import ingest_bytes
from app.services.mirofish_bridge import build_mirofish_pack
from tests.conftest import SAMPLE_POLICY


def test_uploaded_scenario_keeps_hypothetical_status_at_external_boundary():
    """Uploading a supplied scenario must not turn it into an official announcement."""
    import httpx

    from app.contracts.run import SeedSpec
    from app.services.mirofish_bridge import launch_mirofish

    source = (
        "Maju Forest Redevelopment and Land Optimization Framework\n"
        "A hypothetical 32-hectare site includes a 5-hectare green corridor."
    )
    document = ingest_bytes("maju-demo.txt", source.encode())
    ir = heuristic_extract(document)
    pack = build_mirofish_pack(
        ir,
        SeedSpec(text="Discuss uncertain tradeoffs.", population_size=5,
                 groups=["home_buyers", "conservation_researchers"]),
    )
    requests = []

    def receive(request):
        requests.append(request.content.decode())
        return httpx.Response(200, json={"success": True, "data": {"project_id": "demo"}})

    with httpx.Client(transport=httpx.MockTransport(receive)) as client:
        launch = launch_mirofish(
            pack,
            policy_filename="maju-demo.txt",
            policy_bytes=source.encode(),
            base_url="https://simulation.example",
            client=client,
        )

    assert launch.ok
    assert len(requests) == 1
    assert source in requests[0]
    assert "hypothetical" in pack.simulation_requirement.lower()
    assert "not a verified government announcement" in pack.seed_markdown.lower()
    assert "not representative" in pack.simulation_requirement.lower()
    assert "A government just announced" not in requests[0]


def test_pack_from_ir_without_suite():
    document = ingest_bytes("p.txt", SAMPLE_POLICY.read_bytes())
    ir = heuristic_extract(document)
    from app.contracts.run import SeedSpec

    pack = build_mirofish_pack(
        ir,
        SeedSpec(text="80 mixed students", population_size=80, groups=["students", "teachers"]),
    )
    assert pack.population_size == 50
    assert pack.agent_count == 0
    assert "Resident 001" in pack.seed_markdown
    assert "social media" in pack.simulation_requirement.lower() or "talk" in pack.simulation_requirement.lower()
    assert "do not invent eligibility categories" in pack.simulation_requirement.lower()
    assert "ineligible groups were paid" not in pack.simulation_requirement.lower()
    assert ir.rules[0].statement[:40] in pack.seed_markdown


def test_create_run_writes_mirofish_pack(tmp_settings):
    from app.services.coordinator import Coordinator

    coordinator = Coordinator(settings=tmp_settings)
    record = coordinator.create_run(filename="sample_policy.txt", payload=SAMPLE_POLICY.read_bytes())
    assert record.mirofish is not None
    assert record.mirofish.seed_markdown
    seed_path = coordinator.store._dir(record.run_id) / "mirofish_seed.md"
    assert seed_path.exists()


def test_attach_suite_rebuilds_named_agents(tmp_settings):
    from app.contracts.scenario import Scenario, ScenarioSuite
    from app.services.coordinator import Coordinator

    coordinator = Coordinator(settings=tmp_settings)
    record = coordinator.create_run(filename="sample_policy.txt", payload=SAMPLE_POLICY.read_bytes())
    suite = ScenarioSuite(
        policy_id=record.ir.policy_id,
        policy_revision=record.ir.revision,
        seed="census",
        population_size=2,
        scenarios=[
            Scenario(
                kind="normal",
                title="Adult citizen",
                facts={"actor.name": "Tan Wei Ming", "actor.citizenship": "citizen", "actor.age": 34},
                expected_outcome="compliant",
            ),
            Scenario(
                kind="adversarial",
                title="PR claim",
                facts={"actor.name": "Priya Nair", "actor.citizenship": "permanent_resident", "actor.age": 41},
                expected_outcome="violation",
            ),
        ],
    )
    updated = coordinator.attach_suite(record.run_id, suite)
    assert updated.mirofish is not None
    assert updated.mirofish.agent_count == 2
    assert "Tan Wei Ming" in updated.mirofish.seed_markdown
    assert "Priya Nair" in updated.mirofish.seed_markdown
    assert "adversarial" in updated.mirofish.seed_markdown
