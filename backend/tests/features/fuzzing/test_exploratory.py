"""Oracle-free exploratory model boundary."""

from copy import deepcopy
from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from app.core.fakes import ScriptedLLMClient
from app.core.hashing import canonical_sha256
from app.domain.models import GenerationConfig, LLMResponse, Predicate, RunManifest
from app.features.fuzzing.exploratory import (
    ExploratoryBatchPayload,
    ModelOutputValidationError,
    PromptCommitmentError,
    generate_exploratory_candidates,
)
from app.features.fuzzing.prompts import (
    EXPLORATORY_SCHEMA_NAME,
    EXPLORATORY_SYSTEM_INSTRUCTIONS,
    REPAIR_SYSTEM_INSTRUCTIONS,
    exploratory_prompt_commitment,
    exploratory_prompt_sha256,
)
from tests.domain.factories import (
    make_invariant,
    make_policy,
    make_policy_contract,
    make_rule,
)


def valid_exploratory_payload() -> dict:
    return {
        "scenarios": [
            {
                "category": "adversarial",
                "facts": {
                    "employee_role": "employee",
                    "expense_category": "meal",
                    "amount_minor": 7_777,
                    "destination_type": "international",
                    "booking_days_before": 3,
                    "receipt_present": False,
                    "approval_roles_present": ["manager"],
                    "prior_same_day_category_spend_minor": 2_000,
                },
                "target_rule_ids": ["rule-meal"],
                "target_invariant_ids": ["invariant-0"],
                "rationale": "Exercises an unusual but valid combination of input facts.",
            }
        ]
    }


def manifest(*, committed: bool = True) -> RunManifest:
    return RunManifest(
        manifest_id="manifest-1",
        run_id="run-1",
        engine_version="1.0",
        engine_sha256="e" * 64,
        prompt_hashes=(exploratory_prompt_commitment(),) if committed else (),
        provider="scripted",
        model_identifier="scripted-model",
        generation_config=GenerationConfig(),
        random_seed=42,
        started_at=datetime(2026, 9, 6, tzinfo=UTC),
        mode="cached",
    )


def request() -> dict:
    return {
        "operation": "scenario_generation",
        "policy": make_policy(),
        "contract": make_policy_contract(),
        "manifest": manifest(),
        "requested_rule_ids": frozenset({"rule-meal"}),
        "requested_invariant_ids": frozenset({"invariant-0"}),
        "existing_scenarios": (),
        "used_fact_sha256s": frozenset(),
        "count": 1,
        "seed": 42,
    }


def test_exploratory_schema_forbids_model_authored_oracle() -> None:
    payload = valid_exploratory_payload()
    payload["scenarios"][0]["assertions"] = [
        {"dimension": "eligibility", "expected": "deny"}
    ]
    with pytest.raises(ValidationError):
        ExploratoryBatchPayload.model_validate(payload)


def test_exploratory_schema_does_not_let_model_claim_boundary_ownership() -> None:
    payload = valid_exploratory_payload()
    payload["scenarios"][0]["category"] = "boundary"

    with pytest.raises(ValidationError):
        ExploratoryBatchPayload.model_validate(payload)


def test_prompt_commitment_binds_schema_and_every_trusted_instruction() -> None:
    schema = ExploratoryBatchPayload.model_json_schema()
    expected = canonical_sha256(
        {
            "schema_name": EXPLORATORY_SCHEMA_NAME,
            "system_instructions": {
                "initial": EXPLORATORY_SYSTEM_INSTRUCTIONS,
                "repair": REPAIR_SYSTEM_INSTRUCTIONS,
            },
            "response_schema": schema,
        }
    )
    changed_schema = deepcopy(schema)
    changed_schema["title"] = "changed-private-schema"

    assert exploratory_prompt_commitment().prompt_sha256 == expected
    assert exploratory_prompt_sha256(changed_schema) != expected


@pytest.mark.asyncio
async def test_request_rejects_manifest_without_exact_prompt_schema_commitment() -> (
    None
):
    llm = ScriptedLLMClient([LLMResponse(output=valid_exploratory_payload())])
    arguments = request() | {"manifest": manifest(committed=False)}

    with pytest.raises(PromptCommitmentError, match="PROMPT_COMMITMENT_MISMATCH"):
        await generate_exploratory_candidates(llm, **arguments)

    assert llm.requests == []


@pytest.mark.asyncio
async def test_invalid_output_gets_one_sanitized_repair() -> None:
    llm = ScriptedLLMClient(
        [
            LLMResponse(output={"scenarios": [{"assertions": []}]}),
            LLMResponse(output=valid_exploratory_payload()),
        ]
    )
    candidates = await generate_exploratory_candidates(llm, **request())

    assert len(candidates) == 1
    assert candidates[0].assertions == ()
    assert candidates[0].origins == frozenset({"llm_exploratory"})
    assert [item.operation for item in llm.requests] == [
        "scenario_generation",
        "scenario_generation",
    ]
    assert [item.repair_attempt for item in llm.requests] == [0, 1]
    assert all(
        item.response_schema_name == "policyfuzz_exploratory_batch_v1"
        for item in llm.requests
    )
    assert llm.requests[0].generation_config.temperature_milli == 400
    assert llm.requests[0].generation_config.max_output_tokens == 1_800


@pytest.mark.asyncio
async def test_second_invalid_output_raises_safe_error_without_raw_values() -> None:
    secret = "DO-NOT-LEAK-POLICY-OR-OUTPUT"
    llm = ScriptedLLMClient(
        [
            LLMResponse(output={"invalid": secret}),
            LLMResponse(output={"still_invalid": secret}),
        ]
    )

    with pytest.raises(ModelOutputValidationError) as raised:
        await generate_exploratory_candidates(llm, **request())
    assert raised.value.code == "SCENARIO_OUTPUT_INVALID"
    assert raised.value.repair_attempted is True
    assert secret not in str(raised.value)


@pytest.mark.asyncio
async def test_prompt_excludes_existing_assertions_and_model_output_boundaries() -> (
    None
):
    llm = ScriptedLLMClient([LLMResponse(output=valid_exploratory_payload())])
    await generate_exploratory_candidates(llm, **request())
    sent = llm.requests[0]

    assert "expected_value" not in sent.untrusted_payload_json
    assert "assertion" not in sent.untrusted_payload_json
    assert "Do not create exact numeric boundary cases" in sent.system_instructions


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("policy", "contract"),
    (
        (
            make_policy(
                rules=(
                    make_rule(
                        when=(
                            Predicate(
                                field="amount_minor", operator="gte", value=7_777
                            ),
                        )
                    ),
                )
            ),
            make_policy_contract(),
        ),
        (
            make_policy(),
            make_policy_contract(
                invariants=(
                    make_invariant(
                        0,
                        when=(
                            Predicate(
                                field="daily_category_total_minor",
                                operator="eq",
                                value=9_777,
                            ),
                        ),
                    ),
                    make_invariant(1),
                    make_invariant(2),
                )
            ),
        ),
    ),
)
async def test_exact_stored_or_derived_numeric_threshold_gets_python_owned_repair(
    policy, contract
) -> None:
    repaired = valid_exploratory_payload()
    repaired["scenarios"][0]["facts"]["amount_minor"] = 7_778
    llm = ScriptedLLMClient(
        [
            LLMResponse(output=valid_exploratory_payload()),
            LLMResponse(output=repaired),
        ]
    )

    candidates = await generate_exploratory_candidates(
        llm,
        **(request() | {"policy": policy, "contract": contract}),
    )

    assert candidates[0].facts.amount_minor == 7_778
    assert [item.repair_attempt for item in llm.requests] == [0, 1]
