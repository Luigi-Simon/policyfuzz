"""Validate preserved human review records; issue correctness is scored separately.

This validates custody, source binding, and timing, not human identity or the
truth of independence assertions. It never creates or changes review evidence.
"""

from __future__ import annotations

import hashlib
import json
import re
import unicodedata
from datetime import UTC, datetime, timedelta
from pathlib import Path

OWNERS = ("person-1-integration", "person-4-evaluation")
MATCHED_FIELDS = (
    "reviewer_id",
    "reviewer_type",
    "independent",
    "candidate_version",
    "source_policy_sha256",
    "duration_seconds",
    "started_at",
    "completed_at",
    "first_reported_issue_seconds",
)
ATTEMPT_METADATA = (
    "team/person-1-integration/evidence/blind-first-run.json.metadata.json"
)
MAX_BYTES = 1_048_576


class ManualReviewError(ValueError):
    """A fixed public validation error with no review text or local path."""


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise ManualReviewError(message)


def _read(root: Path, relative: str) -> tuple[Path, bytes]:
    path = root / relative
    _require(
        not any(item.is_symlink() for item in (path, *path.parents))
        and path.resolve().is_relative_to(root.resolve()),
        "Manual review paths must be owned regular files without aliases.",
    )
    try:
        _require(
            path.is_file() and path.stat().st_size <= MAX_BYTES,
            "Manual review evidence is missing or too large.",
        )
        with path.open("rb") as stream:
            data = stream.read(MAX_BYTES + 1)
        _require(len(data) <= MAX_BYTES, "Manual review evidence is too large.")
    except OSError:
        raise ManualReviewError("Manual review evidence could not be read.") from None
    return path, data


def _json(data: bytes) -> dict:
    def unique(pairs):
        values = {}
        for key, value in pairs:
            _require(key not in values, "Manual review JSON contains duplicate fields.")
            values[key] = value
        return values

    def invalid(_):
        raise ManualReviewError("Manual review JSON is invalid.")

    try:
        value = json.loads(data, object_pairs_hook=unique, parse_constant=invalid)
    except (UnicodeError, json.JSONDecodeError):
        raise ManualReviewError("Manual review JSON is invalid.") from None
    _require(isinstance(value, dict), "Manual review JSON must be an object.")
    return value


def _time(value: object) -> datetime:
    _require(
        isinstance(value, str), "Manual review timestamps must include a timezone."
    )
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        _require(
            parsed.utcoffset() is not None,
            "Manual review timestamps must include a timezone.",
        )
        return parsed.astimezone(UTC)
    except (ValueError, OverflowError):
        raise ManualReviewError("Manual review timestamp is invalid.") from None


def _text(value: object) -> bool:
    return isinstance(value, str) and bool(value.strip())


def _validate_raw(
    raw: dict, active: dict, current: datetime, attempt_start: datetime
) -> str:
    reviewer = raw.get("reviewer_id")
    _require(
        _text(reviewer)
        and raw.get("reviewer_type") == "human"
        and raw.get("independent") is True,
        "Independent human reviewer metadata is required.",
    )
    _require(
        type(raw.get("candidate_version")) is int
        and raw["candidate_version"] == active["candidate_version"]
        and raw.get("source_policy_sha256") == active["source_policy_sha256"],
        "Manual review source does not match the active candidate.",
    )
    started = _time(raw.get("started_at"))
    completed = _time(raw.get("completed_at"))
    _require(
        type(raw.get("duration_seconds")) is int
        and raw["duration_seconds"] == 600
        and completed - started == timedelta(seconds=600)
        and completed <= current
        and completed <= attempt_start,
        "Manual reviews must last exactly ten minutes and finish before the model attempt.",
    )
    issues = raw.get("reported_issues")
    _require(isinstance(issues, list), "Manual review reported issues must be a list.")
    identifiers = set()
    observed = []
    for issue in issues:
        _require(isinstance(issue, dict), "Manual review issue is invalid.")
        identifier = issue.get("issue_id")
        seconds = issue.get("observed_at_seconds")
        _require(
            isinstance(identifier, str)
            and re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._:-]{0,127}", identifier)
            is not None
            and identifier not in identifiers
            and _text(issue.get("description"))
            and type(seconds) is int
            and 0 <= seconds <= 600,
            "Manual review issues require unique stable IDs, descriptions, and valid observation times.",
        )
        identifiers.add(identifier)
        observed.append(seconds)
    expected = min(observed) if observed else None
    first = raw.get("first_reported_issue_seconds")
    _require(
        "first_reported_issue_seconds" in raw
        and type(first) is type(expected)
        and first == expected,
        "First reported issue time does not match the original issue list.",
    )
    return unicodedata.normalize("NFC", reviewer).strip().casefold()


def validate_manual_reviews(
    root: Path, active: dict, *, now: datetime | None = None
) -> tuple[str, ...]:
    """Return both wrapper/raw path pairs for Gate B hashing after validation.

    ``now`` is an aware clock injection for deterministic tests. The original raw
    files must finish before the recorded blind attempt began. Returned paths are
    repository-relative POSIX strings; the attempt metadata is already hashed by
    Gate B. No field here asserts issue correctness or verifies a human identity.
    """
    current = datetime.now(UTC) if now is None else now
    _require(
        isinstance(current, datetime) and current.utcoffset() is not None,
        "Manual review validation requires an aware clock.",
    )
    _require(
        isinstance(active, dict)
        and type(active.get("candidate_version")) is int
        and active["candidate_version"] > 0
        and isinstance(active.get("source_policy_sha256"), str)
        and re.fullmatch(r"[0-9a-f]{64}", active["source_policy_sha256"]) is not None,
        "Active manual review candidate binding is invalid.",
    )
    _, attempt_bytes = _read(root, ATTEMPT_METADATA)
    attempt_start = _time(_json(attempt_bytes).get("started_at"))
    reviewers = set()
    paths = []
    identities = set()
    for owner in OWNERS:
        folder = f"team/{owner}/evidence"
        wrapper_name = f"{folder}/manual-review.json"
        raw_name = f"{folder}/manual-review.raw.json"
        wrapper_path, wrapper_bytes = _read(root, wrapper_name)
        wrapper = _json(wrapper_bytes)
        _require(
            wrapper.get("external_file") == raw_name,
            "Manual review original must use its exact owned path.",
        )
        raw_path, raw_bytes = _read(root, raw_name)
        _require(
            wrapper.get("external_file_sha256")
            == hashlib.sha256(raw_bytes).hexdigest(),
            "Manual review original bytes do not match the imported hash.",
        )
        raw = _json(raw_bytes)
        reviewer = _validate_raw(raw, active, current, attempt_start)
        _require(
            all(
                key in wrapper
                and key in raw
                and type(wrapper[key]) is type(raw[key])
                and wrapper[key] == raw[key]
                for key in MATCHED_FIELDS
            ),
            "Manual review wrapper does not match the preserved original.",
        )
        _require(
            reviewer not in reviewers, "Manual reviews require two distinct reviewers."
        )
        reviewers.add(reviewer)
        for path in (wrapper_path, raw_path):
            info = path.stat()
            identity = (info.st_dev, info.st_ino)
            _require(
                identity not in identities,
                "Manual review files must not alias another evidence file.",
            )
            identities.add(identity)
        paths.extend((wrapper_name, raw_name))
    return tuple(paths)
