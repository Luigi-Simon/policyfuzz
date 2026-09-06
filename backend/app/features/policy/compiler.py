"""Validated deterministic and LLM-backed policy compilation."""

from __future__ import annotations

from dataclasses import dataclass

from app.core.hashing import canonical_sha256
from app.domain.models import (
    CompilePolicyRequest,
    InvariantSuggestion,
    InvariantSuggestions,
    LLMRequest,
    PolicyCompilation,
    PolicyIR,
)
from app.domain.protocols import LLMClient, PolicyCompiler
from app.features.policy.extraction import (
    assign_baseline_rule_ids,
    canonical_predicates,
    extract_policy,
    validate_policy_extraction,
)
from app.features.policy.model_output import complete_typed
from app.features.policy.prompts import build_invariant_suggestion_prompt


def compile_baseline_policy(request: CompilePolicyRequest) -> PolicyCompilation:
    """Build a provisional baseline without invoking or trusting a model."""

    if request.extraction is None:
        raise ValueError("POLICY_EXTRACTION_REQUIRED")
    validated = validate_policy_extraction(request.document, request.extraction)
    rules = assign_baseline_rule_ids(
        request.document,
        validated.extraction.rules,
    )
    identity = canonical_sha256(
        {
            "document_sha256": request.document.document_sha256,
            "rule_ids": tuple(rule.rule_id for rule in rules),
            "unsupported_clauses": validated.extraction.unsupported_clauses,
        }
    )
    policy = PolicyIR(
        policy_id=f"policy-{identity}",
        document_sha256=request.document.document_sha256,
        kind="compiled_baseline",
        review_status="provisional",
        base_currency="SGD",
        rules=rules,
        unsupported_clauses=validated.extraction.unsupported_clauses,
    )
    return PolicyCompilation(
        policy=policy,
        excluded_rule_count=validated.excluded_rule_count,
    )


def _normalize_suggestion(item: InvariantSuggestion) -> InvariantSuggestion:
    assertion = item.assertion
    normalized_when = canonical_predicates(item.when)
    assertion_id = "assertion-" + canonical_sha256(
        {
            "when": normalized_when,
            "target_kind": assertion.target_kind,
            "dimension": assertion.dimension,
            "operator": assertion.operator,
            "expected_value": assertion.expected_value,
        }
    )
    normalized_assertion = assertion.model_copy(update={"assertion_id": assertion_id})
    invariant_id = "invariant-" + canonical_sha256(
        {
            "when": normalized_when,
            "assertion": normalized_assertion,
        }
    )
    return item.model_copy(
        update={
            "invariant_id": invariant_id,
            "when": normalized_when,
            "assertion": normalized_assertion,
            "origin": "model_suggestion",
        }
    )


@dataclass(frozen=True, slots=True)
class LLMPolicyCompiler(PolicyCompiler):
    """Provider-neutral compiler with typed extraction and intent suggestions."""

    llm: LLMClient

    async def compile(self, request: CompilePolicyRequest) -> PolicyCompilation:
        extraction = request.extraction
        if extraction is None:
            extraction = await extract_policy(self.llm, request)
        baseline = compile_baseline_policy(
            request.model_copy(update={"extraction": extraction})
        )

        prompt = build_invariant_suggestion_prompt(baseline.policy)
        llm_request = LLMRequest(
            operation="invariant_suggestion",
            system_instructions=prompt.system_instructions,
            untrusted_payload_json=prompt.policy_payload_json,
            response_schema=InvariantSuggestions.model_json_schema(),
            response_schema_name="InvariantSuggestions",
        )
        suggestions = await complete_typed(
            self.llm,
            request=llm_request,
            response_model=InvariantSuggestions,
            repair_operation="invariant_suggestion",
        )
        normalized = InvariantSuggestions(
            invariant_drafts=tuple(
                _normalize_suggestion(item) for item in suggestions.invariant_drafts
            )
        )
        return baseline.model_copy(
            update={"invariant_drafts": normalized.invariant_drafts}
        )
