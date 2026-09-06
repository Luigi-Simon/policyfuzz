from app.services.evaluate import RuleEvaluator
from app.services.extract import heuristic_extract
from app.services.fuzz import FuzzDesigner
from app.services.ingest import ingest_bytes
from app.contracts.run import SeedSpec
from tests.conftest import SAMPLE_POLICY


def test_fuzzer_caps_at_50_and_covers_kinds():
    document = ingest_bytes("sample_policy.txt", SAMPLE_POLICY.read_bytes())
    ir = heuristic_extract(document)
    suite = FuzzDesigner(max_agents=50).generate(
        ir,
        SeedSpec(text="urban high school", population_size=200, groups=["students", "teachers"]),
    )
    assert suite.population_size == 50
    assert len(suite.scenarios) == 50
    kinds = {item.kind for item in suite.scenarios}
    assert {"normal", "boundary", "adversarial"} <= kinds
    assert all(item.facts.get("actor.name") for item in suite.scenarios)
    assert all(item.facts.get("action.name") for item in suite.scenarios)
    covered = {rid for item in suite.scenarios for rid in item.targeted_rule_ids}
    assert covered


def test_fuzzer_respects_smaller_population():
    document = ingest_bytes("sample_policy.txt", SAMPLE_POLICY.read_bytes())
    ir = heuristic_extract(document)
    suite = FuzzDesigner().generate(ir, SeedSpec(text="tiny", population_size=8))
    assert len(suite.scenarios) == 8


def test_fuzzer_uses_injected_audience_segments():
    from app.contracts.run import AudienceSegment

    document = ingest_bytes("sample_policy.txt", SAMPLE_POLICY.read_bytes())
    ir = heuristic_extract(document)
    suite = FuzzDesigner().generate(
        ir,
        SeedSpec(
            text="California district",
            population_size=12,
            locale="US-CA",
            segments=[
                AudienceSegment(
                    id="students",
                    label="Students",
                    weight=3,
                    attributes={"age": 16, "grade": 10},
                ),
                AudienceSegment(
                    id="teachers",
                    label="Teachers",
                    weight=1,
                    attributes={"role_title": "teacher"},
                ),
            ],
        ),
    )
    groups = {item.facts.get("actor.group") for item in suite.scenarios}
    assert groups <= {"students", "teachers"}
    assert any(item.facts.get("context.locale") == "US-CA" for item in suite.scenarios)
    student = next(item for item in suite.scenarios if item.facts.get("actor.group") == "students")
    assert student.facts.get("actor.age") == 16
    assert student.facts.get("actor.segment") == "Students"


def test_evaluator_emits_findings_for_every_scenario():
    document = ingest_bytes("sample_policy.txt", SAMPLE_POLICY.read_bytes())
    ir = heuristic_extract(document)
    suite = FuzzDesigner().generate(ir, SeedSpec(text="board", population_size=12))
    report = RuleEvaluator().evaluate(ir, suite)
    assert len(report.findings) == 12
    assert set(report.metrics["verdicts"]) >= {"pass", "fail", "ambiguous"}
    assert all(finding.traces for finding in report.findings)
