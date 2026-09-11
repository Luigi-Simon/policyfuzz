from app.v2.sandbox.capture import parse_records
from app.v2.sandbox.quality import discussion_quality


def test_duplicate_native_comments_are_flagged_without_discarding_sources():
    rows = {
        "posts": [
            {"post_id": i, "user_id": i - 1, "content": f"Opening {i}", "created_at": 0}
            for i in range(1, 6)
        ],
        "comments": [
            {
                "comment_id": i,
                "post_id": 1,
                "user_id": 1 + i % 4,
                "content": "The same generated comment.",
                "created_at": 1,
            }
            for i in range(1, 7)
        ],
    }
    parsed, _ = parse_records(rows, 5, 2, clock="oasis_step_v1")
    before = [(r.identifier, r.content, parent) for r, parent in parsed]
    notes = discussion_quality(parsed)
    assert any(n.startswith("discussion_quality: duplicate") for n in notes)
    assert any("6 of 6" in n and "1 of 5" in n for n in notes)
    assert before == [(r.identifier, r.content, parent) for r, parent in parsed]


def test_balanced_distinct_comments_need_no_quality_warning():
    rows = {
        "posts": [
            {"post_id": i, "user_id": i - 1, "content": f"Opening {i}"}
            for i in range(1, 6)
        ],
        "comments": [
            {
                "comment_id": i,
                "post_id": i % 5 + 1,
                "user_id": i % 5,
                "content": f"Distinct question {i}",
            }
            for i in range(1, 7)
        ],
    }
    parsed, _ = parse_records(rows, 5, 2)
    assert discussion_quality(parsed) == []
