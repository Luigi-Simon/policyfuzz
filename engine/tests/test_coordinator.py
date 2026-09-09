from app.contracts.scenario import Scenario, ScenarioSuite
from app.services.coordinator import Coordinator
from app.services.revise import revise_policy_ir
from tests.conftest import SAMPLE_POLICY, make_pdf_bytes


class ScriptedRevision:
    enabled = True

    def __init__(self, ir):
        self.ir = ir

    def complete_json(self, *, system, user):
        if "Revision instruction:" not in user:
            return {"recommended_actions": []}
        raw = self.ir.model_dump(mode="json")
        raw["rules"][0]["when"].append(
            {"field": "context.days", "op": "gte", "value": 7}
        )
        return raw


def test_pipeline_compiles_without_llm(tmp_settings):
    coordinator = Coordinator(settings=tmp_settings)
    payload = SAMPLE_POLICY.read_bytes()
    record = coordinator.create_run(
        filename="sample_policy.txt",
        payload=payload,
        seed=None,
    )
    assert record.status == "completed"
    assert record.ir is not None
    assert record.ir.rules
    assert record.suite is not None
    assert len(record.suite.scenarios) <= 50
    assert record.evaluation is not None
    assert record.effectiveness is not None
    assert 0 <= record.effectiveness.score <= 100
    stored = coordinator.store.get(record.run_id)
    assert stored is not None
    assert stored.ir.policy_id == record.ir.policy_id


def test_revise_bumps_revision(tmp_settings):
    coordinator = Coordinator(settings=tmp_settings)
    record = coordinator.create_run(
        filename="sample_policy.txt",
        payload=SAMPLE_POLICY.read_bytes(),
    )
    coordinator.llm = ScriptedRevision(record.ir)
    revised = coordinator.revise(record.run_id, "Delay enforcement by one week.")
    assert revised.ir is not None
    assert revised.ir.revision == 2
    assert revised.ir.parent_revision == 1
    assert revised.ir.change_log
    assert revised.status == "completed"


def test_attach_suite(tmp_settings):
    coordinator = Coordinator(settings=tmp_settings)
    record = coordinator.create_run(
        filename="ban.pdf",
        payload=make_pdf_bytes(
            "Students must not use phones. Teachers shall confiscate after 2 warnings."
        ),
    )
    suite = ScenarioSuite(
        policy_id=record.ir.policy_id,
        policy_revision=record.ir.revision,
        seed="200 students, mixed grades",
        population_size=200,
        scenarios=[
            Scenario(
                kind="boundary",
                title="Exactly two warnings",
                facts={
                    "actor.role": "student",
                    "action.name": "use_device",
                    "context.warnings": 2,
                },
                targeted_rule_ids=[record.ir.rules[0].id],
                expected_outcome="violation",
            )
        ],
    )
    updated = coordinator.attach_suite(record.run_id, suite)
    assert updated.status == "completed"
    assert updated.suite is not None
    assert updated.suite.scenarios[0].kind == "boundary"
    assert updated.evaluation is not None
    assert updated.effectiveness is not None


def test_designer_plugin_advances_status(tmp_settings):
    from examples.simple_designer import SimpleDesigner

    coordinator = Coordinator(settings=tmp_settings, designer=SimpleDesigner())
    record = coordinator.create_run(
        filename="sample_policy.txt", payload=SAMPLE_POLICY.read_bytes()
    )
    assert record.status == "completed"
    assert record.suite is not None
    assert {item.kind for item in record.suite.scenarios} == {
        "normal",
        "boundary",
        "adversarial",
        "targeted",
    }


def test_revise_function_without_run():
    from app.services.extract import heuristic_extract
    from app.services.ingest import ingest_bytes

    document = ingest_bytes("p.txt", SAMPLE_POLICY.read_bytes())
    ir = heuristic_extract(document)
    revised = revise_policy_ir(
        ir, "Delay enforcement by one week.", llm=ScriptedRevision(ir)
    )
    assert revised.revision == ir.revision + 1
    assert revised.policy_id == ir.policy_id
