from app.contracts.policy import PolicyDocument
from app.contracts.scenario import Scenario, ScenarioSuite
from app.services.compile import compile_ir
from app.services.extract import heuristic_extract
from app.services.ingest import ingest_bytes
from tests.conftest import SAMPLE_POLICY, make_pdf_bytes


def test_ingest_pdf_keeps_pages():
    payload = make_pdf_bytes("Students must not use phones in class.")
    document = ingest_bytes("ban.pdf", payload)
    assert document.page_count == 1
    assert "phones" in document.text.lower()


def test_ingest_txt():
    document = ingest_bytes("note.txt", b"Teachers shall confiscate devices after two warnings.")
    assert document.media_type == "text/plain"
    assert document.page_count == 1


def test_heuristic_extract_sample_policy():
    text = SAMPLE_POLICY.read_text(encoding="utf-8")
    document = ingest_bytes("sample_policy.txt", text.encode("utf-8"))
    ir = heuristic_extract(document)
    compiled = compile_ir(ir)
    assert compiled.rules
    assert compiled.actor_types
    assert all(rule.citations and rule.citations[0].quote for rule in compiled.rules)
    assert "actor.role" in compiled.index.fact_fields
    assert compiled.revision == 1


def test_compile_builds_rules_by_actor():
    document = PolicyDocument(filename="x.txt", text="Students must not run.", pages=["Students must not run."])
    ir = heuristic_extract(document)
    compiled = compile_ir(ir)
    assert compiled.index.rules_by_actor
    assert compiled.index.fact_fields


def test_scenario_suite_groups_by_kind():
    suite = ScenarioSuite(
        policy_id="pol_x",
        policy_revision=1,
        seed="urban high school",
        scenarios=[
            Scenario(kind="normal", title="n", facts={}),
            Scenario(kind="adversarial", title="a", facts={}),
        ],
    )
    grouped = suite.by_kind()
    assert len(grouped["normal"]) == 1
    assert len(grouped["adversarial"]) == 1
