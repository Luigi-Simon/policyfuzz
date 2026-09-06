"""Deterministic PolicyIR grader: ScenarioSuite → EvaluationReport."""

from __future__ import annotations

from typing import Any

from app.contracts.evaluation import EvaluationReport, Finding, TraceStep, Verdict
from app.contracts.policy import PolicyIR, Predicate, Rule
from app.contracts.scenario import ExpectedOutcome, Scenario, ScenarioSuite
from app.plugins.evaluator import Evaluator


class RuleEvaluator(Evaluator):
    """Walk each scenario against cited rules and emit pass/fail with traces."""

    def evaluate(self, ir: PolicyIR, suite: ScenarioSuite) -> EvaluationReport:
        findings = [_grade(ir, scenario) for scenario in suite.scenarios]
        by_verdict: dict[str, int] = {"pass": 0, "fail": 0, "ambiguous": 0, "error": 0}
        for finding in findings:
            by_verdict[finding.verdict] = by_verdict.get(finding.verdict, 0) + 1
        covered = {rule_id for finding in findings for rule_id in finding.rule_ids}
        return EvaluationReport(
            policy_id=ir.policy_id,
            policy_revision=ir.revision,
            suite_id=suite.suite_id,
            findings=findings,
            metrics={
                "scenario_count": len(suite.scenarios),
                "rule_count": len(ir.rules),
                "rules_covered": len(covered),
                "verdicts": by_verdict,
            },
        )


def _grade(ir: PolicyIR, scenario: Scenario) -> Finding:
    rule_map = ir.rule_map()
    targets = [rule_id for rule_id in scenario.targeted_rule_ids if rule_id in rule_map]
    if not targets:
        targets = [rule.id for rule in ir.rules]
    traces: list[TraceStep] = []
    actual = _infer_outcome(ir, scenario, targets, traces)
    verdict = _verdict(scenario.expected_outcome, actual)
    summary = (
        f"{scenario.title}: expected {scenario.expected_outcome or 'unspecified'}, "
        f"policy yielded {actual}."
    )
    return Finding(
        scenario_id=scenario.scenario_id,
        verdict=verdict,
        rule_ids=targets,
        summary=summary,
        traces=traces,
    )


def _infer_outcome(
    ir: PolicyIR,
    scenario: Scenario,
    targets: list[str],
    traces: list[TraceStep],
) -> ExpectedOutcome:
    rule_map = ir.rule_map()
    matched: list[Rule] = []
    excepted: list[Rule] = []
    for rule_id in targets:
        rule = rule_map[rule_id]
        when_ok = all(_matches(predicate, scenario.facts) for predicate in rule.when) if rule.when else True
        except_ok = any(_matches(predicate, scenario.facts) for predicate in rule.except_when)
        traces.append(
            TraceStep(
                rule_id=rule.id,
                matched=when_ok and not except_ok,
                detail=(
                    f"when={when_ok} except_when={except_ok} "
                    f"action={scenario.facts.get('action.name')} then={_modality(rule)}"
                ),
            )
        )
        if when_ok and except_ok:
            excepted.append(rule)
        elif when_ok:
            matched.append(rule)
    if excepted:
        return "exception"
    if not matched:
        if scenario.kind == "targeted" or any(rule_map[rid].ambiguity for rid in targets if rid in rule_map):
            return "ambiguous"
        return "ambiguous"
    for rule in matched:
        modality = _modality(rule)
        required = rule.then[0].action if rule.then else None
        actual_action = scenario.facts.get("action.name")
        if modality == "must_not" and (required is None or actual_action == required):
            return "violation"
        if modality == "must" and required and actual_action != required:
            return "violation"
    return "compliant"


def _verdict(expected: ExpectedOutcome | None, actual: ExpectedOutcome) -> Verdict:
    if expected is None:
        return "ambiguous" if actual == "ambiguous" else "pass"
    if actual == "ambiguous" and expected == "ambiguous":
        return "pass"
    if actual == expected:
        return "pass"
    if actual == "ambiguous":
        return "ambiguous"
    return "fail"


def _modality(rule: Rule) -> str:
    return rule.then[0].modality if rule.then else "must"


def _matches(predicate: Predicate, facts: dict[str, Any]) -> bool:
    left = facts.get(predicate.field)
    op = predicate.op
    right = predicate.value
    if op == "exists":
        return left is not None and left != ""
    if op == "eq":
        return left == right
    if op == "neq":
        return left != right
    if op == "in":
        options = list(right) if isinstance(right, (list, tuple)) else [right]
        return left in options
    if op == "not_in":
        options = list(right) if isinstance(right, (list, tuple)) else [right]
        return left not in options
    if op == "matches":
        return str(right) in str(left or "")
    try:
        left_n = float(left)
        if op == "gt":
            return left_n > float(right)
        if op == "gte":
            return left_n >= float(right)
        if op == "lt":
            return left_n < float(right)
        if op == "lte":
            return left_n <= float(right)
        if op == "between" and isinstance(right, (list, tuple)) and len(right) == 2:
            return float(right[0]) <= left_n <= float(right[1])
    except (TypeError, ValueError):
        return False
    return False
