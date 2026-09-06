"""Small synthetic fixtures for the public version-1 domain contracts."""

from app.domain.models import (
    Assertion,
    Effect,
    Invariant,
    PolicyContract,
    PolicyIR,
    Rule,
    Scenario,
    ScenarioCandidate,
    ScenarioFacts,
    ScenarioSuite,
    SourceSpan,
    TextRuleProvenance,
)

HASH = "a" * 64


def make_span(**changes):
    return SourceSpan(
        **dict(
            page=1, start=0, end=12, quote="Meals capped", quote_sha256=HASH, **changes
        )
    )


def make_rule(**changes):
    values = {
        "rule_id": "rule-meal",
        "revision": 0,
        "description": "Meal cap",
        "when": (),
        "effects": (Effect(dimension="claim_cap_minor", value=5000),),
        "overrides": (),
        "provenance": TextRuleProvenance(citation_id="citation-meal", span=make_span()),
        "confidence_percent": 95,
    }
    return Rule(**(values | changes))


def make_assertion(**changes):
    values = {
        "assertion_id": "assertion-cap",
        "target_kind": "effect_value",
        "dimension": "claim_cap_minor",
        "operator": "lte",
        "expected_value": 5000,
        "origin": "session_confirmed",
        "source_invariant_id": "invariant-cap",
    }
    return Assertion(**(values | changes))


def make_invariant(index=0, **changes):
    values = {
        "invariant_id": f"invariant-{index}",
        "description": "Claims stay within cap",
        "when": (),
        "assertion": make_assertion(
            assertion_id=f"assertion-{index}", source_invariant_id=f"invariant-{index}"
        ),
        "severity": "high",
        "origin": "session_confirmed",
    }
    return Invariant(**(values | changes))


def make_policy_contract(**changes):
    values = {
        "contract_id": "contract-1",
        "required_dimensions": frozenset({"claim_cap_minor"}),
        "invariants": tuple(make_invariant(i) for i in range(3)),
    }
    return PolicyContract(**(values | changes))


def make_policy(**changes):
    values = {
        "policy_id": "policy-1",
        "document_sha256": HASH,
        "kind": "compiled_baseline",
        "review_status": "session_confirmed",
        "rules": (make_rule(),),
        "unsupported_clauses": (),
    }
    return PolicyIR(**(values | changes))


def make_facts(**changes):
    values = {
        "employee_role": "employee",
        "expense_category": "meal",
        "amount_minor": 5000,
        "destination_type": "domestic",
        "booking_days_before": 0,
        "receipt_present": True,
        "approval_roles_present": frozenset(),
        "prior_same_day_category_spend_minor": 0,
    }
    return ScenarioFacts(**(values | changes))


def make_scenario(index=0, **changes):
    values = {
        "scenario_id": f"scenario-{index}",
        "category": "boundary",
        "origins": frozenset({"session"}),
        "facts": make_facts(),
        "target_rule_ids": ("rule-meal",),
        "target_invariant_ids": (),
        "assertions": (make_assertion(),),
        "protected": False,
        "partition": "visible",
    }
    return Scenario(**(values | changes))


def make_scenario_candidate(**changes):
    values = {
        "candidate_id": "candidate-1",
        "category": "adversarial",
        "origins": frozenset({"llm_exploratory"}),
        "facts": make_facts(),
        "target_rule_ids": (),
        "target_invariant_ids": (),
        "assertions": (),
        "protected": False,
        "partition": "visible",
    }
    return ScenarioCandidate(**(values | changes))


def make_scenario_suite(scenarios=None, **changes):
    values = {
        "suite_id": "suite-1",
        "content_sha256": HASH,
        "seed": 42,
        "document_sha256": HASH,
        "policy_contract_sha256": HASH,
        "rule_set_sha256": HASH,
        "engine_version": "1.0",
        "scenarios": scenarios if scenarios is not None else (make_scenario(),),
    }
    return ScenarioSuite(**(values | changes))


def make_inputs(**changes):
    from app.domain.models import InputHashes

    values = {
        "policy_sha256": HASH,
        "contract_sha256": HASH,
        "suite_sha256": HASH,
        "engine_sha256": HASH,
        "run_manifest_sha256": HASH,
    }
    return InputHashes(**(values | changes))


def make_trace(**changes):
    from app.domain.models import DimensionResult, EvaluationTrace

    values = {
        "scenario_id": "scenario-0",
        "fired_rule_ids": ("rule-meal",),
        "predicate_results": (),
        "resolved_effects": (
            DimensionResult(dimension="claim_cap_minor", status="VALUE", value=5000),
        ),
        "compliance_values": (),
        "source_citations": (make_rule().provenance,),
        "trace_sha256": HASH,
    }
    return EvaluationTrace(**(values | changes))
