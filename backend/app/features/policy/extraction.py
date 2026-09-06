"""Deterministic validation of typed policy-extraction candidates."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass

from app.domain.models import (
    PolicyDocument,
    PolicyExtraction,
    RuleDraft,
    SourceSpan,
    TextRuleProvenance,
    UnsupportedClause,
)
from app.features.policy.citations import (
    CitationValidationError,
    validate_source_span,
)
from app.features.policy.model_output import parse_typed_output


MAX_BASELINE_RULES = 12


class ExtractionValidationError(ValueError):
    """A sanitized extraction failure safe to expose to a caller."""

    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(code)


@dataclass(frozen=True, slots=True)
class ValidatedPolicyExtraction:
    """Validated extraction plus the deterministic exclusion count."""

    extraction: PolicyExtraction
    excluded_rule_count: int


def _line_span(document: PolicyDocument, proposed: SourceSpan) -> SourceSpan:
    """Derive a verified nonempty line without trusting proposed quote text."""

    page = next((item for item in document.pages if item.page == proposed.page), None)
    if page is None:
        page = document.pages[0]
    if not page.text:
        raise ExtractionValidationError("NO_CITABLE_POLICY_TEXT")

    local_anchor = proposed.start - page.start
    if not 0 <= local_anchor < len(page.text):
        local_anchor = 0
    line_start = page.text.rfind("\n", 0, local_anchor + 1) + 1
    line_end = page.text.find("\n", local_anchor)
    if line_end == -1:
        line_end = len(page.text)

    if line_end == line_start:
        for candidate in page.text.splitlines(keepends=True):
            content = candidate.rstrip("\r\n")
            if content:
                line_start = page.text.index(candidate)
                line_end = line_start + len(content)
                break
    quote = page.text[line_start:line_end]
    if not quote:
        raise ExtractionValidationError("NO_CITABLE_POLICY_TEXT")
    return SourceSpan(
        page=page.page,
        start=page.start + line_start,
        end=page.start + line_end,
        quote=quote,
        quote_sha256=hashlib.sha256(quote.encode("utf-8")).hexdigest(),
        section=proposed.section,
    )


def _invalid_citation_clause(
    document: PolicyDocument,
    rule: RuleDraft,
    *,
    index: int,
    existing_ids: set[str],
) -> UnsupportedClause:
    provenance = rule.provenance
    if not isinstance(provenance, TextRuleProvenance):
        raise ExtractionValidationError("INVALID_RULE_PROVENANCE")
    clause_id = f"invalid-citation-{index + 1}"
    suffix = 2
    while clause_id in existing_ids:
        clause_id = f"invalid-citation-{index + 1}-{suffix}"
        suffix += 1
    existing_ids.add(clause_id)
    return UnsupportedClause(
        clause_id=clause_id,
        span=_line_span(document, provenance.span),
        reason_code="invalid_citation",
        affected_dimensions=frozenset(effect.dimension for effect in rule.effects),
        when_hint=rule.when or None,
        review_status="provisional",
    )


def validate_policy_extraction(
    document: PolicyDocument,
    extraction: PolicyExtraction,
    *,
    max_rules: int = MAX_BASELINE_RULES,
) -> ValidatedPolicyExtraction:
    """Validate citations, preserve unsupported prose, and bound rule count.

    Invalid cited rules are excluded individually and retained as unsupported
    clauses anchored to source text derived by Python. Existing unsupported
    clauses must already carry valid exact citations.
    """

    if (
        not isinstance(max_rules, int)
        or isinstance(max_rules, bool)
        or not 1 <= max_rules <= 12
    ):
        raise ValueError("max_rules must be an integer from 1 to 12")
    if extraction.document_sha256 != document.document_sha256:
        raise ExtractionValidationError("DOCUMENT_HASH_MISMATCH")

    for clause in extraction.unsupported_clauses:
        try:
            validate_source_span(document, clause.span)
        except CitationValidationError as exc:
            raise ExtractionValidationError("INVALID_UNSUPPORTED_CITATION") from exc

    accepted: list[RuleDraft] = []
    unsupported = list(extraction.unsupported_clauses)
    existing_ids = {clause.clause_id for clause in unsupported}
    excluded = 0
    for index, rule in enumerate(extraction.rules):
        if not isinstance(rule.provenance, TextRuleProvenance):
            raise ExtractionValidationError("INVALID_RULE_PROVENANCE")
        try:
            validate_source_span(document, rule.provenance.span)
        except CitationValidationError:
            unsupported.append(
                _invalid_citation_clause(
                    document,
                    rule,
                    index=index,
                    existing_ids=existing_ids,
                )
            )
            excluded += 1
            continue
        if len(accepted) == max_rules:
            excluded += 1
            continue
        accepted.append(rule)

    validated = PolicyExtraction(
        document_sha256=document.document_sha256,
        rules=tuple(accepted),
        unsupported_clauses=tuple(unsupported),
    )
    return ValidatedPolicyExtraction(
        extraction=validated,
        excluded_rule_count=excluded,
    )


def parse_and_validate_policy_extraction(
    document: PolicyDocument,
    raw_output: str,
) -> ValidatedPolicyExtraction:
    """Strictly parse a raw proposal, then apply deterministic provenance checks."""

    extraction = parse_typed_output(
        raw_output,
        response_model=PolicyExtraction,
    )
    return validate_policy_extraction(document, extraction)
