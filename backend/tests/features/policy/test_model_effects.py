import json

import pytest

from app.core.fakes import ScriptedLLMClient
from app.domain.models import CompilePolicyRequest, Effect, LLMResponse
from app.features.policy.extraction import extract_policy
from app.features.policy.ingest import ingest_policy_text
from app.features.policy.model_io import ModelPolicyExtraction
from app.features.policy.model_output import (
    ModelOutputValidationError,
    parse_typed_output,
)
from app.features.policy.prompts import build_policy_extraction_prompt


def _document():
    return ingest_policy_text(
        title="Synthetic schema test",
        text="Claims have eligibility, receipt and approval requirements, and caps.",
        source_type="pasted_text",
    )


def _payload(document, dimension, value):
    prompt = build_policy_extraction_prompt(document)
    handle = json.loads(prompt.policy_payload_json)["citation_catalog"][0][
        "citation_handle"
    ]
    return {
        "document_sha256": document.document_sha256,
        "rules": [
            {
                "rule_handle": "rule_1",
                "citation_handle": handle,
                "description": "Synthetic effect schema candidate",
                "when": [],
                "effects": [{"dimension": dimension, "value": value}],
                "overrides": [],
            }
        ],
        "unsupported_clauses": [],
    }


def test_provider_schema_exposes_each_dimensions_actual_value_constraints():
    schema = json.loads(
        build_policy_extraction_prompt(_document()).response_schema_json
    )
    items = schema["$defs"]["ModelRuleDraft"]["properties"]["effects"]["items"]
    mapping = items["discriminator"]["mapping"]
    assert items["discriminator"]["propertyName"] == "dimension"
    assert set(mapping) == {
        "eligibility",
        "receipt_requirement",
        "approval_requirement",
        "claim_cap_minor",
        "daily_category_cap_minor",
    }
    expected_enums = {
        "eligibility": {"allow", "deny"},
        "receipt_requirement": {"required", "not_required"},
        "approval_requirement": {"none", "manager", "director", "finance"},
    }
    for dimension, reference in mapping.items():
        branch = schema["$defs"][reference.rsplit("/", 1)[1]]
        assert branch["properties"]["dimension"]["const"] == dimension
        value = branch["properties"]["value"]
        if dimension in expected_enums:
            assert set(value["enum"]) == expected_enums[dimension]
        else:
            assert value["type"] == "integer"
            assert value["minimum"] == 0


@pytest.mark.parametrize(
    ("dimension", "value", "error_code"),
    [
        ("approval_requirement", "not_required", "literal_error"),
        ("claim_cap_minor", True, "int_type"),
        ("daily_category_cap_minor", -1, "greater_than_equal"),
    ],
)
def test_invalid_dimension_value_pairs_fail_private_schema_constraints(
    dimension, value, error_code
):
    payload = _payload(_document(), dimension, value)
    with pytest.raises(ModelOutputValidationError) as caught:
        parse_typed_output(json.dumps(payload), response_model=ModelPolicyExtraction)
    assert any(code == error_code for _, code in caught.value.issues)


async def test_invalid_approval_literal_repairs_once_to_supported_none_value():
    document = _document()
    llm = ScriptedLLMClient(
        (
            LLMResponse(
                output=_payload(document, "approval_requirement", "not_required")
            ),
            LLMResponse(output=_payload(document, "approval_requirement", "none")),
        )
    )

    extraction = await extract_policy(llm, CompilePolicyRequest(document=document))

    assert extraction.rules[0].effects[0] == Effect(
        dimension="approval_requirement", value="none"
    )
    assert len(llm.requests) == 2
    feedback = json.loads(llm.requests[1].untrusted_payload_json)[
        "policyfuzz_validation_feedback"
    ]
    assert any(issue["code"] == "literal_error" for issue in feedback["issues"])
    assert "not_required" not in json.dumps(feedback)


@pytest.mark.parametrize(
    ("dimension", "value"),
    [
        ("eligibility", "allow"),
        ("receipt_requirement", "required"),
        ("approval_requirement", "manager"),
        ("claim_cap_minor", 0),
        ("daily_category_cap_minor", 12_345),
    ],
)
async def test_all_five_private_effect_variants_hydrate_frozen_public_effects(
    dimension, value
):
    document = _document()
    llm = ScriptedLLMClient((LLMResponse(output=_payload(document, dimension, value)),))

    extraction = await extract_policy(llm, CompilePolicyRequest(document=document))

    effect = extraction.rules[0].effects[0]
    assert type(effect) is Effect
    assert effect.dimension == dimension
    assert effect.value == value
    assert len(llm.requests) == 1
