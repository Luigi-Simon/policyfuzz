"""Constrained LLM boundary for oracle-free exploratory scenario facts."""

from __future__ import annotations

import json
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from app.core.hashing import canonical_sha256
from app.domain.models import (
    GenerationConfig,
    LLMOperation,
    LLMRequest,
    PolicyContract,
    PolicyIR,
    RunManifest,
    Scenario,
    ScenarioCandidate,
    ScenarioFacts,
)
from app.domain.protocols import LLMClient
from app.features.fuzzing.constants import MAX_SCENARIOS
from app.features.fuzzing.prompts import (
    EXPLORATORY_SCHEMA_NAME,
    EXPLORATORY_SYSTEM_INSTRUCTIONS,
    REPAIR_SYSTEM_INSTRUCTIONS,
    exploratory_prompt_commitment,
)


class _PrivateModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)


class ExploratoryScenarioPayload(_PrivateModel):
    """Provider output: facts and targeting hints, never scored answers."""

    category: Literal["normal", "adversarial"]
    facts: ScenarioFacts
    target_rule_ids: tuple[str, ...] = ()
    target_invariant_ids: tuple[str, ...] = ()
    rationale: Annotated[str, Field(min_length=1, max_length=240)]


class ExploratoryBatchPayload(_PrivateModel):
    scenarios: Annotated[tuple[ExploratoryScenarioPayload, ...], Field(max_length=15)]


class ModelOutputValidationError(ValueError):
    """Sanitized terminal model-output error with no source values."""

    __slots__ = ("code", "repair_attempted")

    def __init__(self, *, repair_attempted: bool) -> None:
        self.code = "SCENARIO_OUTPUT_INVALID"
        self.repair_attempted = repair_attempted
        super().__init__(self.code)


class PromptCommitmentError(ValueError):
    """The run manifest does not bind the exact prompt/schema request surface."""

    def __init__(self) -> None:
        super().__init__("PROMPT_COMMITMENT_MISMATCH")


def _safe_json(value: object) -> str:
    def json_default(item: object) -> object:
        if isinstance(item, BaseModel):
            return item.model_dump(mode="json")
        if isinstance(item, (set, frozenset)):
            return sorted(item)
        raise TypeError(f"unsupported JSON value: {type(item).__name__}")

    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
        default=json_default,
    )


def _input_payload(
    *,
    policy: PolicyIR,
    contract: PolicyContract,
    manifest: RunManifest,
    requested_rule_ids: frozenset[str],
    requested_invariant_ids: frozenset[str],
    existing_scenarios: tuple[Scenario, ...],
    used_fact_sha256s: frozenset[str],
    count: int,
    seed: int,
) -> dict[str, object]:
    return {
        "policy": {
            "policy_id": policy.policy_id,
            "base_currency": policy.base_currency,
            "rules": tuple(
                {"rule_id": rule.rule_id, "when": rule.when} for rule in policy.rules
            ),
        },
        "contract": {
            "contract_id": contract.contract_id,
            "invariants": tuple(
                {"invariant_id": item.invariant_id, "when": item.when}
                for item in contract.invariants
            ),
        },
        "manifest": {
            "manifest_id": manifest.manifest_id,
            "engine_version": manifest.engine_version,
        },
        "requested_rule_ids": requested_rule_ids,
        "requested_invariant_ids": requested_invariant_ids,
        "existing_scenarios": tuple(
            {
                "category": item.category,
                "facts": item.facts,
                "target_rule_ids": item.target_rule_ids,
                "target_invariant_ids": item.target_invariant_ids,
                "partition": item.partition,
            }
            for item in existing_scenarios
        ),
        "used_fact_sha256s": used_fact_sha256s,
        "requested_count": count,
        "seed": seed,
    }


def _numeric_thresholds(
    policy: PolicyIR, contract: PolicyContract
) -> dict[str, frozenset[int]]:
    result: dict[str, set[int]] = {}
    condition_groups = (
        *(rule.when for rule in policy.rules),
        *(invariant.when for invariant in contract.invariants),
    )
    for conditions in condition_groups:
        for condition in conditions:
            if type(condition.value) is int:
                result.setdefault(condition.field, set()).add(condition.value)
    return {field: frozenset(values) for field, values in result.items()}


def _uses_exact_numeric_boundary(
    facts: ScenarioFacts, thresholds: dict[str, frozenset[int]]
) -> bool:
    values = facts.model_dump()
    values["daily_category_total_minor"] = (
        facts.amount_minor + facts.prior_same_day_category_spend_minor
    )
    return any(
        values.get(field) in boundaries for field, boundaries in thresholds.items()
    )


def _parse(
    response_output: object,
    *,
    count: int,
    thresholds: dict[str, frozenset[int]],
) -> ExploratoryBatchPayload:
    try:
        raw = (
            response_output
            if isinstance(response_output, str)
            else _safe_json(response_output)
        )
        batch = ExploratoryBatchPayload.model_validate_json(raw, strict=True)
    except (TypeError, ValueError, ValidationError, json.JSONDecodeError):
        raise ModelOutputValidationError(repair_attempted=False) from None
    if len(batch.scenarios) > count or any(
        _uses_exact_numeric_boundary(item.facts, thresholds) for item in batch.scenarios
    ):
        raise ModelOutputValidationError(repair_attempted=False)
    return batch


def _request(
    *,
    operation: LLMOperation,
    payload: dict[str, object],
    seed: int,
    repair_attempt: Literal[0, 1],
) -> LLMRequest:
    return LLMRequest(
        operation=operation,
        system_instructions=(
            EXPLORATORY_SYSTEM_INSTRUCTIONS
            if repair_attempt == 0
            else REPAIR_SYSTEM_INSTRUCTIONS
        ),
        untrusted_payload_json=_safe_json(payload),
        response_schema=ExploratoryBatchPayload.model_json_schema(),
        response_schema_name=EXPLORATORY_SCHEMA_NAME,
        generation_config=GenerationConfig(
            temperature_milli=400,
            max_output_tokens=1_800,
            seed=seed,
        ),
        repair_attempt=repair_attempt,
    )


def exploratory_response_example(
    *,
    rule_id: str = "rule-example",
    invariant_id: str = "invariant-example",
) -> dict[str, object]:
    """Return a complete offline response fixture for API/workflow scripts."""

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
                "target_rule_ids": [rule_id],
                "target_invariant_ids": [invariant_id],
                "rationale": "Exercises an unusual but valid combination of input facts.",
            }
        ]
    }


async def generate_exploratory_candidates(
    llm: LLMClient,
    *,
    operation: LLMOperation,
    policy: PolicyIR,
    contract: PolicyContract,
    manifest: RunManifest,
    requested_rule_ids: frozenset[str],
    requested_invariant_ids: frozenset[str],
    existing_scenarios: tuple[Scenario, ...],
    used_fact_sha256s: frozenset[str],
    count: int,
    seed: int,
) -> tuple[ScenarioCandidate, ...]:
    """Generate input facts with one bounded, sanitized schema repair."""

    if operation not in {"scenario_generation", "targeted_scenario_generation"}:
        raise ValueError("operation must generate scenarios")
    if type(count) is not int or not 0 <= count <= MAX_SCENARIOS:
        raise ValueError("count must be between zero and fifteen")
    if count == 0:
        return ()
    if exploratory_prompt_commitment() not in manifest.prompt_hashes:
        raise PromptCommitmentError()
    thresholds = _numeric_thresholds(policy, contract)
    payload = _input_payload(
        policy=policy,
        contract=contract,
        manifest=manifest,
        requested_rule_ids=requested_rule_ids,
        requested_invariant_ids=requested_invariant_ids,
        existing_scenarios=existing_scenarios,
        used_fact_sha256s=used_fact_sha256s,
        count=count,
        seed=seed,
    )
    try:
        response = await llm.complete_json(
            _request(operation=operation, payload=payload, seed=seed, repair_attempt=0)
        )
        batch = _parse(response.output, count=count, thresholds=thresholds)
    except ModelOutputValidationError:
        repair_payload = payload | {"validation_codes": ("SCENARIO_OUTPUT_INVALID",)}
        response = await llm.complete_json(
            _request(
                operation=operation,
                payload=repair_payload,
                seed=seed,
                repair_attempt=1,
            )
        )
        try:
            batch = _parse(response.output, count=count, thresholds=thresholds)
        except ModelOutputValidationError:
            raise ModelOutputValidationError(repair_attempted=True) from None

    return tuple(
        ScenarioCandidate(
            candidate_id="candidate-"
            + canonical_sha256(
                {
                    "category": item.category,
                    "facts": item.facts,
                    "target_rule_ids": tuple(sorted(set(item.target_rule_ids))),
                    "target_invariant_ids": tuple(
                        sorted(set(item.target_invariant_ids))
                    ),
                    "partition": "visible",
                }
            ),
            category=item.category,
            origins=frozenset({"llm_exploratory"}),
            facts=item.facts,
            target_rule_ids=tuple(sorted(set(item.target_rule_ids))),
            target_invariant_ids=tuple(sorted(set(item.target_invariant_ids))),
        )
        for item in batch.scenarios
    )
