import pytest
from pydantic import ValidationError

from app.domain.models import (
    AssertionContent,
    CompilePolicyRequest,
    InvariantDraft,
    InvariantSuggestion,
    InvariantSuggestions,
    PolicyCompilation,
    PolicyDocument,
    PolicyPage,
    Predicate,
)

from .factories import HASH, make_policy


def make_suggestion(index: int, **changes: object) -> InvariantSuggestion:
    values = {
        "invariant_id": f"suggestion-{index}",
        "description": f"Daily meal total stays under limit {index}",
        "rationale": f"Protect the daily policy intent {index}",
        "when": (
            Predicate(field="expense_category", operator="eq", value="meal"),
            Predicate(field="daily_category_total_minor", operator="lte", value=10_000),
        ),
        "assertion": AssertionContent(
            assertion_id=f"suggested-assertion-{index}",
            target_kind="effect_value",
            dimension="daily_category_cap_minor",
            operator="lte",
            expected_value=10_000 + index,
        ),
    }
    return InvariantSuggestion(**(values | changes))


def test_suggestion_is_unconfirmed_and_permits_derived_daily_total() -> None:
    suggestion = make_suggestion(0)

    assert suggestion.origin == "model_suggestion"
    assert suggestion.when[1].field == "daily_category_total_minor"
    assert "severity" not in type(suggestion).model_fields
    assert "source_invariant_id" not in type(suggestion.assertion).model_fields
    with pytest.raises(ValidationError):
        make_suggestion(0, origin="session_confirmed")


@pytest.mark.parametrize("count", [0, 1, 2, 6])
def test_suggestion_collection_requires_three_to_five_items(count: int) -> None:
    with pytest.raises(ValidationError):
        InvariantSuggestions(
            invariant_drafts=tuple(make_suggestion(index) for index in range(count))
        )


def test_suggestion_collection_rejects_duplicate_ids() -> None:
    suggestions = [make_suggestion(index) for index in range(3)]
    suggestions[2] = make_suggestion(2, invariant_id="suggestion-0")
    with pytest.raises(ValidationError, match="suggestion IDs must be unique"):
        InvariantSuggestions(invariant_drafts=tuple(suggestions))

    suggestions[2] = make_suggestion(
        2,
        assertion=make_suggestion(2).assertion.model_copy(
            update={"assertion_id": "suggested-assertion-0"}
        ),
    )
    with pytest.raises(
        ValidationError, match="suggestion assertion IDs must be unique"
    ):
        InvariantSuggestions(invariant_drafts=tuple(suggestions))


def test_suggestion_collection_treats_when_as_unordered_and_semantic() -> None:
    first = make_suggestion(0)
    duplicate = make_suggestion(
        2,
        invariant_id="different-id",
        description="Different display description",
        rationale="Different display rationale",
        when=tuple(reversed(first.when)),
        assertion=first.assertion.model_copy(
            update={"assertion_id": "different-assertion"}
        ),
    )

    with pytest.raises(ValidationError, match="suggestion semantics must be unique"):
        InvariantSuggestions(invariant_drafts=(first, make_suggestion(1), duplicate))


def test_suggestion_semantics_ignore_membership_value_order() -> None:
    first = make_suggestion(
        0,
        when=(
            Predicate(
                field="expense_category",
                operator="in",
                value=("meal", "hotel"),
            ),
        ),
    )
    duplicate = make_suggestion(
        2,
        when=(
            Predicate(
                field="expense_category",
                operator="in",
                value=("hotel", "meal"),
            ),
        ),
        assertion=first.assertion.model_copy(
            update={"assertion_id": "different-assertion"}
        ),
    )

    with pytest.raises(ValidationError, match="suggestion semantics must be unique"):
        InvariantSuggestions(invariant_drafts=(first, make_suggestion(1), duplicate))


def test_confirmed_invariant_model_rejects_model_suggestion() -> None:
    suggestion = make_suggestion(0)
    with pytest.raises(ValidationError):
        InvariantDraft.model_validate(suggestion.model_dump() | {"severity": "high"})


def test_compilation_accepts_empty_or_three_to_five_suggestions() -> None:
    assert PolicyCompilation(policy=make_policy()).invariant_drafts == ()
    suggestions = tuple(make_suggestion(index) for index in range(3))
    assert (
        PolicyCompilation(
            policy=make_policy(), invariant_drafts=suggestions
        ).invariant_drafts
        == suggestions
    )
    with pytest.raises(ValidationError):
        PolicyCompilation(policy=make_policy(), invariant_drafts=suggestions[:2])


def test_compilation_rejects_duplicate_suggestion_semantics() -> None:
    first = make_suggestion(0)
    duplicate = make_suggestion(
        2,
        invariant_id="different-id",
        description="Different display description",
        rationale="Different display rationale",
        when=tuple(reversed(first.when)),
        assertion=first.assertion.model_copy(
            update={"assertion_id": "different-assertion"}
        ),
    )

    with pytest.raises(ValidationError, match="suggestion semantics must be unique"):
        PolicyCompilation(
            policy=make_policy(),
            invariant_drafts=(first, make_suggestion(1), duplicate),
        )


def test_compile_request_allows_document_only_input() -> None:
    document = PolicyDocument(
        document_id="document-1",
        title="Synthetic policy",
        source_type="pasted_text",
        pages=(PolicyPage(page=1, text="Synthetic policy", start=0, end=16),),
        document_sha256=HASH,
    )

    assert CompilePolicyRequest(document=document).extraction is None
