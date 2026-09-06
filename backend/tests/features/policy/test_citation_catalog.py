import hashlib
import json
from pathlib import Path

import pytest

from app.core.fakes import ScriptedLLMClient
from app.domain.models import CompilePolicyRequest, LLMResponse
from app.features.policy import citations
from app.features.policy.compiler import compile_baseline_policy
from app.features.policy.extraction import ExtractionValidationError, extract_policy
from app.features.policy.ingest import ingest_policy_pages, ingest_policy_text
from app.features.policy.model_output import ModelOutputValidationError
from app.features.policy.prompts import build_policy_extraction_prompt


def _document(text="Meals or hotels require receipts.\nReasonable costs may qualify."):
    return ingest_policy_text(title="Synthetic", text=text, source_type="pasted_text")


def _payload(document):
    catalog = json.loads(build_policy_extraction_prompt(document).policy_payload_json)
    entries = catalog["citation_catalog"]
    return {
        "document_sha256": document.document_sha256,
        "rules": [
            {
                "rule_handle": f"rule_{category}",
                "citation_handle": entries[0]["citation_handle"],
                "description": f"{category} receipt",
                "when": [
                    {"field": "expense_category", "operator": "eq", "value": category}
                ],
                "effects": [{"dimension": "receipt_requirement", "value": "required"}],
                "overrides": [],
            }
            for category in ("meal", "hotel")
        ],
        "unsupported_clauses": [
            {
                "clause_id": "unsupported-1",
                "citation_handle": entries[-1]["citation_handle"],
                "reason_code": "ambiguous_language",
                "affected_dimensions": ["eligibility"],
                "when_hint": None,
            }
        ],
    }


def test_catalog_preserves_normalized_unicode_repeated_locations_and_page_offsets():
    document = ingest_policy_pages(
        title="Synthetic",
        pages=("Cafe\u0301.\r\nCafe\u0301.\r\n", "🙂 Rules.\nCafé."),
        source_type="pasted_text",
    )
    catalog = citations.build_citation_catalog(document)
    assert [
        (entry.span.page, entry.span.start, entry.span.end, entry.span.quote)
        for entry in catalog.entries
    ] == [
        (1, 0, 5, "Café."),
        (1, 6, 11, "Café."),
        (2, 13, 21, "🙂 Rules."),
        (2, 22, 27, "Café."),
    ]
    assert len({entry.citation_handle for entry in catalog.entries}) == 4
    for entry in catalog.entries:
        assert (
            entry.span.quote_sha256
            == hashlib.sha256(entry.span.quote.encode()).hexdigest()
        )
        assert catalog.resolve(entry.citation_handle) == entry.span
        citations.validate_source_span(document, entry.span)
    assert catalog == citations.build_citation_catalog(document)


@pytest.mark.parametrize(
    "text",
    ["x" * 50_000, "x\n" * 24_999 + "z", "\n" * 49_999 + "z"],
    ids=["long_line", "tiny_lines", "blank_lines"],
)
def test_catalog_bounds_payload_and_covers_entire_maximum_document(text):
    document = _document(text)
    catalog = citations.build_citation_catalog(document)
    assert len(catalog.entries) <= 532
    covered = set()
    for entry in catalog.entries:
        citations.validate_source_span(document, entry.span)
        covered.update(range(entry.span.start, entry.span.end))
    assert all(
        index in covered
        for index, character in enumerate(text)
        if not character.isspace()
    )
    # No duplicated page text or quadratic collection of overlapping candidates.
    payload = build_policy_extraction_prompt(document).policy_payload_json
    assert len(payload) <= 3 * len(text) + 10_000


def test_catalog_handles_are_bound_to_source_document_and_layout():
    document = _document("Same.\nSame.")
    foreign = _document("Same.\nOther.")
    first = citations.build_citation_catalog(document)
    second = citations.build_citation_catalog(foreign)
    with pytest.raises(
        citations.CitationValidationError, match="UNKNOWN_CITATION_HANDLE"
    ):
        first.resolve(second.entries[0].citation_handle)
    with pytest.raises(
        citations.CitationValidationError, match="UNKNOWN_CITATION_HANDLE"
    ):
        first.resolve("missing-private-quote")


async def test_provider_chooses_handles_and_python_materializes_all_public_citations():
    document = _document()
    payload = _payload(document)
    llm = ScriptedLLMClient((LLMResponse(output=payload),))
    extraction = await extract_policy(llm, CompilePolicyRequest(document=document))
    assert len(extraction.rules) == 2
    assert extraction.rules[0].provenance.span == extraction.rules[1].provenance.span
    assert (
        extraction.rules[0].provenance.span.quote == "Meals or hotels require receipts."
    )
    assert (
        extraction.unsupported_clauses[0].span.quote == "Reasonable costs may qualify."
    )
    assert extraction.unsupported_clauses[0].review_status == "provisional"
    for span in [
        *(r.provenance.span for r in extraction.rules),
        extraction.unsupported_clauses[0].span,
    ]:
        citations.validate_source_span(document, span)
    compiled = compile_baseline_policy(
        CompilePolicyRequest(document=document, extraction=extraction)
    )
    assert len({rule.rule_id for rule in compiled.policy.rules}) == 2
    assert len(llm.requests) == 1
    assert "SourceSpan" not in json.dumps(llm.requests[0].response_schema)
    assert "quote_sha256" not in json.dumps(llm.requests[0].response_schema)


@pytest.mark.parametrize("destination", ["rules", "unsupported_clauses"])
@pytest.mark.parametrize("foreign", [False, True])
async def test_unknown_and_foreign_handles_fail_closed_without_fallback(
    destination, foreign
):
    document = _document()
    payload = _payload(document)
    handle = (
        _payload(_document("Different.\nSource."))[destination][0]["citation_handle"]
        if foreign
        else "PRIVATE_UNKNOWN_HANDLE"
    )
    payload[destination][0]["citation_handle"] = handle
    llm = ScriptedLLMClient((LLMResponse(output=payload),))
    with pytest.raises(
        ExtractionValidationError, match="UNKNOWN_CITATION_HANDLE"
    ) as caught:
        await extract_policy(llm, CompilePolicyRequest(document=document))
    assert handle not in str(caught.value)
    assert len(llm.requests) == 1


async def test_provider_full_span_payload_is_rejected_after_one_repair():
    document = _document()
    payload = _payload(document)
    payload["rules"][0]["provenance"] = {"span": {"quote_sha256": "invented"}}
    llm = ScriptedLLMClient((LLMResponse(output=payload), LLMResponse(output=payload)))
    with pytest.raises(ModelOutputValidationError) as caught:
        await extract_policy(llm, CompilePolicyRequest(document=document))
    assert caught.value.repair_attempted
    assert len(llm.requests) == 2


@pytest.mark.parametrize(
    ("collection", "field"),
    [("rules", "overrides"), ("unsupported_clauses", "when_hint")],
)
async def test_omitted_private_semantic_fields_stop_after_one_repair(collection, field):
    document = _document()
    payload = _payload(document)
    payload[collection][0].pop(field)
    llm = ScriptedLLMClient((LLMResponse(output=payload), LLMResponse(output=payload)))

    with pytest.raises(ModelOutputValidationError) as caught:
        await extract_policy(llm, CompilePolicyRequest(document=document))

    assert caught.value.code == "SCHEMA_VALIDATION_FAILED"
    assert caught.value.repair_attempted
    assert (f"{collection}.0.{field}", "missing") in caught.value.issues
    assert len(llm.requests) == 2
    assert llm.requests[1].repair_attempt == 1


async def test_explicit_empty_overrides_and_null_hint_are_valid_provider_choices():
    document = _document()
    llm = ScriptedLLMClient((LLMResponse(output=_payload(document)),))

    extraction = await extract_policy(llm, CompilePolicyRequest(document=document))

    assert all(rule.overrides == () for rule in extraction.rules)
    assert extraction.unsupported_clauses[0].when_hint is None
    assert len(llm.requests) == 1


async def test_repair_requiring_explicit_fields_preserves_provider_scoped_hint():
    document = _document(
        "Meals or hotels require receipts.\nReasonable hotel costs may qualify."
    )
    initial = _payload(document)
    initial["rules"][0].pop("overrides")
    initial["unsupported_clauses"][0].pop("when_hint")
    repaired = _payload(document)
    repaired["unsupported_clauses"][0]["when_hint"] = [
        {"field": "expense_category", "operator": "eq", "value": "hotel"}
    ]
    llm = ScriptedLLMClient((LLMResponse(output=initial), LLMResponse(output=repaired)))

    extraction = await extract_policy(llm, CompilePolicyRequest(document=document))

    hint = extraction.unsupported_clauses[0].when_hint
    assert hint is not None
    assert [(item.field, item.operator, item.value) for item in hint] == [
        ("expense_category", "eq", "hotel")
    ]
    assert len(llm.requests) == 2
    assert llm.requests[1].repair_attempt == 1


async def test_provider_schema_repair_preserves_catalog_and_still_resolves_citations():
    document = _document()
    llm = ScriptedLLMClient(
        (LLMResponse(output="bad JSON"), LLMResponse(output=_payload(document)))
    )
    extraction = await extract_policy(llm, CompilePolicyRequest(document=document))
    assert len(extraction.rules) == 2
    original = json.loads(llm.requests[0].untrusted_payload_json)
    repaired = json.loads(llm.requests[1].untrusted_payload_json)
    assert original["citation_catalog"] == repaired["citation_catalog"]
    assert len(llm.requests) == 2


async def test_reused_long_source_is_not_subject_to_provider_output_size_limit():
    document = _document("Meals or hotels require receipts. " + "x" * 49_966)
    llm = ScriptedLLMClient((LLMResponse(output=_payload(document)),))
    extraction = await extract_policy(llm, CompilePolicyRequest(document=document))
    assert len(extraction.rules) == 2
    assert extraction.rules[0].provenance.span.end == 50_000
    assert extraction.unsupported_clauses[0].span == extraction.rules[0].provenance.span


@pytest.mark.parametrize(
    "mutation", ["duplicate_effect", "invariant_field", "unsupported_hint"]
)
async def test_hydration_retains_frozen_public_semantic_validators(mutation):
    document = _document()
    payload = _payload(document)
    if mutation == "duplicate_effect":
        payload["rules"][0]["effects"] *= 2
    elif mutation == "invariant_field":
        payload["rules"][0]["when"] = [
            {"field": "daily_category_total_minor", "operator": "gt", "value": 1}
        ]
    else:
        payload["unsupported_clauses"][0]["when_hint"] = [
            {"field": "daily_category_total_minor", "operator": "gt", "value": 1}
        ]
    llm = ScriptedLLMClient((LLMResponse(output=payload), LLMResponse(output=payload)))
    with pytest.raises(ModelOutputValidationError, match="SCHEMA_VALIDATION_FAILED"):
        await extract_policy(llm, CompilePolicyRequest(document=document))
    assert len(llm.requests) <= 2


async def test_private_overrides_reject_citation_aliases_even_when_a_rule_alias_matches():
    document = _document()
    payload = _payload(document)
    payload["rules"][1]["citation_handle"] = payload["unsupported_clauses"][0][
        "citation_handle"
    ]
    payload["rules"][1]["overrides"] = [
        {"dimension": "receipt_requirement", "target_rule_id": value}
        for value in ("rule_meal", payload["rules"][0]["citation_handle"])
    ]
    llm = ScriptedLLMClient((LLMResponse(output=payload),))
    with pytest.raises(ExtractionValidationError, match="UNKNOWN_OVERRIDE_REFERENCE"):
        await extract_policy(llm, CompilePolicyRequest(document=document))


async def test_rules_sharing_source_keep_independent_override_handles():
    document = _document()
    payload = _payload(document)
    payload["rules"][1]["overrides"] = [
        {"dimension": "receipt_requirement", "target_rule_id": "rule_meal"}
    ]
    llm = ScriptedLLMClient((LLMResponse(output=payload),))
    extraction = await extract_policy(llm, CompilePolicyRequest(document=document))
    compiled = compile_baseline_policy(
        CompilePolicyRequest(document=document, extraction=extraction)
    )
    assert (
        compiled.policy.rules[1].overrides[0].target_rule_id
        == compiled.policy.rules[0].rule_id
    )


async def test_semantically_identical_override_targets_fail_with_sanitized_error():
    document = _document()
    payload = _payload(document)
    duplicate = dict(
        payload["rules"][0], rule_handle="duplicate", description="PRIVATE_MODEL_VALUE"
    )
    payload["rules"].append(duplicate)
    payload["rules"][1]["overrides"] = [
        {"dimension": "receipt_requirement", "target_rule_id": value}
        for value in ("rule_meal", "duplicate")
    ]
    llm = ScriptedLLMClient((LLMResponse(output=payload),))
    with pytest.raises(
        ModelOutputValidationError, match="SCHEMA_VALIDATION_FAILED"
    ) as caught:
        await extract_policy(llm, CompilePolicyRequest(document=document))
    assert "PRIVATE_MODEL_VALUE" not in str(caught.value)


async def test_diagnostic_source_quotes_can_be_selected_without_model_hashes_or_offsets():
    root = Path(__file__).parents[4]
    source = (root / "samples/policies/development-policy.txt").read_text()
    document = _document(source)
    diagnostic = json.loads(
        (
            root
            / "team/person-1-integration/evidence/live-rehearsal-2026-09-06/diagnostic-response.json"
        ).read_text()
    )
    catalog = citations.build_citation_catalog(document)
    by_quote = {entry.span.quote: entry.citation_handle for entry in catalog.entries}
    # A fake chooses verified source handles; no model semantics are corrected.
    for rule in diagnostic["rules"]:
        rule["citation_handle"] = by_quote[rule.pop("provenance")["span"]["quote"]]
        # Preserve the legacy fixture's implicit empty override in the new wire
        # format. This citation-only fake does not assert semantic completeness.
        rule.setdefault("overrides", [])
    for clause in diagnostic["unsupported_clauses"]:
        clause["citation_handle"] = by_quote[clause.pop("span")["quote"]]
    llm = ScriptedLLMClient((LLMResponse(output=diagnostic),))
    extraction = await extract_policy(llm, CompilePolicyRequest(document=document))
    assert len(extraction.rules) == 10
    assert len(extraction.unsupported_clauses) == 1
    assert len(llm.requests) == 1
    for span in [
        *(r.provenance.span for r in extraction.rules),
        extraction.unsupported_clauses[0].span,
    ]:
        citations.validate_source_span(document, span)
