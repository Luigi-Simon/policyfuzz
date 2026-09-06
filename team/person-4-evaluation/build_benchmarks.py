"""SYNTHETIC HACKATHON SAMPLE — NOT COMPANY POLICY.

Rebuild public benchmark labels from independently authored scenario expectations.
No private blind material is read and no evaluator result supplies gold answers.
Run: PYTHONPATH=backend backend/.venv/bin/python team/person-4-evaluation/build_benchmarks.py
"""

import json
from datetime import UTC, datetime
from pathlib import Path

from app.core.artifacts import semantic_payload_projection
from app.core.hashing import canonical_sha256
from app.domain.models import (
    AnalyzeFindingsRequest,
    Assertion,
    BenchmarkDefect,
    BenchmarkManifest,
    EvaluatePolicyRequest,
    InputHashes,
    PolicyContract,
    PolicyIR,
    Scenario,
    ScenarioFacts,
    ScenarioSuite,
    ScoreBenchmarkRequest,
)
from app.features.evaluation.benchmark import score_benchmark
from app.features.evaluation.engine import (
    DeterministicEvaluationEngine,
    matched_invariants,
    payload_hash,
)
from app.features.evaluation.findings import DeterministicFindingAnalyzer
from app.features.evaluation.signatures import semantic_rule_signature

BANNER = "SYNTHETIC HACKATHON SAMPLE — NOT COMPANY POLICY"
ROOT = Path(__file__).resolve().parents[2]
# ID, category, amount, destination, booking days, receipt, prior spend, partition.
CASES = (
    ("receipt-below", "meal", 4999, "domestic", 20, False, 0, "visible"),
    ("receipt-exact", "transport", 5000, "domestic", 20, True, 0, "visible"),
    ("receipt-above", "transport", 5001, "domestic", 20, True, 0, "visible"),
    ("split-meal", "meal", 6000, "domestic", 20, True, 5000, "visible"),
    ("meal-at-cap", "meal", 10000, "domestic", 20, True, 0, "visible"),
    ("meal-over-cap", "meal", 10001, "domestic", 20, True, 0, "visible"),
    (
        "hotel-international-below",
        "hotel",
        24999,
        "international",
        20,
        True,
        0,
        "visible",
    ),
    ("hotel-international-at", "hotel", 25000, "international", 20, True, 0, "visible"),
    ("hotel-domestic-below", "hotel", 24999, "domestic", 20, True, 0, "holdout"),
    ("transport-at-cap", "transport", 20000, "domestic", 20, True, 0, "holdout"),
    ("transport-over-cap", "transport", 20001, "domestic", 20, True, 0, "visible"),
    ("airfare-short", "airfare", 30000, "domestic", 13, True, 0, "visible"),
    ("airfare-boundary", "airfare", 30000, "domestic", 14, True, 0, "holdout"),
    ("incidental-unsupported", "incidental", 1000, "domestic", 20, False, 0, "visible"),
    ("hotel-domestic-over", "hotel", 25001, "domestic", 20, True, 0, "visible"),
)


# Independently authored source/intent labels. These definitions are the answer key;
# neither evaluation states nor measured Finding objects participate in their creation.
DEVELOPMENT_DEFECT_LABELS = (
    {
        "type": "structural_gap",
        "dimension": "receipt_requirement",
        "severity": "medium",
        "rule_citations": ("citation-receipt-below-50", "citation-receipt-threshold"),
        "source_citations": ("citation-receipt-below-50", "citation-receipt-threshold"),
        "witnesses": ("receipt-exact",),
    },
    {
        "type": "conflict",
        "dimension": "approval_requirement",
        "severity": "medium",
        "rule_citations": (
            "citation-hotel-below-250-no-approval",
            "citation-international-hotel-approval",
        ),
        "source_citations": (
            "citation-hotel-below-250-no-approval",
            "citation-international-hotel-approval",
        ),
        "witnesses": ("hotel-international-below",),
    },
    {
        "type": "intent_breach",
        "dimension": "daily_category_cap_minor",
        "severity": "high",
        "rule_citations": (),
        "source_citations": ("citation-meal-claim-cap",),
        "witnesses": ("meal-at-cap", "meal-over-cap", "receipt-below", "split-meal"),
    },
)


def authored_defects(
    name: str, policy: PolicyIR, contract: PolicyContract
) -> tuple[BenchmarkDefect, ...]:
    """Bind the fixed synthetic answer key to canonical source and confirmed-intent IDs."""
    if name == "corrected-control":
        return ()
    if name != "development":
        raise ValueError("only public development/control benchmarks are supported")
    by_citation = {r.provenance.citation_id: r for r in policy.rules}
    by_id = {r.rule_id: r for r in policy.rules}
    if len(by_citation) != len(policy.rules):
        raise ValueError("benchmark source citation identities must be unique")
    daily = tuple(
        i
        for i in contract.invariants
        if i.assertion.dimension == "daily_category_cap_minor"
        and i.assertion.target_kind == "effect_value"
        and i.assertion.operator == "lte"
        and i.assertion.expected_value == 10000
        and len(i.when) == 1
        and (i.when[0].field, i.when[0].operator, i.when[0].value)
        == ("expense_category", "eq", "meal")
    )
    if len(daily) != 1:
        raise ValueError(
            "benchmark requires the independently confirmed SGD 100 daily meal intent"
        )
    defects = []
    for label in DEVELOPMENT_DEFECT_LABELS:
        rule_ids = tuple(
            sorted(by_citation[c].rule_id for c in label["rule_citations"])
        )
        root = {"type": label["type"], "dimension": label["dimension"]}
        if label["type"] == "intent_breach":
            root["invariant_id"] = daily[0].invariant_id
            target_ids = (daily[0].invariant_id,)
        else:
            root["rule_ids"] = rule_ids
            target_ids = rule_ids
        # Canonical fingerprint preimage is authored here from the fixed root labels,
        # not requested from the measured analyzer or copied from its Finding objects.
        fingerprint = canonical_sha256(root)
        spans = tuple(
            sorted(
                (by_citation[c].provenance.span for c in label["source_citations"]),
                key=canonical_sha256,
            )
        )
        defects.append(
            BenchmarkDefect(
                defect_id=f"defect-{label['type']}",
                finding_type=label["type"],
                dimension=label["dimension"],
                target_ids=target_ids,
                severity=label["severity"],
                source_spans=spans,
                semantic_signature_sha256=canonical_sha256(
                    tuple(
                        semantic_rule_signature(by_id[rid], by_id) for rid in rule_ids
                    )
                ),
                permitted_witness_ids=label["witnesses"],
                expected_finding_fingerprint_sha256=fingerprint,
            )
        )
    return tuple(
        sorted(defects, key=lambda defect: defect.expected_finding_fingerprint_sha256)
    )


def authored_expectations(category, amount, destination, booking):
    values = {
        "receipt_requirement": "required" if amount >= 5000 else "not_required",
        "approval_requirement": "manager"
        if (category == "hotel" and destination == "international")
        or (category == "airfare" and booking < 14)
        else "none",
    }
    if category != "incidental":
        values["eligibility"] = "allow"
    if category in ("meal", "hotel", "transport"):
        values["claim_cap_minor"] = {"meal": 10000, "hotel": 25000, "transport": 20000}[
            category
        ]
    if category == "meal":
        values["daily_category_cap_minor"] = 10000
    return values


def write_json(path, value, first=None):
    data = value.model_dump(mode="json") if hasattr(value, "model_dump") else value
    if first:
        data = {
            first: data[first],
            **{key: data[key] for key in sorted(data) if key != first},
        }
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n")


def build(name):
    directory = ROOT / "samples" / "benchmarks" / name
    policy = PolicyIR.model_validate_json(
        (directory / "canonical-policy-ir.json").read_text()
    )
    contract = PolicyContract.model_validate_json(
        (directory / "confirmed-contract.json").read_text()
    )
    scenarios = []
    for sid, category, amount, destination, booking, receipt, prior, partition in CASES:
        values = authored_expectations(category, amount, destination, booking)
        facts = ScenarioFacts(
            employee_role="employee",
            expense_category=category,
            amount_minor=amount,
            destination_type=destination,
            booking_days_before=booking,
            receipt_present=receipt,
            approval_roles_present=frozenset({"manager"}),
            prior_same_day_category_spend_minor=prior,
        )
        assertions = tuple(
            Assertion(
                assertion_id=f"gold-{sid}-{dimension}",
                target_kind="effect_value",
                dimension=dimension,
                operator="eq",
                expected_value=value,
                origin="gold",
                gold_label_id=f"label-{sid}-{dimension}",
            )
            for dimension, value in sorted(values.items())
        )
        confirmed = tuple(i.assertion for i in matched_invariants(contract, facts))
        scenarios.append(
            Scenario(
                scenario_id=sid,
                category="adversarial" if sid == "split-meal" else "boundary",
                origins=frozenset({"gold", "session"})
                if confirmed
                else frozenset({"gold"}),
                facts=facts,
                assertions=assertions + confirmed,
                protected=partition == "holdout",
                partition=partition,
            )
        )
    suite = ScenarioSuite(
        suite_id=f"{BANNER}: {name}",
        content_sha256="0" * 64,
        seed=42,
        document_sha256=policy.document_sha256,
        policy_contract_sha256=payload_hash(contract),
        rule_set_sha256=canonical_sha256(semantic_payload_projection(policy)),
        engine_version="1.0.0",
        scenarios=tuple(scenarios),
    )
    suite = suite.model_copy(update={"content_sha256": payload_hash(suite)})
    inputs = InputHashes(
        policy_sha256=payload_hash(policy),
        contract_sha256=payload_hash(contract),
        suite_sha256=payload_hash(suite),
        engine_sha256=canonical_sha256(
            {"engine_version": "1.0.0", "purpose": "public benchmark labeling"}
        ),
        run_manifest_sha256=canonical_sha256({"benchmark": name, "seed": 42}),
    )
    defects = authored_defects(name, policy, contract)
    gold_scenarios = tuple(
        s.model_copy(
            update={
                "origins": frozenset({"gold"}),
                "assertions": tuple(a for a in s.assertions if a.origin == "gold"),
            }
        )
        for s in suite.scenarios
    )
    manifest = BenchmarkManifest(
        benchmark_id=f"{BANNER}: {name}",
        document_sha256=policy.document_sha256,
        policy_contract_sha256=payload_hash(contract),
        engine_version="1.0.0",
        sealed_at=datetime(2026, 9, 4, tzinfo=UTC),
        seal_sha256=canonical_sha256(
            {"defects": tuple(defects), "gold_scenarios": gold_scenarios}
        ),
        defects=tuple(defects),
        gold_scenarios=gold_scenarios,
        required_dimensions=contract.required_dimensions,
    )
    # Evaluate only after the independent, immutable manifest is fully constructed.
    evaluation = DeterministicEvaluationEngine().evaluate(
        EvaluatePolicyRequest(
            policy=policy,
            contract=contract,
            suite=suite,
            inputs=inputs,
            engine_version="1.0.0",
        )
    )
    findings = DeterministicFindingAnalyzer().analyze(
        AnalyzeFindingsRequest(
            policy=policy, contract=contract, suite=suite, evaluation=evaluation
        )
    )
    score = score_benchmark(
        ScoreBenchmarkRequest(
            manifest=manifest, findings=findings, evaluation=evaluation
        )
    )
    if (
        score.true_positives != len(defects)
        or score.false_positives
        or score.false_negatives
    ):
        raise ValueError(
            "measured benchmark findings differ from independently authored defect labels"
        )
    write_json(directory / "frozen-suite.json", suite, "suite_id")
    write_json(directory / "defect-manifest.json", manifest, "benchmark_id")
    # Frozen archive contract: this file records expected deterministic baseline execution.
    # Independently authored intended values remain in the suite gold assertions.
    write_json(directory / "expected-effects.json", evaluation)
    print(
        json.dumps(
            {
                "benchmark": name,
                "suite_sha256": payload_hash(suite),
                "findings": score.true_positives,
                "coverage": evaluation.coverage.status,
            }
        )
    )


if __name__ == "__main__":
    for benchmark in ("development", "corrected-control"):
        build(benchmark)
