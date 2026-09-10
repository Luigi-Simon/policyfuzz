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


def test_seed_reproduces_probe_facts_across_python_processes():
    """Interpreter hash randomization must not alter a frozen probe's input facts."""
    import json
    import os
    import subprocess
    import sys
    from pathlib import Path

    script = '''
import json
from app.contracts.run import SeedSpec
from app.services.extract import heuristic_extract
from app.services.fuzz import FuzzDesigner
from app.services.ingest import ingest_bytes
from tests.conftest import SAMPLE_POLICY
ir = heuristic_extract(ingest_bytes("sample_policy.txt", SAMPLE_POLICY.read_bytes()))
suite = FuzzDesigner().generate(ir, SeedSpec(text="repeatable rehearsal", population_size=12))
print(json.dumps([item.model_dump(exclude={"scenario_id"}) for item in suite.scenarios], sort_keys=True))
'''
    engine = Path(__file__).resolve().parents[1]
    results = []
    for hash_seed in ("1", "2"):
        environment = os.environ.copy()
        environment["PYTHONHASHSEED"] = hash_seed
        completed = subprocess.run(
            [sys.executable, "-c", script],
            cwd=engine,
            env=environment,
            check=True,
            capture_output=True,
            text=True,
            timeout=20,
        )
        results.append(json.loads(completed.stdout.splitlines()[-1]))
    assert results[0] == results[1]


def test_capped_population_covers_later_rules_before_repeating_earlier_rules():
    from collections import Counter

    from app.contracts.policy import PolicyDocument, PolicyIR, Rule

    ir = PolicyIR(
        title="Twenty synthetic rules",
        source=PolicyDocument(filename="synthetic.txt"),
        rules=[
            Rule(id=f"R{index:03}", title=f"Rule {index}", statement="Synthetic rule")
            for index in range(1, 21)
        ],
    )
    suite = FuzzDesigner().generate(ir, SeedSpec(text="coverage", population_size=50))
    counts = Counter(rule_id for item in suite.scenarios for rule_id in item.targeted_rule_ids)
    assert set(counts) == {rule.id for rule in ir.rules}
    assert max(counts.values()) - min(counts.values()) <= 1
    assert len({item.targeted_rule_ids[0] for item in suite.scenarios[:20]}) == 20
    assert {item.kind for item in suite.scenarios} >= {"normal", "boundary", "adversarial"}


def test_generated_probe_kinds_never_supply_their_own_expected_outcomes():
    document = ingest_bytes("sample_policy.txt", SAMPLE_POLICY.read_bytes())
    ir = heuristic_extract(document)
    suite = FuzzDesigner().generate(ir, SeedSpec(text="unasserted probes", population_size=50))
    assert {item.kind for item in suite.scenarios} >= {"normal", "boundary", "adversarial"}
    assert all(item.expected_outcome is None for item in suite.scenarios)


def test_small_population_balances_probe_kinds_across_distinct_rules():
    from app.contracts.policy import PolicyDocument, PolicyIR, Rule

    ir = PolicyIR(
        title="Synthetic coverage",
        source=PolicyDocument(filename="synthetic.txt"),
        rules=[
            Rule(id=f"R{index}", title=f"Rule {index}", statement="Synthetic rule")
            for index in range(10)
        ],
    )
    suite = FuzzDesigner().generate(ir, SeedSpec(text="small coverage", population_size=3))
    assert len({item.targeted_rule_ids[0] for item in suite.scenarios}) == 3
    assert {item.kind for item in suite.scenarios} == {"normal", "boundary", "adversarial"}


def test_ambiguity_probes_do_not_starve_later_rules():
    from app.contracts.policy import PolicyDocument, PolicyIR, Rule

    ir = PolicyIR(
        title="Synthetic ambiguous rules",
        source=PolicyDocument(filename="synthetic.txt"),
        rules=[
            Rule(
                id=f"R{index}", title=f"Rule {index}", statement="Synthetic rule",
                ambiguity="Owner interpretation required",
            )
            for index in range(10)
        ],
    )
    suite = FuzzDesigner().generate(ir, SeedSpec(text="ambiguity coverage", population_size=40))
    for rule in ir.rules:
        kinds = {item.kind for item in suite.scenarios if rule.id in item.targeted_rule_ids}
        assert kinds == {"normal", "boundary", "adversarial", "targeted"}
    assert len({item.targeted_rule_ids[0] for item in suite.scenarios[:10]}) == 10
