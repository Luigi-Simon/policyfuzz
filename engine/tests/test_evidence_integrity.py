"""Regression tests for scoring authority and revision evidence isolation."""

import pytest
from app.contracts.evaluation import EvaluationReport, Finding
from app.contracts.policy import (
    ActionSpec,
    ActorType,
    Obligation,
    PolicyDocument,
    PolicyIR,
    Rule,
)
from app.contracts.scenario import Scenario, ScenarioSuite
from app.llm import LLMError
from app.services.coordinator import Coordinator
from app.services.effectiveness import synthesize_effectiveness
from app.services.evaluate import RuleEvaluator
from app.services.mirofish_runner import SwarmError
from app.services.revise import revise_policy_ir


def policy():
    return PolicyIR(
        policy_id="synthetic-policy",
        title="Synthetic lab rule",
        source=PolicyDocument(
            filename="synthetic.txt", text="Visitors must wear badges."
        ),
        actor_types=[ActorType(id="visitor", label="Visitor")],
        actions=[ActionSpec(name="wear_badge")],
        rules=[
            Rule(
                id="R001",
                title="Badges",
                statement="Visitors must wear badges.",
                applies_to=["visitor"],
                then=[Obligation(modality="must", action="wear_badge")],
            )
        ],
    )


class ScoreOverrideLLM:
    enabled = True

    def complete_json(self, **kwargs):
        return {
            "score": 100,
            "justification": "All checks passed: 100/100.",
            "recommended_actions": [],
        }


def test_model_cannot_overwrite_measured_score_or_justification():
    ir = policy()
    evaluation = EvaluationReport(
        policy_id=ir.policy_id,
        policy_revision=1,
        suite_id="suite",
        findings=[
            Finding(
                scenario_id="case",
                verdict="fail",
                rule_ids=["R001"],
                summary="Missing badge",
            )
        ],
    )
    report = synthesize_effectiveness(ir, evaluation, llm=ScoreOverrideLLM())
    assert report.score == 10
    assert "100/100" not in report.justification
    assert "1 fail" in report.justification
    assert report.metrics["score_kind"] == "exploratory_heuristic"


def test_swarm_opinions_cannot_inflate_policy_test_score():
    ir = policy()
    evaluation = EvaluationReport(
        policy_id=ir.policy_id,
        policy_revision=1,
        suite_id="suite",
        findings=[
            Finding(
                scenario_id="case",
                verdict="fail",
                rule_ids=["R001"],
                summary="Missing badge",
            )
        ],
    )
    report = synthesize_effectiveness(
        ir,
        evaluation,
        swarm={
            "posts": [
                {"user_name": "Sam", "content": "I support this clear, fair policy."}
            ]
        },
    )
    assert report.score == 10
    assert report.swarm_used is True
    assert report.highlights


@pytest.mark.parametrize("action", ["wear_badge", "enter_without_badge"])
def test_scenario_without_assertion_cannot_pass(action):
    ir = policy()
    suite = ScenarioSuite(
        policy_id=ir.policy_id,
        policy_revision=1,
        seed="synthetic",
        scenarios=[
            Scenario(
                kind="normal",
                title="Unverified expectation",
                facts={"action.name": action},
                expected_outcome=None,
            )
        ],
    )
    report = RuleEvaluator().evaluate(ir, suite)
    assert report.findings[0].verdict == "ambiguous"
    assert "unasserted" in report.findings[0].summary.lower()
    effectiveness = synthesize_effectiveness(ir, report)
    assert effectiveness.metrics["score_available"] is False
    assert effectiveness.metrics["unasserted_count"] == 1
    assert effectiveness.score == 0


def _stored_run(settings):
    coordinator = Coordinator(settings=settings)
    record = coordinator.create_run(
        filename="synthetic.txt", payload=b"Visitors must wear badges."
    )
    assert record.status == "completed"
    record.extra["swarm"] = {
        "simulation_id": "baseline-swarm",
        "posts": [{"user_name": "Sam", "content": "Baseline policy is clear."}],
        "comments": [{"user_name": "Alex", "content": "I support this original rule."}],
    }
    coordinator.store.save(record)
    return coordinator, record


class RevisionLLM:
    enabled = True

    def __init__(self, baseline):
        self.baseline = baseline

    def complete_json(self, **kwargs):
        if "Revision instruction:" not in kwargs.get("user", ""):
            return {"recommended_actions": []}
        payload = self.baseline.model_dump(mode="json")
        payload["rules"][0]["then"][0]["modality"] = "may"
        return payload


def test_revision_reuses_frozen_cases_and_archives_prior_swarm(tmp_settings):
    coordinator, baseline = _stored_run(tmp_settings)
    frozen = baseline.suite.model_dump(mode="json")
    coordinator.llm = RevisionLLM(baseline.ir)
    revised = coordinator.revise(baseline.run_id, "Clarify the badge rule.")
    assert revised.suite.suite_id == frozen["suite_id"]
    assert [item.model_dump(mode="json") for item in revised.suite.scenarios] == frozen[
        "scenarios"
    ]
    assert "swarm" not in revised.extra
    assert revised.effectiveness.swarm_used is False
    assert revised.effectiveness.interaction_verified is False
    assert (
        revised.extra["evidence_history"][-1]["swarm"]["simulation_id"]
        == "baseline-swarm"
    )
    assert revised.extra["evidence_history"][-1]["suite"] == frozen
    assert revised.extra["revision_comparison"]["same_scenarios"] is True
    assert revised.extra["revision_comparison"]["independent_validation"] is False


@pytest.mark.parametrize("entrypoint", ["rehearse", "attach_mirofish", "attach_suite"])
def test_structured_revision_never_launches_original_source(
    tmp_settings, monkeypatch, entrypoint
):
    coordinator, baseline = _stored_run(tmp_settings)
    coordinator.llm = RevisionLLM(baseline.ir)
    revised = coordinator.revise(baseline.run_id, "Clarify the badge rule.")
    coordinator.settings.mirofish_base_url = "http://mirofish.invalid"
    coordinator.settings.mirofish_auto_launch = True
    calls = []

    def unexpected_launch(*args, **kwargs):
        calls.append(kwargs)
        raise AssertionError("Original prose must not be sent as revised policy")

    monkeypatch.setattr("app.services.coordinator.run_swarm", unexpected_launch)
    monkeypatch.setattr("app.services.coordinator.launch_mirofish", unexpected_launch)
    if entrypoint == "rehearse":
        result = coordinator.rehearse(revised.run_id, swarm=True)
    elif entrypoint == "attach_mirofish":
        result = coordinator.attach_mirofish(revised.run_id, launch=True)
    else:
        result = coordinator.attach_suite(revised.run_id, revised.suite)

    assert calls == []
    assert result.ir.revision == 2
    assert result.document.text == baseline.document.text
    assert result.suite.suite_id == baseline.suite.suite_id
    assert result.suite.scenarios == baseline.suite.scenarios
    assert result.evaluation.policy_revision == 2
    assert result.mirofish.launch.attempted is False
    assert result.mirofish.launch.ok is False
    assert "wording is unverified" in result.mirofish.launch.error
    assert "swarm" not in result.extra


def test_replacing_suite_invalidates_previous_swarm(tmp_settings):
    coordinator, baseline = _stored_run(tmp_settings)
    replacement = ScenarioSuite(
        policy_id=baseline.ir.policy_id,
        policy_revision=1,
        seed="new",
        scenarios=[
            Scenario(
                kind="normal", title="New audience", facts={"action.name": "comply"}
            )
        ],
    )
    result = coordinator.attach_suite(baseline.run_id, replacement)
    assert "swarm" not in result.extra
    assert result.effectiveness.swarm_used is False
    assert (
        result.extra["evidence_history"][-1]["swarm"]["simulation_id"]
        == "baseline-swarm"
    )


class FailedRevisionLLM:
    enabled = True

    def complete_json(self, **kwargs):
        raise LLMError("sensitive upstream provider response")


def test_failed_live_revision_preserves_active_evidence(tmp_settings):
    coordinator, baseline = _stored_run(tmp_settings)
    coordinator.llm = FailedRevisionLLM()
    result = coordinator.revise(baseline.run_id, "Clarify the badge rule.")
    assert result.status == "failed"
    assert result.ir == baseline.ir
    assert result.suite == baseline.suite
    assert result.evaluation == baseline.evaluation
    assert result.effectiveness == baseline.effectiveness
    assert result.extra["swarm"] == baseline.extra["swarm"]
    assert "sensitive" not in result.error
    stored = coordinator.store.get(baseline.run_id)
    assert stored.ir == baseline.ir


def test_disabled_provider_cannot_claim_a_completed_revision(tmp_settings):
    coordinator, baseline = _stored_run(tmp_settings)
    result = coordinator.revise(baseline.run_id, "Clarify the badge rule.")
    assert result.status == "failed"
    assert result.ir.revision == baseline.ir.revision
    assert result.ir.rules == baseline.ir.rules


def test_direct_live_revision_failure_is_explicit():
    with pytest.raises(ValueError, match="revision") as caught:
        revise_policy_ir(policy(), "Clarify badges.", llm=FailedRevisionLLM())
    assert "sensitive" not in str(caught.value)


@pytest.mark.parametrize("field", ["title", "details"])
def test_description_only_revision_cannot_claim_executable_change(field):
    ir = policy()

    class DescriptionOnlyLLM:
        enabled = True

        def complete_json(self, **kwargs):
            raw = ir.model_dump(mode="json")
            if field == "title":
                raw["rules"][0]["title"] = "Clearer badge wording"
            else:
                raw["rules"][0]["then"][0]["details"] = "Clearer badge wording"
            raw["rules"][0]["citations"] = [{"quote": "Visitors must wear badges."}]
            return raw

    with pytest.raises(ValueError, match="executable"):
        revise_policy_ir(ir, "Clarify badges.", llm=DescriptionOnlyLLM())


def test_failed_swarm_rerun_does_not_reuse_previous_success(tmp_settings, monkeypatch):
    coordinator, baseline = _stored_run(tmp_settings)
    coordinator.settings.mirofish_base_url = "http://mirofish.invalid"

    def failed(*args, **kwargs):
        raise SwarmError("synthetic timeout")

    monkeypatch.setattr("app.services.coordinator.run_swarm", failed)
    result = coordinator.rehearse(baseline.run_id, swarm=True)
    assert "swarm" not in result.extra
    assert result.effectiveness.swarm_used is False
    assert result.effectiveness.interaction_verified is False
    assert result.error is not None
    assert (
        result.extra["evidence_history"][-1]["swarm"]["simulation_id"]
        == "baseline-swarm"
    )
