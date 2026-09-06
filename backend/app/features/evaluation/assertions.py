"""Assertions receive independent expectations and never invent an oracle."""

from app.domain.models import (
    Assertion,
    AssertionResult,
    ComplianceResult,
    DimensionResult,
)
from app.features.evaluation.predicates import _OPERATORS


def evaluate_assertion(
    assertion: Assertion,
    dimensions: tuple[DimensionResult, ...],
    compliance: tuple[ComplianceResult, ...] = (),
) -> AssertionResult:
    dimension = next(
        (d for d in dimensions if d.dimension == assertion.dimension), None
    )
    if dimension is None or dimension.status == "ERROR":
        return AssertionResult(assertion_id=assertion.assertion_id, status="ERROR")
    if dimension.status != "VALUE":
        return AssertionResult(
            assertion_id=assertion.assertion_id, status="INCONCLUSIVE"
        )
    actual = dimension.value
    if assertion.target_kind == "compliance_value":
        result = next(
            (c for c in compliance if c.dimension == assertion.dimension), None
        )
        if result is None or result.status == "ERROR":
            return AssertionResult(assertion_id=assertion.assertion_id, status="ERROR")
        if result.status not in ("COMPLIANT", "NONCOMPLIANT"):
            return AssertionResult(
                assertion_id=assertion.assertion_id, status="INCONCLUSIVE"
            )
        actual = result.status
    matched = _OPERATORS[assertion.operator](actual, assertion.expected_value)
    return AssertionResult(
        assertion_id=assertion.assertion_id,
        status="PASS" if matched else "FAIL",
        actual_value=actual,
    )
