from app.contracts.run import SeedSpec
from app.services.effectiveness import synthesize_effectiveness
from app.services.evaluate import RuleEvaluator
from app.services.extract import heuristic_extract
from app.services.fuzz import FuzzDesigner
from app.services.ingest import ingest_bytes
from tests.conftest import SAMPLE_POLICY


def test_effectiveness_score_is_0_to_100_with_repair_hints():
    document = ingest_bytes("sample_policy.txt", SAMPLE_POLICY.read_bytes())
    ir = heuristic_extract(document)
    suite = FuzzDesigner().generate(ir, SeedSpec(text="parents and students", population_size=20))
    evaluation = RuleEvaluator().evaluate(ir, suite)
    report = synthesize_effectiveness(ir, evaluation)
    assert 0 <= report.score <= 100
    assert report.justification
    assert report.recommended_actions
    assert report.swarm_used is False
    assert report.interaction_verified is False
    assert "Fuzz suite" in report.justification


def test_swarm_highlights_feed_justification():
    document = ingest_bytes("sample_policy.txt", SAMPLE_POLICY.read_bytes())
    ir = heuristic_extract(document)
    suite = FuzzDesigner().generate(ir, SeedSpec(text="town", population_size=6))
    evaluation = RuleEvaluator().evaluate(ir, suite)
    swarm = {
        "posts": [
            {
                "user_name": "Priya Nair",
                "platform": "twitter",
                "content": "This is unfair — rumours say ineligible PRs already got paid.",
            }
        ],
        "comments": [
            {
                "user_name": "Hafiz Abdullah",
                "platform": "twitter",
                "content": "PRs are not eligible. The $500 is for citizens only.",
                "post_author": "Priya Nair",
            }
        ],
        "actions": [{"agent_name": "Priya Nair", "content": "posted about rumours"}],
    }
    report = synthesize_effectiveness(ir, evaluation, swarm=swarm)
    assert report.swarm_used is True
    assert report.interaction_verified is True
    assert any("Priya Nair" in item.agent for item in report.highlights)
    assert "Priya Nair" in report.justification
    assert "Hafiz Abdullah" in report.justification
    assert "Key swarm conversations" in report.justification
    assert any(hint.action in {"communicate", "clarify", "tighten"} for hint in report.recommended_actions)
