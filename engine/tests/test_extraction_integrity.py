from copy import deepcopy

import pytest
from app.contracts.policy import PolicyDocument
from app.llm import LLMError
from app.services.extract import (
    _ir_from_llm,
    _user_prompt,
    extract_policy_ir,
    heuristic_extract,
)

SOURCE = "Employees must obtain approval before claiming expenses."


def document(*pages):
    return PolicyDocument(
        filename="synthetic-policy.txt",
        pages=list(pages),
        page_count=len(pages),
        text="\n\n".join(pages),
    )


def model_payload():
    return {
        "title": "Expense policy",
        "actor_types": [{"id": "employee", "label": "Employee"}],
        "actions": [{"name": "claim_expense"}],
        "rules": [
            {
                "id": "R042",
                "title": "Approval",
                "statement": SOURCE,
                "citations": [{"quote": SOURCE, "page": 1}],
                "applies_to": ["employee"],
                "when": [
                    {"field": "action.name", "op": "eq", "value": "claim_expense"}
                ],
                "then": [{"modality": "must", "action": "claim_expense"}],
            }
        ],
    }


class ScriptedAdapter:
    enabled = True

    def __init__(self, response=None, error=None):
        self.response = response
        self.error = error

    def complete_json(self, **kwargs):
        if self.error:
            raise self.error
        return deepcopy(self.response)


@pytest.mark.parametrize("quote", ["Invented approval requirement.", "", "   ", None])
def test_model_citation_must_be_nonempty_exact_source_text(quote):
    raw = model_payload()
    raw["rules"][0]["citations"][0]["quote"] = quote
    with pytest.raises(ValueError, match="citation"):
        _ir_from_llm(document(SOURCE), raw)


def test_every_citation_is_validated_not_only_first():
    raw = model_payload()
    raw["rules"][0]["citations"].append({"quote": "Fabricated source.", "page": 1})
    with pytest.raises(ValueError, match="citation"):
        _ir_from_llm(document(SOURCE), raw)


def test_missing_citation_is_not_fabricated_from_statement():
    raw = model_payload()
    raw["rules"][0]["citations"] = []
    with pytest.raises(ValueError, match="citation"):
        _ir_from_llm(document(SOURCE), raw)


@pytest.mark.parametrize("page", [0, -1, 3, True, "1", 1.5])
def test_citation_page_requires_valid_integer_page(page):
    raw = model_payload()
    raw["rules"][0]["citations"][0]["page"] = page
    with pytest.raises(ValueError, match="citation"):
        _ir_from_llm(document(SOURCE, "Other page."), raw)


def test_valid_quote_on_wrong_page_is_rejected():
    raw = model_payload()
    raw["rules"][0]["citations"][0]["page"] = 2
    with pytest.raises(ValueError, match="citation"):
        _ir_from_llm(document(SOURCE, "Other page."), raw)


def test_long_quote_is_validated_in_full_without_truncation():
    prefix = "Employees must retain receipts. " * 12
    raw = model_payload()
    raw["rules"][0]["citations"][0]["quote"] = prefix + "Invented ending."
    with pytest.raises(ValueError, match="citation"):
        _ir_from_llm(document(prefix + "Actual ending."), raw)


def test_long_valid_quote_preserves_exact_text():
    quote = "Employees must retain receipts. " * 12
    raw = model_payload()
    raw["rules"][0]["citations"][0]["quote"] = quote
    ir = _ir_from_llm(document(quote), raw)
    assert ir.rules[0].citations[0].quote == quote


def test_null_page_is_resolved_from_exact_source_match():
    raw = model_payload()
    raw["rules"][0]["citations"][0]["page"] = None
    ir = _ir_from_llm(document("Other page.", SOURCE), raw)
    assert ir.rules[0].citations[0].page == 2


def test_model_rule_identity_survives_reordering():
    raw = model_payload()
    other = deepcopy(raw["rules"][0])
    other["id"] = "R017"
    raw["rules"].insert(0, other)
    ir = _ir_from_llm(document(SOURCE), raw)
    assert [rule.id for rule in ir.rules] == ["R017", "R042"]


def test_duplicate_model_rule_ids_are_rejected():
    raw = model_payload()
    raw["rules"].append(deepcopy(raw["rules"][0]))
    with pytest.raises(ValueError, match="rule id"):
        _ir_from_llm(document(SOURCE), raw)


@pytest.mark.parametrize(
    "error", [LLMError("private provider detail"), ValueError("private parse detail")]
)
def test_live_provider_failure_never_silently_returns_heuristic(error):
    with pytest.raises(ValueError, match="No heuristic replacement") as raised:
        extract_policy_ir(document(SOURCE), ScriptedAdapter(error=error))
    assert "private" not in str(raised.value)


def test_live_invalid_citation_never_silently_returns_heuristic():
    raw = model_payload()
    raw["rules"][0]["citations"][0]["quote"] = "Invented sentence."
    with pytest.raises(ValueError, match="No heuristic replacement"):
        extract_policy_ir(document(SOURCE), ScriptedAdapter(raw))


@pytest.mark.parametrize(
    "field,value",
    [
        ("actor_types", []),
        ("actions", []),
        ("rules", []),
    ],
)
def test_live_missing_policy_structure_fails_closed(field, value):
    raw = model_payload()
    raw[field] = value
    with pytest.raises(ValueError, match="No heuristic replacement"):
        extract_policy_ir(document(SOURCE), ScriptedAdapter(raw))


@pytest.mark.parametrize(
    "key,value",
    [
        ("applies_to", ["invented_actor"]),
        ("then", [{"modality": "must", "action": "invented_action"}]),
        (
            "when",
            [
                {
                    "field": "action.name",
                    "op": "invented_operator",
                    "value": "claim_expense",
                }
            ],
        ),
        ("when", ["invalid predicate"]),
        ("then", []),
    ],
)
def test_live_invalid_rule_structure_is_not_repaired_into_executable_rule(key, value):
    raw = model_payload()
    raw["rules"][0][key] = value
    with pytest.raises(ValueError, match="No heuristic replacement"):
        extract_policy_ir(document(SOURCE), ScriptedAdapter(raw))


def test_valid_live_ir_compiles_with_verified_source_citation():
    ir = extract_policy_ir(document(SOURCE), ScriptedAdapter(model_payload()))
    assert ir.rules[0].citations[0].quote == SOURCE
    assert ir.index.rules_by_actor == {"employee": ["R042"]}


def test_offline_heuristic_is_explicitly_labelled_as_unverified_demo():
    ir = heuristic_extract(document(SOURCE))
    assert any(
        "demo" in note.lower() and "unverified" in note.lower()
        for note in ir.open_questions
    )


def test_heuristic_citations_preserve_source_whitespace():
    text = "Employees must\nretain  receipts for all expenses."
    ir = heuristic_extract(document(text))
    assert all(
        citation.quote in text for rule in ir.rules for citation in rule.citations
    )


def test_model_prompt_does_not_silently_clip_long_pages():
    text = "Policy introduction. " * 400 + SOURCE
    assert SOURCE in _user_prompt(document(text))


def test_model_prompt_rejects_oversize_source_instead_of_partial_extraction():
    with pytest.raises(ValueError, match="too long"):
        _user_prompt(document("a" * 24001))
