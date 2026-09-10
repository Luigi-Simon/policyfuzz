"""Offline trust-boundary tests for the friend's Judge adapter contract."""

from copy import deepcopy

import pytest
from pydantic import ValidationError

from app.v2.judge_contracts import JudgeRequest, JudgeResult, validate_judge_result
from app.v2.judge_examples import make_judge_example


@pytest.mark.parametrize("kind", ["complete", "partial", "unscored"])
def test_authored_examples_validate(kind):
    request, result = make_judge_example(kind)
    validate_judge_result(request, result)
    assert result.execution_mode.value == "fixture"
    assert "original_records" not in request.model_dump_json()


def test_a_judge_cannot_return_metric_verdict_fields():
    _, result = make_judge_example()
    data = result.model_dump(mode="json")
    data["passed"] = 999
    with pytest.raises(ValidationError):
        JudgeResult.model_validate(data)


@pytest.mark.parametrize(
    "field", ["run_id", "policy_text_sha256", "request_fingerprint"]
)
def test_rejects_stale_evidence(field):
    request, result = make_judge_example()
    replacement = "0" * 64 if field != "run_id" else "different-run"
    changed = result.model_copy(update={field: replacement})
    with pytest.raises(ValueError):
        validate_judge_result(request, changed)


def test_rejects_invented_metric_citation():
    request, result = make_judge_example()
    data = result.model_dump(mode="json")
    data["cons"][0]["citations"][0]["id"] = "invented-case"
    with pytest.raises(ValueError):
        validate_judge_result(request, JudgeResult.model_validate(data))


def test_partial_translation_cannot_be_cited_as_available_evidence():
    request, result = make_judge_example("partial")
    missing = next(
        m
        for m in request.sandbox.messages
        if m.translation_status.value == "unavailable"
    )
    data = result.model_dump(mode="json")
    data["key_interactions"] = [
        {
            "text": "A stakeholder made a specific objection.",
            "citations": [
                {"kind": "sandbox_message", "id": missing.message_id, "case_id": None}
            ],
        }
    ]
    with pytest.raises(ValueError):
        validate_judge_result(request, JudgeResult.model_validate(data))


def test_unscored_evidence_cannot_support_pilot_recommendation():
    request, result = make_judge_example("unscored")
    changed = result.model_copy(update={"recommendation": "consider_limited_pilot"})
    with pytest.raises(ValueError):
        validate_judge_result(request, changed)


def test_findings_require_citations_and_english_display():
    _, result = make_judge_example()
    data = result.model_dump(mode="json")
    uncited = deepcopy(data)
    uncited["cons"][0]["citations"] = []
    with pytest.raises(ValidationError):
        JudgeResult.model_validate(uncited)
    data["cons"][0]["text"] = "政策有问题"
    with pytest.raises(ValidationError):
        JudgeResult.model_validate(data)
    data["cons"][0]["text"] = "   "
    with pytest.raises(ValidationError):
        JudgeResult.model_validate(data)


def test_metric_failures_cannot_be_overridden_with_pilot_recommendation():
    request, result = make_judge_example()
    assert request.metric.failed > 0
    changed = result.model_copy(update={"recommendation": "consider_limited_pilot"})
    with pytest.raises(ValueError):
        validate_judge_result(request, changed)


def test_request_cannot_mix_run_evidence():
    request, _ = make_judge_example()
    data = request.model_dump(mode="json")
    data["sandbox"]["run_id"] = "unrelated-run"
    with pytest.raises(ValidationError):
        JudgeRequest.model_validate(data)


def test_a_step_reference_must_resolve_inside_its_case():
    request, result = make_judge_example()
    data = result.model_dump(mode="json")
    data["cons"][0]["citations"] = [
        {
            "kind": "metric_step",
            "id": "invented-step",
            "case_id": request.metric.cases[0].case_id,
        }
    ]
    with pytest.raises(ValueError):
        validate_judge_result(request, JudgeResult.model_validate(data))


def test_partial_cannot_be_disguised_as_complete():
    request, result = make_judge_example("partial")
    changed = result.model_copy(update={"status": "completed"})
    with pytest.raises(ValueError):
        validate_judge_result(request, changed)
