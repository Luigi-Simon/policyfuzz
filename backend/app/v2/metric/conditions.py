"""Conservative prose compiler and executable, clause-local boundary probes.

This does not model benefit administration. It tests the interpreted comparisons,
not an independent implementation, and always retains an unscored whole-policy
case. Unsupported syntax, scope, exceptions and formulas are never guessed.
"""

import hashlib
import operator
import re
from decimal import Decimal

from app.core.hashing import canonical_sha256
from app.v2.metric_contracts import (
    AssertionResult,
    ConditionTraceStep,
    EvaluateConditionAction,
    MetricCaseResult,
    MetricReview,
    MetricRunResult,
    MetricState,
    NumericCondition,
    PolicyClause,
    PolicyConditions,
    PolicyGoal,
    UnsupportedAction,
)

from .employment import LABELS, LIMITATIONS, compile_employment

_FIELDS = {
    "age_years": (r"age(?:d)?", "Age in completed years", 1),
    "assessable_income_cents": (
        r"(?:annual\s+)?assessable\s+income(?:\s*\(AI\))?(?:\s+for the Year of Assessment)?",
        "Assessable income in cents",
        100,
    ),
    "annual_income_cents": (r"annual\s+income", "Annual income in cents", 100),
    "monthly_income_cents": (r"monthly\s+income", "Monthly income in cents", 100),
    "annual_value_cents": (
        r"(?:home\s+)?annual\s+value",
        "Home annual value in cents",
        100,
    ),
    "property_count": (
        r"(?:property\s+count|number\s+of\s+properties)",
        "Number of properties",
        1,
    ),
}
_OPS = {
    "ge": r">=|≥|at least|no less than",
    "gt": r">|above|over|more than|greater than",
    "le": r"<=|≤|at most|no more than|not exceed(?:ing)?|up to",
    "lt": r"<|below|under|less than",
    "eq": r"=|exactly|equal to",
}
_NUMBER = r"(?:[0-9]{1,3}(?:,[0-9]{3})+|[0-9]+)(?:\.[0-9]{1,2})?"
_END = r"(?![\d,]|\.\d|[a-zA-Z])"
_OPERATIONS = {
    "ge": operator.ge,
    "gt": operator.gt,
    "le": operator.le,
    "lt": operator.lt,
    "eq": operator.eq,
}
_BOUNDARY_ORACLE = {
    "ge": (False, True, True),
    "gt": (False, False, True),
    "le": (True, True, False),
    "lt": (True, False, False),
    "eq": (False, True, False),
}
_LIMITATIONS = (
    "These are clause-local boundary checks of an interpreted model, not independent verification of policy correctness or a deployed benefit system.",
    "Only explicit age, income, home annual value and property-count comparisons in supported English syntax are executable. Citizenship, residence, exclusions, voucher uses and other prose remain unscored.",
    "Conditions are tested separately. Their applicability to individual benefits, combined eligibility, payout tiers, proration, timing and exceptions are not inferred.",
    "Dollar amounts use integer cents; no currency conversion or real-world eligibility decision is performed.",
)
_COVERAGE_REASON = (
    "Combined eligibility and payout outcomes remain unscored. The compiler has no verified component scope, tier formula, proration rule or benefit-system implementation. "
    "Review the actual source for these rules; an unsupported interpretation does not establish that the policy omits them."
)
_ASSUMPTIONS = (
    "Numeric comparisons are clause-local; no implicit AND/OR relationship or jurisdiction is assumed.",
)


def compile_conditions(text):
    """Return only explicit comparisons, with exact source offsets and hashes."""
    # These are data, never executable instructions. Such documents also fall
    # outside this deliberately small policy grammar.
    if re.search(
        r"\b(ignore|disregard|instructions?|system prompt)\b", text, re.IGNORECASE
    ):
        return ()
    conditions = []
    for segment in re.finditer(r".+?(?:[.!?](?=\s|$)|\n|$)", text, re.DOTALL):
        sentence = segment.group()
        safe = re.sub(
            r"not exceed(?:ing)?|no (?:more|less) than|(?:and|or) (?:above|older|over)",
            "",
            sentence,
            flags=re.IGNORECASE,
        )
        if re.search(
            r"\b(not|no|may|might|unless|except|example|if|either|or|excluding|exempt)\b",
            safe,
            re.IGNORECASE,
        ):
            continue
        matches = []
        for field, (name, _, scale) in _FIELDS.items():
            for op, expression in _OPS.items():
                pattern = rf"\b(?:{name})\s*(?:(?:must\s+be|must|is|of)\s+)?(?:{expression})\s*(?:SGD\s*)?\$?\s*(?P<n>{_NUMBER}){_END}"
                for match in re.finditer(pattern, sentence, re.IGNORECASE):
                    matches.append((match, field, op, scale))
            if field == "age_years":
                for match in re.finditer(
                    rf"\bage(?:d)?\s+(?P<n>{_NUMBER})(?:\s*(?:years?\s*)?(?:and|or)\s+(?:above|older|over)|\+)(?!\w)",
                    sentence,
                    re.IGNORECASE,
                ):
                    matches.append((match, field, "ge", scale))
        for match, field, op, scale in sorted(matches, key=lambda row: row[0].start()):
            tail = sentence[match.end() :]
            unit = (
                r"(?:years?(?:\s+old)?)?"
                if field == "age_years"
                else r"(?:dollars?|SGD)?"
                if scale == 100
                else ""
            )
            if not re.match(
                rf"\s*{unit}\s*(?:[.,;:]|$|\b(?:and|with)\b)", tail, re.IGNORECASE
            ):
                continue
            value = Decimal(match["n"].replace(",", "")) * scale
            if value != value.to_integral_value() or not 0 <= value <= 100_000_000:
                continue
            if scale == 1 and (
                "." in match["n"]
                or "$" in match.group()
                or "SGD" in match.group().upper()
            ):
                continue
            start, end = segment.start() + match.start(), segment.start() + match.end()
            conditions.append(
                NumericCondition(
                    id=f"R{len(conditions) + 1}",
                    clause_id=f"C-R{len(conditions) + 1}",
                    field=field,
                    operator=op,
                    threshold=int(value),
                    source_start=start,
                    source_end=end,
                    source_sha256=hashlib.sha256(text[start:end].encode()).hexdigest(),
                )
            )
            if len(conditions) == 12:
                return tuple(conditions)
    conditions.extend(compile_employment(text, _NUMBER, _END, _OPS))
    conditions.sort(key=lambda c: c.source_start)
    return tuple(
        c.model_copy(update={"id": f"R{i}", "clause_id": f"C-R{i}"})
        for i, c in enumerate(conditions[:12], 1)
    )


def evaluate_condition(condition, value):
    """Pure comparison; source interpretation and model calls do not occur here."""
    return _OPERATIONS[condition.operator](value, condition.threshold)


def _boundary_case(condition):
    label = (
        LABELS[condition.field]
        if condition.field in LABELS
        else _FIELDS[condition.field][1]
    )
    actions, trace = [], []
    for index, value in enumerate(
        range(condition.threshold - 1, condition.threshold + 2)
    ):
        action = EvaluateConditionAction(condition_id=condition.id, value=value)
        matches = evaluate_condition(condition, value)
        state = canonical_sha256(MetricState())
        actions.append(action)
        trace.append(
            ConditionTraceStep(
                step_id=f"S{index + 1}",
                action_index=index,
                action=action,
                matches=matches,
                detail=f"{label}: {value}. Extracted condition matches: {matches}. This is not a whole-policy compliance decision.",
                before_state_sha256=state,
                after_state_sha256=state,
            )
        )
    expected = _BOUNDARY_ORACLE[condition.operator]
    passed = tuple(s.matches for s in trace) == expected
    return MetricCaseResult(
        case_id=f"condition-{condition.id}",
        title=f"{label}: threshold boundary",
        category="boundary",
        plausibility=f"Participants have {label.lower()} immediately below, at and above {condition.threshold}. Consider applicability and exceptions separately.",
        initial_state=MetricState(),
        actions=tuple(actions),
        trace=tuple(trace),
        assertions=(
            AssertionResult(
                requirement_id=f"G-{condition.id}",
                passed=passed,
                expected=f"The extracted {condition.operator} comparison has below/at/above outcomes {expected}.",
                actual=f"Interpreted-model outcomes: {tuple(s.matches for s in trace)}. No independent policy implementation was tested.",
                step_refs=tuple(s.step_id for s in trace),
            ),
        ),
        verdict="pass" if passed else "fail",
    )


def run_policy_conditions(policy, run_id, *, test_budget):
    conditions = compile_conditions(policy.description)
    if not conditions:
        return None
    employment = any(c.field in LABELS for c in conditions)
    limits = LIMITATIONS if employment else _LIMITATIONS
    if employment and any(c.field not in LABELS for c in conditions):
        limits += _LIMITATIONS
    rules = PolicyConditions(conditions=conditions)
    clauses = tuple(
        PolicyClause(
            id=c.clause_id,
            text=f"Extracted local condition: {LABELS[c.field] if c.field in LABELS else _FIELDS[c.field][1]} {c.operator} {c.threshold}. Applicability and exceptions are not established. Source characters {c.source_start}–{c.source_end} (end exclusive).",
        )
        for c in conditions
    )
    goals = tuple(
        PolicyGoal(
            id=f"G-{c.id}",
            text="Verify that the interpreted comparison respects its explicit threshold and inclusive or exclusive boundary. This tests model conformance only.",
            clause_ids=(c.clause_id,),
        )
        for c in conditions
    )
    policy_hash = hashlib.sha256(policy.description.encode()).hexdigest()
    review = MetricReview(
        policy_text_sha256=policy_hash,
        review_fingerprint=canonical_sha256(
            {
                "input": policy,
                "compiler": "conditions-v2",
                "rules": rules,
                "clauses": clauses,
                "goals": goals,
                "assumptions": _ASSUMPTIONS,
                "limitations": limits,
            }
        ),
        status="ready",
        rules=rules,
        clauses=clauses,
        goals=goals,
        assumptions=_ASSUMPTIONS,
        limitations=limits,
    )
    # Reserve a slot even at budget=1. A small budget must never erase the
    # missing policy-wide oracle or turn these probes into deployment approval.
    cases = tuple(_boundary_case(c) for c in conditions[: test_budget - 1]) + (
        MetricCaseResult(
            case_id="policy-combined-outcomes",
            title="Combined workplace outcomes and exceptions"
            if employment
            else "Combined eligibility and benefit outcomes",
            category="compound",
            plausibility="A participant encounters overlapping work arrangements, notice periods and operational exceptions. Review their combined treatment against the source policy."
            if employment
            else "An applicant has several eligibility characteristics and requests multiple policy benefits. Consider component eligibility, payout tiers and exceptional circumstances.",
            initial_state=MetricState(),
            actions=(
                UnsupportedAction(
                    action="review_workplace_outcomes"
                    if employment
                    else "determine_benefits"
                ),
            ),
            verdict="unscored",
            unscored_reason="Combined workplace outcomes, applicability and exceptions need a reviewed executable model and independent expected outcomes. Passing a duration comparison does not verify workplace compliance or establish that unsupported rules are absent."
            if employment
            else _COVERAGE_REASON,
        ),
    )
    if employment and len(cases) < test_budget:
        from .scenarios import plan_scenarios

        # Retain relevant exploratory questions alongside executable probes;
        # these questions carry neither traces nor invented expected outcomes.
        planning_review = MetricReview.model_validate(
            {
                **review.model_dump(),
                "status": "needs_clarification",
                "rules": None,
                "clauses": (),
                "goals": (),
            }
        )
        planned = plan_scenarios(
            policy, run_id, planning_review, test_budget=test_budget - len(cases)
        )
        cases += planned.cases
    passed, failed = (
        sum(c.verdict == "pass" for c in cases),
        sum(c.verdict == "fail" for c in cases),
    )
    return MetricRunResult(
        run_id=run_id,
        policy_text_sha256=policy_hash,
        review_fingerprint=review.review_fingerprint,
        generation_method="policy_conditions",
        status="partial",
        review=review,
        suite_sha256=canonical_sha256(
            {
                "compiler": "conditions-v2",
                "review": review.review_fingerprint,
                "rules": rules,
                "boundary_oracle": _BOUNDARY_ORACLE,
                "actions": [c.actions for c in cases],
            }
        ),
        cases=cases,
        passed=passed,
        failed=failed,
        unscored=sum(c.verdict == "unscored" for c in cases),
        pass_rate=passed / (passed + failed) if passed + failed else None,
        limitations=(
            *limits,
            f"Executed {passed + failed} of {len(conditions)} extracted comparisons; source coverage is incomplete.",
        ),
    )
