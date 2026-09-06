"""Manual-review custody checks use only synthetic temporary evidence."""

import hashlib
import json
from datetime import UTC, datetime

import pytest

OWNERS = ("person-1-integration", "person-4-evaluation")
NOW = datetime(2026, 9, 6, 12, tzinfo=UTC)


def write(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, sort_keys=True) + "\n")
    return hashlib.sha256(path.read_bytes()).hexdigest()


@pytest.fixture
def reviews(tmp_path):
    active = {"candidate_version": 2, "source_policy_sha256": "a" * 64}
    for index, owner in enumerate(OWNERS):
        folder = tmp_path / "team" / owner / "evidence"
        raw = {
            "reviewer_id": f"synthetic-reviewer-{index}",
            "reviewer_type": "human",
            "independent": True,
            **active,
            "duration_seconds": 600,
            "started_at": "2026-09-06T11:00:00Z",
            "completed_at": "2026-09-06T11:10:00Z",
            "reported_issues": [
                {
                    "issue_id": "issue-a",
                    "description": "Synthetic observation A",
                    "observed_at_seconds": 120,
                },
                {
                    "issue_id": "issue-b",
                    "description": "Synthetic observation B",
                    "observed_at_seconds": 0,
                },
            ],
            "first_reported_issue_seconds": 0,
        }
        raw_path = folder / "manual-review.raw.json"
        digest = write(raw_path, raw)
        wrapper = {key: value for key, value in raw.items() if key != "reported_issues"}
        wrapper.update(
            external_file=raw_path.relative_to(tmp_path).as_posix(),
            external_file_sha256=digest,
        )
        write(folder / "manual-review.json", wrapper)
    write(
        tmp_path
        / "team/person-1-integration/evidence/blind-first-run.json.metadata.json",
        {"started_at": "2026-09-06T11:20:00Z"},
    )
    return tmp_path, active


def amend(reviews, mutate, owner=OWNERS[0]):
    root, _ = reviews
    folder = root / "team" / owner / "evidence"
    wrapper_path = folder / "manual-review.json"
    raw_path = folder / "manual-review.raw.json"
    raw = json.loads(raw_path.read_text())
    wrapper = json.loads(wrapper_path.read_text())
    mutate(raw, wrapper)
    wrapper["external_file_sha256"] = write(raw_path, raw)
    write(wrapper_path, wrapper)


def test_valid_reviews_return_both_original_files_and_wrappers_without_writing(reviews):
    from scripts.manual_review import validate_manual_reviews

    root, active = reviews
    before = {path: path.read_bytes() for path in root.rglob("*.json")}
    paths = validate_manual_reviews(root, active, now=NOW)
    assert paths == tuple(
        f"team/{owner}/evidence/{name}"
        for owner in OWNERS
        for name in ("manual-review.json", "manual-review.raw.json")
    )
    assert {path: path.read_bytes() for path in before} == before


def test_empty_issue_list_has_null_first_reported_time(reviews):
    from scripts.manual_review import validate_manual_reviews

    def change(raw, wrapper):
        raw["reported_issues"] = []
        raw["first_reported_issue_seconds"] = wrapper[
            "first_reported_issue_seconds"
        ] = None

    amend(reviews, change)
    assert len(validate_manual_reviews(*reviews, now=NOW)) == 4


def test_changed_original_bytes_are_rejected_even_if_json_content_is_unchanged(reviews):
    from scripts.manual_review import ManualReviewError, validate_manual_reviews

    root, active = reviews
    raw = root / f"team/{OWNERS[0]}/evidence/manual-review.raw.json"
    raw.write_bytes(raw.read_bytes() + b"\n")
    with pytest.raises(ManualReviewError):
        validate_manual_reviews(root, active, now=NOW)


@pytest.mark.parametrize(
    "path",
    [
        "./team/person-1-integration/evidence/manual-review.raw.json",
        "team/person-4-evaluation/evidence/manual-review.raw.json",
        "team/person-1-integration/evidence/../evidence/manual-review.raw.json",
        "../manual-review.raw.json",
        "team/person-1-integration/evidence/manual-review.json",
        "/tmp/manual-review.raw.json",
    ],
)
def test_external_file_must_be_the_exact_owned_original_path(reviews, path):
    from scripts.manual_review import ManualReviewError, validate_manual_reviews

    amend(reviews, lambda raw, wrapper: wrapper.update(external_file=path))
    with pytest.raises(ManualReviewError):
        validate_manual_reviews(*reviews, now=NOW)


@pytest.mark.parametrize(
    "field,value",
    [
        ("source_policy_sha256", "b" * 64),
        ("candidate_version", 3),
        ("candidate_version", True),
        ("independent", False),
        ("reviewer_type", "agent"),
        ("reviewer_id", " "),
    ],
)
def test_source_and_reviewer_binding_is_required(reviews, field, value):
    from scripts.manual_review import ManualReviewError, validate_manual_reviews

    def change(raw, wrapper):
        raw[field] = wrapper[field] = value

    amend(reviews, change)
    with pytest.raises(ManualReviewError):
        validate_manual_reviews(*reviews, now=NOW)


@pytest.mark.parametrize(
    "field,value",
    [
        ("started_at", "2026-09-06T11:00:00"),
        ("completed_at", "2026-09-06T11:09:59Z"),
        ("completed_at", "2026-09-06T11:10:00.000001Z"),
        ("duration_seconds", 599),
        ("duration_seconds", 600.0),
        ("completed_at", "not-a-time"),
    ],
)
def test_exact_aware_ten_minute_timing_is_required(reviews, field, value):
    from scripts.manual_review import ManualReviewError, validate_manual_reviews

    def change(raw, wrapper):
        raw[field] = wrapper[field] = value

    amend(reviews, change)
    with pytest.raises(ManualReviewError):
        validate_manual_reviews(*reviews, now=NOW)


def test_future_review_is_rejected(reviews):
    from scripts.manual_review import ManualReviewError, validate_manual_reviews

    with pytest.raises(ManualReviewError):
        validate_manual_reviews(*reviews, now=datetime(2026, 9, 6, 11, 5, tzinfo=UTC))


@pytest.mark.parametrize(
    "issue",
    [
        "negative",
        "late",
        "bool",
        "float",
        "duplicate",
        "empty_description",
        "missing_id",
        "wrong_first",
        "null_first",
        "empty_nonnull",
    ],
)
def test_issue_clocks_ids_descriptions_and_first_report_match_raw_list(reviews, issue):
    from scripts.manual_review import ManualReviewError, validate_manual_reviews

    def change(raw, wrapper):
        first = raw["reported_issues"][0]
        if issue in {"negative", "late", "bool", "float"}:
            first["observed_at_seconds"] = {
                "negative": -1,
                "late": 601,
                "bool": True,
                "float": 3.0,
            }[issue]
        elif issue == "duplicate":
            first["issue_id"] = raw["reported_issues"][1]["issue_id"]
        elif issue == "empty_description":
            first["description"] = " "
        elif issue == "missing_id":
            first.pop("issue_id")
        elif issue == "empty_nonnull":
            raw["reported_issues"] = []
        else:
            raw["first_reported_issue_seconds"] = wrapper[
                "first_reported_issue_seconds"
            ] = 120 if issue == "wrong_first" else None

    amend(reviews, change)
    with pytest.raises(ManualReviewError):
        validate_manual_reviews(*reviews, now=NOW)


@pytest.mark.parametrize(
    "field,value",
    [
        ("reviewer_id", "other-reviewer"),
        ("source_policy_sha256", "c" * 64),
        ("duration_seconds", 599),
        ("first_reported_issue_seconds", False),
    ],
)
def test_wrapper_must_match_the_preserved_original(reviews, field, value):
    from scripts.manual_review import ManualReviewError, validate_manual_reviews

    amend(reviews, lambda raw, wrapper: wrapper.update({field: value}))
    with pytest.raises(ManualReviewError):
        validate_manual_reviews(*reviews, now=NOW)


def test_two_reviewers_must_be_distinct(reviews):
    from scripts.manual_review import ManualReviewError, validate_manual_reviews

    def change(raw, wrapper):
        raw["reviewer_id"] = wrapper["reviewer_id"] = "synthetic-reviewer-0"

    amend(reviews, change, owner=OWNERS[1])
    with pytest.raises(ManualReviewError):
        validate_manual_reviews(*reviews, now=NOW)


@pytest.mark.parametrize("target", ["raw", "folder"])
def test_symlinks_are_rejected_including_parent_components(reviews, tmp_path, target):
    from scripts.manual_review import ManualReviewError, validate_manual_reviews

    root, active = reviews
    folder = root / f"team/{OWNERS[0]}/evidence"
    path = folder / "manual-review.raw.json" if target == "raw" else folder
    moved = tmp_path / ("moved.json" if target == "raw" else "moved")
    path.rename(moved)
    path.symlink_to(moved, target_is_directory=target == "folder")
    with pytest.raises(ManualReviewError):
        validate_manual_reviews(root, active, now=NOW)


@pytest.mark.parametrize(
    "started_at", ["2026-09-06T11:09:59Z", "2026-09-06T11:20:00", None]
)
def test_manual_review_must_finish_before_aware_model_attempt_time(reviews, started_at):
    from scripts.manual_review import ManualReviewError, validate_manual_reviews

    root, active = reviews
    write(
        root / "team/person-1-integration/evidence/blind-first-run.json.metadata.json",
        {"started_at": started_at},
    )
    with pytest.raises(ManualReviewError):
        validate_manual_reviews(root, active, now=NOW)


def test_reviewer_identity_comparison_normalizes_case_whitespace_and_nfc(reviews):
    from scripts.manual_review import ManualReviewError, validate_manual_reviews

    def first(raw, wrapper):
        raw["reviewer_id"] = wrapper["reviewer_id"] = "Café"

    def second(raw, wrapper):
        raw["reviewer_id"] = wrapper["reviewer_id"] = "  CAFE\u0301  "

    amend(reviews, first)
    amend(reviews, second, owner=OWNERS[1])
    with pytest.raises(ManualReviewError):
        validate_manual_reviews(*reviews, now=NOW)
