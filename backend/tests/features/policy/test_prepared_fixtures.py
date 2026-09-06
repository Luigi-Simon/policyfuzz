import json
from pathlib import Path


TEAM_DIR = Path(__file__).parents[4] / "team/person-2-policy"


def _load(name: str):
    return json.loads((TEAM_DIR / name).read_text(encoding="utf-8"))


def test_invariant_fixtures_cover_bounds_duplicates_and_confirmation_attack() -> None:
    fixtures = _load("invariant-suggestion-fixtures.json")

    assert len(fixtures["valid_three"]) == 3
    assert len(fixtures["too_few"]) < 3
    assert len(fixtures["too_many"]) > 5
    assert fixtures["duplicate_semantics"][0]["value"] == (
        fixtures["duplicate_semantics"][1]["value"]
    )
    assert fixtures["model_assigned_confirmation"][0]["review_status"] == (
        "session_confirmed"
    )


def test_revision_fixtures_cover_all_supported_and_forbidden_cases() -> None:
    fixtures = _load("revision-proposal-fixtures.json")

    assert set(fixtures["valid_operation_kinds"]) == {
        "add_rule",
        "replace_rule",
        "add_override",
    }
    invalid = fixtures["invalid_cases"]
    assert {
        "zero_operations",
        "four_operations",
        "delete_attempt",
        "unknown_target",
        "stale_revision",
        "stale_hash",
        "rejected_finding",
        "candidate_finding",
        "fake_model_ids",
        "false_success_claim",
        "prompt_injection",
    } <= invalid.keys()
