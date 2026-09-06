import pytest
from pydantic import ValidationError

from app.domain.models import (
    AssertionResult,
    DimensionResult,
    Finding,
    ScenarioEvaluation,
    TraceRef,
)

from .factories import HASH, make_trace


@pytest.mark.parametrize(
    "changes",
    [
        {"status": "VALUE", "value": None},
        {"status": "GAP", "value": 5000},
        {"status": "VALUE", "value": "allow"},
        {"status": "CONFLICT", "conflicting_values": (5000,)},
        {"status": "CONFLICT", "conflicting_values": (5000, 5000)},
        {"status": "ERROR", "conflicting_values": (5000, 6000)},
    ],
)
def test_dimension_result_cannot_claim_an_invalid_resolution(changes):
    with pytest.raises(ValidationError):
        DimensionResult(
            **({"dimension": "claim_cap_minor", "status": "VALUE"} | changes)
        )


def test_conflict_preserves_all_values_without_selecting_a_winner():
    result = DimensionResult(
        dimension="claim_cap_minor", status="CONFLICT", conflicting_values=(5000, 6000)
    )
    assert result.value is None
    assert result.model_validate_json(result.model_dump_json()) == result


@pytest.mark.parametrize("verdict", ["PASS", "FAIL"])
def test_resolved_effect_without_frozen_assertion_is_unscored(verdict):
    with pytest.raises(ValidationError):
        ScenarioEvaluation(
            scenario_id="scenario-0", trace=make_trace(), verdict=verdict
        )
    assert (
        ScenarioEvaluation(
            scenario_id="scenario-0", trace=make_trace(), verdict="UNSCORED"
        ).assertion_results
        == ()
    )


def test_scenario_verdict_does_not_contradict_assertion_results():
    with pytest.raises(ValidationError):
        ScenarioEvaluation(
            scenario_id="scenario-0",
            trace=make_trace(),
            verdict="PASS",
            assertion_results=(AssertionResult(assertion_id="a", status="FAIL"),),
        )
    with pytest.raises(ValidationError):
        ScenarioEvaluation(
            scenario_id="scenario-0",
            trace=make_trace(),
            verdict="FAIL",
            assertion_results=(AssertionResult(assertion_id="a", status="PASS"),),
        )


def make_finding(**changes):
    values = {
        "finding_id": "f1",
        "fingerprint_sha256": HASH,
        "finding_type": "structural_gap",
        "evidence_level": "mechanically_reproduced",
        "scenario_ids": ("s1",),
        "dimension": "claim_cap_minor",
        "traces": (TraceRef(scenario_id="s1", trace_sha256=HASH),),
    }
    return Finding(**(values | changes))


@pytest.mark.parametrize(
    "changes",
    [
        {"severity": "high"},
        {"severity": "high", "severity_origin": "session_invariant"},
        {"finding_type": "potential_loophole"},
        {"finding_type": "intent_breach"},
        {"finding_type": "regression"},
        {"scenario_ids": ("s2",)},
        {
            "evidence_level": "candidate",
            "severity": "high",
            "severity_origin": "session_reviewer",
        },
    ],
)
def test_finding_requires_appropriate_independent_evidence(changes):
    with pytest.raises(ValidationError):
        make_finding(**changes)


def test_session_reviewer_can_assign_severity_to_structural_finding():
    finding = make_finding(severity="high", severity_origin="session_reviewer")
    assert finding.model_validate_json(finding.model_dump_json()) == finding
