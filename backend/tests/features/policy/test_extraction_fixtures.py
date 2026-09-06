import json
from pathlib import Path

import pytest

from app.domain.models import PolicyDocument, PolicyPage
from app.features.policy.extraction import parse_and_validate_policy_extraction
from app.features.policy.model_output import ModelOutputValidationError
from app.features.policy.prompts import build_policy_extraction_prompt

FIXTURE_PATH = (
    Path(__file__).parents[4] / "team/person-2-policy/fake-llm-responses.json"
)


@pytest.fixture(scope="module")
def responses() -> dict[str, object]:
    return json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def document(responses: dict[str, object]) -> PolicyDocument:
    text = responses["source_text"]
    assert isinstance(text, str)
    return PolicyDocument(
        document_id="fixture-document",
        title="Synthetic extraction fixture",
        source_type="bundled_sample",
        pages=(PolicyPage(page=1, text=text, start=0, end=len(text)),),
        document_sha256="a" * 64,
    )


def _raw(responses: dict[str, object], case: str) -> str:
    return json.dumps(responses[case])


def test_valid_fixture_has_exact_citations(
    responses: dict[str, object], document: PolicyDocument
) -> None:
    result = parse_and_validate_policy_extraction(
        document, _raw(responses, "valid_exact_citations")
    )

    assert len(result.extraction.rules) == 2
    assert result.excluded_rule_count == 0


@pytest.mark.parametrize("case", ["invalid_hash", "invalid_offsets"])
def test_invalid_citation_fixtures_are_excluded_without_losing_clause(
    responses: dict[str, object],
    document: PolicyDocument,
    case: str,
) -> None:
    result = parse_and_validate_policy_extraction(document, _raw(responses, case))

    assert result.extraction.rules == ()
    assert result.excluded_rule_count == 1
    assert result.extraction.unsupported_clauses[0].reason_code == "invalid_citation"


def test_unsupported_clause_fixture_is_preserved(
    responses: dict[str, object], document: PolicyDocument
) -> None:
    result = parse_and_validate_policy_extraction(
        document, _raw(responses, "unsupported_clause")
    )

    assert result.extraction.rules == ()
    assert result.extraction.unsupported_clauses[0].span.quote == (
        "Reasonable exceptions may apply."
    )


@pytest.mark.parametrize("case", ["invalid_predicate", "invalid_effect"])
def test_invalid_vocabulary_fixtures_fail_strict_contract_validation(
    responses: dict[str, object],
    document: PolicyDocument,
    case: str,
) -> None:
    with pytest.raises(ModelOutputValidationError, match="SCHEMA_VALIDATION_FAILED"):
        parse_and_validate_policy_extraction(document, _raw(responses, case))


def test_prompt_injection_fixture_remains_untrusted_policy_data(
    responses: dict[str, object], document: PolicyDocument
) -> None:
    injection = responses["prompt_injection_text"]
    prompt = build_policy_extraction_prompt(document)
    result = parse_and_validate_policy_extraction(
        document, _raw(responses, "prompt_injection_preserved")
    )

    assert isinstance(injection, str)
    assert injection not in prompt.system_instructions
    assert injection in prompt.policy_payload_json
    assert result.extraction.rules == ()
    assert result.extraction.unsupported_clauses[0].span.quote == injection


def test_more_than_twelve_rules_fixture_is_bounded(
    responses: dict[str, object], document: PolicyDocument
) -> None:
    result = parse_and_validate_policy_extraction(
        document, _raw(responses, "more_than_twelve_rules")
    )

    assert len(result.extraction.rules) == 12
    assert result.excluded_rule_count == 1


def test_or_clause_fixture_is_expanded_into_distinct_and_only_rules(
    responses: dict[str, object], document: PolicyDocument
) -> None:
    result = parse_and_validate_policy_extraction(
        document, _raw(responses, "or_expanded")
    )

    assert len(result.extraction.rules) == 2
    predicates = [rule.when for rule in result.extraction.rules]
    assert all(len(items) == 1 for items in predicates)
    assert {items[0].value for items in predicates} == {"meal", "hotel"}
