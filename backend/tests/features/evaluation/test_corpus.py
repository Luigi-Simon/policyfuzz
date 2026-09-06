import json
from pathlib import Path

from app.domain.models import (
    AnalyzeFindingsRequest,
    EvaluatePolicyRequest,
    InputHashes,
    PolicyContract,
    PolicyIR,
    ScenarioSuite,
)
from app.features.evaluation.engine import DeterministicEvaluationEngine, payload_hash
from app.features.evaluation.findings import DeterministicFindingAnalyzer

ROOT = Path(__file__).resolve().parents[4]


def test_development_three_seeded_roots_and_control():
    for name in ("development", "corrected-control"):
        directory = ROOT / "samples" / "benchmarks" / name
        policy = PolicyIR.model_validate_json(
            (directory / "canonical-policy-ir.json").read_text()
        )
        contract = PolicyContract.model_validate_json(
            (directory / "confirmed-contract.json").read_text()
        )
        suite = ScenarioSuite.model_validate_json(
            (directory / "frozen-suite.json").read_text()
        )
        assert len(suite.scenarios) == 15
        assert suite.content_sha256 == payload_hash(suite)
        inputs = InputHashes(
            policy_sha256=payload_hash(policy),
            contract_sha256=payload_hash(contract),
            suite_sha256=payload_hash(suite),
            engine_sha256="a" * 64,
            run_manifest_sha256="b" * 64,
        )
        report = DeterministicEvaluationEngine().evaluate(
            EvaluatePolicyRequest(
                policy=policy,
                contract=contract,
                suite=suite,
                inputs=inputs,
                engine_version=suite.engine_version,
            )
        )
        findings = DeterministicFindingAnalyzer().analyze(
            AnalyzeFindingsRequest(
                policy=policy, contract=contract, suite=suite, evaluation=report
            )
        )
        scored = [f for f in findings.findings if f.evidence_level != "candidate"]
        if name == "development":
            assert {f.finding_type for f in scored} == {
                "structural_gap",
                "conflict",
                "intent_breach",
            }
            assert len(scored) == 3
        else:
            assert scored == []
        assert report.coverage.status == "satisfied"
        expected = json.loads((directory / "expected-effects.json").read_text())
        from app.domain.models import EvaluationReport

        expected_report = EvaluationReport.model_validate_json(json.dumps(expected))
        assert expected_report.results == report.results
        assert expected_report.coverage == report.coverage


def test_three_operation_development_repair_is_accepted():
    from datetime import UTC, datetime

    from app.core.artifacts import semantic_payload_projection
    from app.core.hashing import canonical_sha256
    from app.domain.models import (
        AddRuleOperation,
        ApplyRevisionRequest,
        BenchmarkCorrectedSemantics,
        CompareRevisionRequest,
        ReplaceRuleOperation,
        RevisionProposal,
    )
    from app.features.evaluation.patches import DeterministicRevisionApplier
    from app.features.evaluation.regression import DeterministicRegressionAnalyzer

    directory = ROOT / "samples" / "benchmarks" / "development"
    policy = PolicyIR.model_validate_json(
        (directory / "canonical-policy-ir.json").read_text()
    )
    contract = PolicyContract.model_validate_json(
        (directory / "confirmed-contract.json").read_text()
    )
    suite = ScenarioSuite.model_validate_json(
        (directory / "frozen-suite.json").read_text()
    )
    semantics = BenchmarkCorrectedSemantics.model_validate_json(
        (directory / "corrected-semantics.json").read_text()
    )
    inputs = InputHashes(
        policy_sha256=payload_hash(policy),
        contract_sha256=payload_hash(contract),
        suite_sha256=payload_hash(suite),
        engine_sha256="a" * 64,
        run_manifest_sha256="b" * 64,
    )

    def evaluate(p):
        return DeterministicEvaluationEngine().evaluate(
            EvaluatePolicyRequest(
                policy=p,
                contract=contract,
                suite=suite,
                inputs=inputs.model_copy(update={"policy_sha256": payload_hash(p)}),
                engine_version="1.0.0",
            )
        )

    def analyze(p, report):
        return DeterministicFindingAnalyzer().analyze(
            AnalyzeFindingsRequest(
                policy=p, contract=contract, suite=suite, evaluation=report
            )
        )

    before = evaluate(policy)
    findings = analyze(policy, before)
    targets = {
        f.dimension: f.finding_id
        for f in findings.findings
        if f.evidence_level != "candidate"
    }
    rules = {r.rule_id: r for r in policy.rules}
    operations = []
    for expected in semantics.rules:
        rule = rules.get(expected.rule_id)
        fields = ("when", "effects", "overrides")
        if rule is not None and all(
            getattr(rule, key) == getattr(expected.rule, key) for key in fields
        ):
            continue
        dimension = next(e.dimension for e in expected.rule.effects)
        shared = {
            "rule_id": expected.rule_id,
            "rule": expected.rule,
            "finding_ids": (targets[dimension],),
        }
        operations.append(
            ReplaceRuleOperation(**shared, expected_revision=rule.revision)
            if rule
            else AddRuleOperation(**shared)
        )
    assert len(operations) == 3
    proposal = RevisionProposal(
        proposal_id="three-defect-repair",
        document_sha256=policy.document_sha256,
        rule_set_sha256=canonical_sha256(semantic_payload_projection(policy)),
        policy_contract_sha256=payload_hash(contract),
        suite_sha256=payload_hash(suite),
        accepted_finding_ids=tuple(sorted(targets.values())),
        operations=tuple(operations),
        draft_policy_wording="Synthetic structured correction.",
    )
    applied = DeterministicRevisionApplier().apply_revision(
        ApplyRevisionRequest(
            policy=policy,
            contract=contract,
            suite=suite,
            proposal=proposal,
            confirmed_at=datetime(2026, 9, 4, tzinfo=UTC),
        )
    )
    assert applied.applied, applied.error
    after = evaluate(applied.revised_policy)
    comparison = DeterministicRegressionAnalyzer().compare(
        CompareRevisionRequest(
            baseline_policy=policy,
            revised_policy=applied.revised_policy,
            contract=contract,
            suite=suite,
            proposal=proposal,
            baseline_evaluation=before,
            revised_evaluation=after,
            baseline_findings=findings,
            revised_findings=analyze(applied.revised_policy, after),
        )
    )
    assert comparison.acceptance.patch_accepted, comparison.acceptance
