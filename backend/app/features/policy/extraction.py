"""Deterministic validation of typed policy-extraction candidates."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass

from app.core.hashing import canonical_sha256
from app.domain.models import (
    CompilePolicyRequest,
    Effect,
    LLMRequest,
    OverrideRef,
    PolicyDocument,
    PolicyExtraction,
    Predicate,
    Rule,
    RuleDraft,
    SourceSpan,
    TextRuleProvenance,
    UnsupportedClause,
)
from app.domain.protocols import LLMClient
from app.features.policy.citations import (
    CitationValidationError,
    canonical_source_span,
)
from app.features.policy.model_io import ModelPolicyExtraction
from app.features.policy.model_output import complete_typed, parse_typed_output
from app.features.policy.prompts import build_policy_extraction_prompt

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


def _canonical_predicate(predicate: Predicate) -> Predicate:
    value = predicate.value
    if predicate.operator in ("in", "not_in") and isinstance(value, tuple):
        value = tuple(sorted(set(value)))
    return predicate.model_copy(update={"value": value})


def canonical_predicates(predicates: tuple[Predicate, ...]) -> tuple[Predicate, ...]:
    """Canonicalize AND conditions and membership sets for semantic identity."""

    normalized = (_canonical_predicate(item) for item in predicates)
    return tuple(sorted(normalized, key=canonical_sha256))


def _canonical_effects(effects: tuple[Effect, ...]) -> tuple[Effect, ...]:
    return tuple(sorted(effects, key=canonical_sha256))


def _verified_source_projection(span: SourceSpan) -> dict[str, object]:
    return {
        "page": span.page,
        "start": span.start,
        "end": span.end,
        "quote_sha256": span.quote_sha256,
    }


def _base_rule_signature(draft: RuleDraft) -> dict[str, object]:
    provenance = draft.provenance
    if not isinstance(provenance, TextRuleProvenance):
        raise ExtractionValidationError("INVALID_RULE_PROVENANCE")
    return {
        "when": canonical_predicates(draft.when),
        "effects": _canonical_effects(draft.effects),
        "source": _verified_source_projection(provenance.span),
    }


def _legacy_rule_id(draft: RuleDraft) -> str:
    provenance = draft.provenance
    if not isinstance(provenance, TextRuleProvenance):
        raise ExtractionValidationError("INVALID_RULE_PROVENANCE")
    return "rule-" + canonical_sha256(
        {
            "when": draft.when,
            "effects": draft.effects,
            "overrides": draft.overrides,
            "source_span_sha256": canonical_sha256(provenance.span),
        }
    )


def _base_reference(draft: RuleDraft) -> str:
    return "local-" + canonical_sha256(_base_rule_signature(draft))


def _rule_aliases(
    drafts: tuple[RuleDraft, ...],
    *,
    local_handles: tuple[str | None, ...] | None = None,
) -> dict[str, set[int]]:
    aliases: dict[str, set[int]] = {}

    def add(value: str | None, index: int) -> None:
        if value is not None:
            aliases.setdefault(value, set()).add(index)

    for index, draft in enumerate(drafts):
        provenance = draft.provenance
        if not isinstance(provenance, TextRuleProvenance):
            raise ExtractionValidationError("INVALID_RULE_PROVENANCE")
        add(provenance.citation_id, index)
        add(_legacy_rule_id(draft), index)
        add(_base_reference(draft), index)
        if not draft.overrides:
            add(
                "rule-"
                + canonical_sha256(
                    {
                        "rule": _base_rule_signature(draft),
                        "overrides": (),
                    }
                ),
                index,
            )
        if local_handles is not None:
            add(local_handles[index], index)
    return aliases


def _resolve_rule_references(
    drafts: tuple[RuleDraft, ...],
    *,
    local_handles: tuple[str | None, ...] | None = None,
) -> tuple[tuple[int, ...], ...]:
    aliases = _rule_aliases(drafts, local_handles=local_handles)
    graph: list[tuple[int, ...]] = []
    for source_index, draft in enumerate(drafts):
        targets: list[int] = []
        source_dimensions = {effect.dimension for effect in draft.effects}
        for edge in draft.overrides:
            matches = aliases.get(edge.target_rule_id, set())
            if not matches:
                raise ExtractionValidationError("UNKNOWN_OVERRIDE_REFERENCE") from None
            if len(matches) != 1:
                raise ExtractionValidationError(
                    "AMBIGUOUS_OVERRIDE_REFERENCE"
                ) from None
            target_index = next(iter(matches))
            target_dimensions = {
                effect.dimension for effect in drafts[target_index].effects
            }
            if (
                edge.dimension not in source_dimensions
                or edge.dimension not in target_dimensions
            ):
                raise ExtractionValidationError("INVALID_OVERRIDE_DIMENSION") from None
            targets.append(target_index)
        graph.append(tuple(targets))

    visiting: set[int] = set()
    visited: set[int] = set()

    def visit(index: int) -> None:
        if index in visiting:
            raise ExtractionValidationError("CYCLIC_OVERRIDE_REFERENCE") from None
        if index in visited:
            return
        visiting.add(index)
        for target in graph[index]:
            visit(target)
        visiting.remove(index)
        visited.add(index)

    for index in range(len(drafts)):
        visit(index)
    return tuple(graph)


def _rewrite_override_references(
    drafts: tuple[RuleDraft, ...],
    *,
    local_handles: tuple[str | None, ...] | None = None,
) -> tuple[RuleDraft, ...]:
    graph = _resolve_rule_references(drafts, local_handles=local_handles)
    rewritten: list[RuleDraft] = []
    for draft, targets in zip(drafts, graph, strict=True):
        overrides = tuple(
            OverrideRef(
                dimension=edge.dimension,
                target_rule_id=_base_reference(drafts[target_index]),
            )
            for edge, target_index in zip(draft.overrides, targets, strict=True)
        )
        rewritten.append(draft.model_copy(update={"overrides": overrides}))
    return tuple(rewritten)


def _model_extraction_to_public(output: ModelPolicyExtraction) -> PolicyExtraction:
    drafts = tuple(
        RuleDraft.model_validate(rule.model_dump(exclude={"rule_handle"}))
        for rule in output.rules
    )
    rewritten = _rewrite_override_references(
        drafts,
        local_handles=tuple(rule.rule_handle for rule in output.rules),
    )
    return PolicyExtraction(
        document_sha256=output.document_sha256,
        rules=rewritten,
        unsupported_clauses=output.unsupported_clauses,
    )


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
        section=None,
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

    rewritten_rules = _rewrite_override_references(extraction.rules)

    provisional_clauses: list[UnsupportedClause] = []
    for clause in extraction.unsupported_clauses:
        try:
            verified_span = canonical_source_span(document, clause.span)
        except CitationValidationError as exc:
            raise ExtractionValidationError("INVALID_UNSUPPORTED_CITATION") from exc
        provisional_clauses.append(
            clause.model_copy(
                update={
                    "span": verified_span,
                    "review_status": "provisional",
                }
            )
        )

    accepted: list[RuleDraft] = []
    unsupported = list(provisional_clauses)
    existing_ids = {clause.clause_id for clause in unsupported}
    excluded = 0
    for index, rule in enumerate(rewritten_rules):
        if not isinstance(rule.provenance, TextRuleProvenance):
            raise ExtractionValidationError("INVALID_RULE_PROVENANCE")
        try:
            verified_span = canonical_source_span(document, rule.provenance.span)
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
        accepted.append(
            rule.model_copy(
                update={
                    "provenance": rule.provenance.model_copy(
                        update={"span": verified_span}
                    )
                }
            )
        )

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


async def extract_policy(
    llm: LLMClient,
    request: CompilePolicyRequest,
) -> PolicyExtraction:
    """Extract and deterministically validate cited policy candidates."""

    prompt = build_policy_extraction_prompt(request.document)
    llm_request = LLMRequest(
        operation="policy_extraction",
        system_instructions=prompt.system_instructions,
        untrusted_payload_json=prompt.policy_payload_json,
        response_schema=json.loads(prompt.response_schema_json),
        response_schema_name="PolicyExtraction",
    )
    extraction = await complete_typed(
        llm,
        request=llm_request,
        response_model=ModelPolicyExtraction,
        repair_operation="policy_extraction",
    )
    public_extraction = _model_extraction_to_public(extraction)
    return validate_policy_extraction(request.document, public_extraction).extraction


def assign_baseline_rule_ids(
    document: PolicyDocument,
    drafts: tuple[RuleDraft, ...],
) -> tuple[Rule, ...]:
    """Assign stable IDs from rule semantics and verified source provenance."""

    verified_drafts: list[RuleDraft] = []
    for draft in drafts:
        provenance = draft.provenance
        if not isinstance(provenance, TextRuleProvenance):
            raise ExtractionValidationError("INVALID_RULE_PROVENANCE")
        verified_span = canonical_source_span(document, provenance.span)
        verified_drafts.append(
            draft.model_copy(
                update={
                    "when": canonical_predicates(draft.when),
                    "effects": _canonical_effects(draft.effects),
                    "provenance": provenance.model_copy(update={"span": verified_span}),
                }
            )
        )
    normalized = _rewrite_override_references(tuple(verified_drafts))
    graph = _resolve_rule_references(normalized)
    base_signatures = tuple(_base_rule_signature(draft) for draft in normalized)
    base_hashes = tuple(canonical_sha256(item) for item in base_signatures)
    rule_ids = tuple(
        "rule-"
        + canonical_sha256(
            {
                "rule": base_signatures[index],
                "overrides": tuple(
                    sorted(
                        (
                            {
                                "dimension": edge.dimension,
                                "target_rule_sha256": base_hashes[target_index],
                            }
                            for edge, target_index in zip(
                                draft.overrides, graph[index], strict=True
                            )
                        ),
                        key=canonical_sha256,
                    )
                ),
            }
        )
        for index, draft in enumerate(normalized)
    )
    if len(set(rule_ids)) != len(rule_ids):
        raise ExtractionValidationError("DUPLICATE_RULE_ID")

    rules: list[Rule] = []
    assigned_ids: set[str] = set()
    for index, draft in enumerate(normalized):
        provenance = draft.provenance
        if not isinstance(provenance, TextRuleProvenance):
            raise ExtractionValidationError("INVALID_RULE_PROVENANCE")
        rule_id = rule_ids[index]
        if rule_id in assigned_ids:
            raise ExtractionValidationError("DUPLICATE_RULE_ID")
        assigned_ids.add(rule_id)
        overrides = tuple(
            sorted(
                (
                    OverrideRef(
                        dimension=edge.dimension,
                        target_rule_id=rule_ids[target_index],
                    )
                    for edge, target_index in zip(
                        draft.overrides, graph[index], strict=True
                    )
                ),
                key=canonical_sha256,
            )
        )
        rules.append(
            Rule(
                rule_id=rule_id,
                revision=0,
                description=draft.description,
                when=draft.when,
                effects=draft.effects,
                overrides=overrides,
                provenance=provenance,
                confidence_percent=draft.confidence_percent,
            )
        )
    return tuple(rules)
