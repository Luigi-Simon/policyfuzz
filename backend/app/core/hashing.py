"""The single canonical SHA256 implementation for integer-only domain values."""

import hashlib
import json
import unicodedata
from collections.abc import Mapping
from datetime import UTC, datetime
from enum import Enum
from uuid import UUID

from pydantic import BaseModel


def _canonical_json(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def normalize_for_hash(value: object) -> object:
    """Return NFC JSON values, retaining sequence order and canonicalizing sets.

    Model fields are read as Python values so nested sets retain their semantics.
    No model fields are excluded here; payload-specific exclusions belong to the
    artifact projections. Cycles, ambiguous keys and non-integer numbers fail.
    """
    active: set[int] = set()

    def normalize(item: object) -> object:
        if isinstance(item, Enum):
            return normalize(item.value)
        if item is None or isinstance(item, (bool, int)):
            return item
        if isinstance(item, float):
            raise TypeError("canonical hashing requires integer-only numbers")
        if isinstance(item, str):
            return unicodedata.normalize("NFC", item)
        if isinstance(item, UUID):
            return str(item)
        if isinstance(item, datetime):
            if item.tzinfo is None or item.utcoffset() is None:
                raise ValueError("canonical datetime must be timezone-aware")
            return (
                item.astimezone(UTC)
                .isoformat(timespec="microseconds")
                .replace("+00:00", "Z")
            )
        if not isinstance(item, (BaseModel, Mapping, list, tuple, set, frozenset)):
            raise TypeError(f"unsupported canonical value: {type(item).__name__}")
        identity = id(item)
        if identity in active:
            raise ValueError("cyclic values cannot be canonically hashed")
        active.add(identity)
        try:
            if isinstance(item, BaseModel):
                return normalize(dict(item))
            if isinstance(item, Mapping):
                result = {}
                for key, child in item.items():
                    if not isinstance(key, str):
                        raise TypeError("canonical mapping keys must be strings")
                    key = unicodedata.normalize("NFC", key)
                    if key in result:
                        raise ValueError("normalized mapping key collision")
                    result[key] = normalize(child)
                return result
            values = [normalize(child) for child in item]
            if isinstance(item, (set, frozenset)):
                unique = {_canonical_json(child): child for child in values}
                return [unique[key] for key in sorted(unique)]
            return values
        finally:
            active.remove(identity)

    return normalize(value)


def canonical_sha256(value: object) -> str:
    """Hash compact sorted-key UTF-8 JSON after canonical normalization."""
    return hashlib.sha256(
        _canonical_json(normalize_for_hash(value)).encode("utf-8")
    ).hexdigest()
