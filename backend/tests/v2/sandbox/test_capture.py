from copy import deepcopy

import pytest

from app.v2.sandbox.capture import parse_records
from app.v2.sandbox.translation import EnglishText, checked_projection


def post(identifier=1, author=0, content="The service helps.", **metadata):
    return {"post_id": identifier, "user_id": author, "content": content, **metadata}


def test_quotes_do_not_reattribute_original_authors_words():
    rows = {
        "posts": [
            post(),
            post(2, 1, original_post_id=1),
            post(3, 1, original_post_id=1, quote_content="But who pays?"),
        ]
    }
    parsed, notes = parse_records(rows, 2, 3)
    assert [(r.identifier, r.content, parent) for r, parent in parsed] == [
        ("post:1", "The service helps.", None),
        ("post:3", "But who pays?", "post:1"),
    ]
    assert not notes


def test_original_records_metadata_are_not_mutated():
    rows = {"posts": [post(created_at="2026-09-10T12:00:00+08:00", round_number=2)]}
    before = deepcopy(rows)
    parsed, _ = parse_records(rows, 1, 3)
    assert rows == before
    assert parsed[0][0].recorded_at.isoformat() == "2026-09-10T12:00:00+08:00"
    assert parsed[0][0].round_number == 2


@pytest.mark.parametrize(
    "metadata",
    [
        {"created_at": "not-a-time", "round_number": 999},
        {"created_at": 0, "round_number": True},
    ],
)
def test_unknown_metadata_stays_unknown(metadata):
    parsed, notes = parse_records({"posts": [post(**metadata)]}, 1, 3)
    assert parsed[0][0].recorded_at is parsed[0][0].round_number is None
    assert len(notes) == 2


def test_missing_parent_is_not_invented():
    parsed, notes = parse_records(
        {
            "comments": [
                {"comment_id": 3, "post_id": 900, "user_id": 0, "content": "A reply."}
            ]
        },
        1,
        3,
    )
    assert parsed[0][1] is None
    assert any(n.startswith("unresolved_reply:") for n in notes)


def test_oasis_clock_mapping_requires_explicit_runner_clock_provenance():
    rows = {
        "posts": [post(created_at=0)],
        "comments": [
            {
                "comment_id": 1,
                "post_id": 1,
                "user_id": 0,
                "content": "Reply",
                "created_at": 2,
            }
        ],
    }
    mapped, notes = parse_records(rows, 1, 3, clock="oasis_step_v1")
    assert [record.round_number for record, _ in mapped] == [None, 2]
    assert all(record.recorded_at is None for record, _ in mapped)
    assert not notes
    unknown, notes = parse_records(rows, 1, 3)
    assert all(record.round_number is None for record, _ in unknown)
    assert notes


def test_cycles_are_bounded_and_flagged():
    rows = {
        "posts": [
            post(1, 0, original_post_id=2, quote_content="One"),
            post(2, 1, original_post_id=1, quote_content="Two"),
        ]
    }
    parsed, notes = parse_records(rows, 2, 3)
    assert len(parsed) == 2
    assert any(n.startswith("cyclic_replies:") for n in notes)


def test_duplicate_source_conflicts_and_same_text_are_distinguished():
    parsed, notes = parse_records(
        {"posts": [post(), post(), post(content="Changed"), post(2, 1)]}, 2, 3
    )
    assert len(parsed) == 2
    assert len(notes) == 1 and notes[0].startswith("duplicate_id_conflict:")


@pytest.mark.parametrize(
    "source,english",
    [
        ("仅限18岁及以上居民。", "Only residents aged 18 and above are eligible."),
        ("没有收据不得报销。", "Reimbursement is not allowed without a receipt."),
        ("每月不得超过500元。", "The monthly amount must not exceed 500 yuan."),
        (
            "Eligible residents only；不得超过50。",
            "Eligible residents only; must not exceed 50.",
        ),
    ],
)
def test_reviewed_eligibility_negation_limits_and_mixed_language(source, english):
    result = EnglishText(text=english, language="Mixed", translated=True)
    assert checked_projection(source, result) == result


@pytest.mark.parametrize(
    "source,result",
    [
        (
            "不得超过50。",
            EnglishText(
                text="Must not exceed 500.", language="Chinese", translated=True
            ),
        ),
        (
            "保留服务。",
            EnglishText(text="保留服务。", language="Chinese", translated=True),
        ),
        ("Bonjour", EnglishText(text="Bonjour", language="French", translated=False)),
        (
            "No more than 50.",
            EnglishText(text="More than 50.", language="English", translated=False),
        ),
    ],
)
def test_changed_amount_unchanged_foreign_text_and_false_english_are_rejected(
    source, result
):
    with pytest.raises(ValueError):
        checked_projection(source, result)
