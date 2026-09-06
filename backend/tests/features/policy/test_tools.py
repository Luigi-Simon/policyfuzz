import pytest

from app.features.policy.ingest import prepare_policy_pages, prepare_policy_text
from app.features.policy.tools import (
    PolicyToolError,
    find_section,
    get_clause_context,
    read_page,
    search_policy,
)


def test_read_page_returns_bounded_page_with_offsets() -> None:
    policy = prepare_policy_pages(("First page text", "Second page text"))

    result = read_page(policy, page_number=2, max_characters=6)

    assert result.page_number == 2
    assert result.text == "Second"
    assert result.start_offset == policy.pages[1].start_offset
    assert result.end_offset == policy.pages[1].start_offset + 6
    assert result.truncated is True


def test_read_page_rejects_invalid_page_without_exposing_text() -> None:
    secret = "PRIVATE student information"
    policy = prepare_policy_text(secret)

    with pytest.raises(PolicyToolError, match="PAGE_OUT_OF_RANGE") as exc_info:
        read_page(policy, page_number=2)

    assert secret not in str(exc_info.value)


def test_search_policy_is_case_insensitive_and_preserves_offsets() -> None:
    policy = prepare_policy_pages(
        ("Receipts are required for meals.", "MEALS above SGD 80 are denied.")
    )

    results = search_policy(policy, "meals")

    assert len(results) == 2
    assert results[0].page_number == 1
    assert policy.text[results[0].start_offset : results[0].end_offset] == "meals"
    assert results[1].page_number == 2
    assert policy.text[results[1].start_offset : results[1].end_offset] == "MEALS"


def test_search_policy_limits_results_and_context() -> None:
    policy = prepare_policy_text("rule " * 20)

    results = search_policy(policy, "rule", max_results=3, context_characters=5)

    assert len(results) == 3
    assert all(len(result.context) <= len("rule") + 10 for result in results)


@pytest.mark.parametrize("query", ["", "   ", "x" * 201])
def test_search_policy_rejects_invalid_query(query: str) -> None:
    policy = prepare_policy_text("A valid policy")

    with pytest.raises(PolicyToolError, match="INVALID_SEARCH_QUERY"):
        search_policy(policy, query)


def test_find_section_returns_heading_and_body_until_next_section() -> None:
    policy = prepare_policy_text(
        "1. Meals\nMeal rules.\n\n2. Approval\nApproval rules.\n\n3. Hotels\nHotel rules."
    )

    result = find_section(policy, "2")

    assert result.section_name == "2"
    assert result.page_number == 1
    assert result.text == "2. Approval\nApproval rules."
    assert policy.text[result.start_offset : result.end_offset] == result.text


@pytest.mark.parametrize(
    ("heading", "section_name"),
    [
        ("2.1 Receipt rules\nKeep receipts.", "2.1"),
        ("4(b) Appeals\nAn appeal is allowed.", "4(b)"),
    ],
)
def test_find_section_supports_nested_and_lettered_headings(
    heading: str,
    section_name: str,
) -> None:
    policy = prepare_policy_text(f"1. Intro\nText.\n\n{heading}\n\n5. End\nText.")

    result = find_section(policy, section_name)

    assert result.text == heading


def test_find_section_rejects_missing_section() -> None:
    policy = prepare_policy_text("1. Meals\nMeal rules.")

    with pytest.raises(PolicyToolError, match="SECTION_NOT_FOUND"):
        find_section(policy, "9")


def test_get_clause_context_returns_bounded_surrounding_text() -> None:
    policy = prepare_policy_text("0123456789CLAUSEabcdefghij")

    result = get_clause_context(
        policy,
        page_number=1,
        start_offset=10,
        end_offset=16,
        context_characters=4,
    )

    assert result.text == "6789CLAUSEabcd"
    assert result.start_offset == 6
    assert result.end_offset == 20


@pytest.mark.parametrize(("start", "end"), [(-1, 2), (3, 3), (4, 2), (0, 999)])
def test_get_clause_context_rejects_invalid_offsets(start: int, end: int) -> None:
    policy = prepare_policy_text("Short policy")

    with pytest.raises(PolicyToolError, match="OFFSETS_OUT_OF_RANGE"):
        get_clause_context(policy, page_number=1, start_offset=start, end_offset=end)
