"""Behavioral contracts for deterministic, integer-only payload hashing."""

import hashlib
from datetime import UTC, datetime, timedelta, timezone
from enum import Enum
from uuid import UUID

import pytest
from pydantic import BaseModel, ConfigDict

from app.core.hashing import canonical_sha256, normalize_for_hash


def test_hash_matches_compact_sorted_utf8_json_and_normalizes_unicode():
    expected = hashlib.sha256('{"a":1,"b":"é"}'.encode()).hexdigest()
    assert canonical_sha256({"b": "e\u0301", "a": 1}) == expected
    assert canonical_sha256({"a": 1, "b": "é"}) == expected
    assert canonical_sha256({"e\u0301": 1}) == canonical_sha256({"é": 1})


def test_sequences_preserve_order_and_sets_sort_and_deduplicate_normalized_values():
    assert normalize_for_hash({"é", "e\u0301", "a"}) == ["a", "é"]
    assert canonical_sha256(frozenset({3, 20, 1})) == canonical_sha256([1, 20, 3])
    assert canonical_sha256((1, 2)) == canonical_sha256([1, 2])
    assert canonical_sha256([1, 2]) != canonical_sha256([2, 1])
    assert canonical_sha256(True) != canonical_sha256(1)
    assert canonical_sha256(None) != canonical_sha256("null")


def test_nested_models_preserve_python_set_semantics():
    class Inner(BaseModel):
        model_config = ConfigDict(frozen=True)
        roles: frozenset[str]

    class Outer(BaseModel):
        items: tuple[Inner, ...]

    model = Outer(items=(Inner(roles=frozenset({"b", "a"})),))
    assert normalize_for_hash(model) == {"items": [{"roles": ["a", "b"]}]}
    assert normalize_for_hash(frozenset({Inner(roles=frozenset({"a"}))})) == [
        {"roles": ["a"]}
    ]


def test_enum_uuid_and_aware_datetime_have_stable_json_values():
    class Label(Enum):
        ITEM = "e\u0301"

    instant = datetime(2026, 9, 4, 12, 30, tzinfo=timezone(timedelta(hours=8)))
    assert normalize_for_hash(instant) == "2026-09-04T04:30:00.000000Z"
    assert canonical_sha256(instant) == canonical_sha256(instant.astimezone(UTC))
    assert normalize_for_hash(Label.ITEM) == "é"
    assert normalize_for_hash(UUID("AABBCCDD-0000-0000-0000-000000000001")) == (
        "aabbccdd-0000-0000-0000-000000000001"
    )


@pytest.mark.parametrize("value", [0.0, 1.5, float("nan"), float("inf"), -float("inf")])
def test_all_floats_are_rejected(value):
    with pytest.raises(TypeError, match="integer-only"):
        canonical_sha256({"nested": [value]})


@pytest.mark.parametrize("value", [b"bytes", {1: "value"}, object(), complex(1, 2)])
def test_non_json_inputs_are_rejected(value):
    with pytest.raises(TypeError):
        canonical_sha256(value)


def test_naive_datetime_and_normalized_key_collision_are_rejected():
    with pytest.raises(ValueError, match="timezone"):
        canonical_sha256(datetime(2026, 9, 4, tzinfo=None))  # noqa: DTZ001 - rejection case
    with pytest.raises(ValueError, match="collision"):
        canonical_sha256({"e\u0301": 1, "é": 1})


@pytest.mark.parametrize("kind", ["list", "mapping", "model"])
def test_cycles_fail_cleanly_but_shared_values_are_allowed(kind):
    shared = {"a": [1]}
    assert normalize_for_hash([shared, shared]) == [{"a": [1]}, {"a": [1]}]
    if kind == "list":
        value = []
        value.append(value)
    elif kind == "mapping":
        value = {}
        value["self"] = value
    else:

        class Node(BaseModel):
            child: object = None

        value = Node()
        value.child = value
    with pytest.raises(ValueError, match="cycl"):
        canonical_sha256(value)


def test_canonical_hash_does_not_silently_remove_fields():
    assert canonical_sha256({"artifact_sha256": "a"}) != canonical_sha256(
        {"artifact_sha256": "b"}
    )
