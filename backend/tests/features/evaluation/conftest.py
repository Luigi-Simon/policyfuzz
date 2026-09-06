import pytest

from app.core.artifacts import complete_payload_projection, semantic_payload_projection
from app.core.hashing import canonical_sha256
from app.domain.models import (
    Assertion,
    Effect,
    EvaluatePolicyRequest,
    InputHashes,
    Invariant,
    PolicyContract,
    PolicyIR,
    Predicate,
    Rule,
    Scenario,
    ScenarioFacts,
    ScenarioSuite,
    SourceSpan,
    TextRuleProvenance,
)


@pytest.fixture
def facts():
    return ScenarioFacts(
        employee_role="employee",
        expense_category="meal",
        amount_minor=5000,
        destination_type="domestic",
        booking_days_before=20,
        receipt_present=False,
        approval_roles_present=frozenset(),
        prior_same_day_category_spend_minor=0,
    )


@pytest.fixture
def rule_factory():
    def make(
        rule_id="r1", dimension="eligibility", value="allow", when=(), overrides=()
    ):
        return Rule(
            rule_id=rule_id,
            revision=1,
            description="Synthetic rule",
            when=when,
            effects=(Effect(dimension=dimension, value=value),),
            overrides=overrides,
            provenance=TextRuleProvenance(
                citation_id=f"cite-{rule_id}",
                span=SourceSpan(
                    page=1, start=0, end=9, quote="Synthetic", quote_sha256="a" * 64
                ),
            ),
        )

    return make


@pytest.fixture
def policy_factory(rule_factory):
    def make(rules=None, unsupported_clauses=()):
        return PolicyIR(
            policy_id="p1",
            document_sha256="b" * 64,
            review_status="session_confirmed",
            rules=tuple(rules or [rule_factory()]),
            unsupported_clauses=unsupported_clauses,
        )

    return make


@pytest.fixture
def contract():
    return PolicyContract(
        contract_id="c1",
        required_dimensions=frozenset({"eligibility"}),
        invariants=tuple(
            Invariant(
                invariant_id=f"i{i}",
                description="Synthetic intent",
                severity="high",
                when=(
                    Predicate(field="expense_category", operator="eq", value=category),
                ),
                assertion=Assertion(
                    assertion_id=f"ia{i}",
                    target_kind="effect_value",
                    dimension="eligibility",
                    operator="eq",
                    expected_value="allow",
                    origin="session_confirmed",
                    source_invariant_id=f"i{i}",
                ),
            )
            for i, category in enumerate(("meal", "hotel", "transport"))
        ),
    )


@pytest.fixture
def scenario_factory(facts):
    def make(scenario_id="s1", **kwargs):
        return Scenario(
            scenario_id=scenario_id,
            category="normal",
            origins=frozenset({"session"}),
            facts=kwargs.pop("facts", facts),
            **kwargs,
        )

    return make


@pytest.fixture
def request_factory(policy_factory, contract, scenario_factory):
    def make(policy=None, scenarios=None):
        policy = policy or policy_factory()
        suite = ScenarioSuite(
            suite_id="suite",
            content_sha256="0" * 64,
            seed=1,
            document_sha256=policy.document_sha256,
            policy_contract_sha256=canonical_sha256(
                complete_payload_projection(contract)
            ),
            rule_set_sha256=canonical_sha256(semantic_payload_projection(policy)),
            engine_version="1.0.0",
            scenarios=tuple(scenarios or [scenario_factory()]),
        )
        suite = suite.model_copy(
            update={
                "content_sha256": canonical_sha256(complete_payload_projection(suite))
            }
        )
        return EvaluatePolicyRequest(
            policy=policy,
            contract=contract,
            suite=suite,
            engine_version="1.0.0",
            inputs=InputHashes(
                policy_sha256=canonical_sha256(complete_payload_projection(policy)),
                contract_sha256=suite.policy_contract_sha256,
                suite_sha256=suite.content_sha256,
                engine_sha256="c" * 64,
                run_manifest_sha256="d" * 64,
            ),
        )

    return make
