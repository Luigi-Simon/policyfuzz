import json
import sqlite3

import pytest

from app.v2.diagnostics import record, recording


def test_diagnostics_survive_failure_without_policy_or_provider_content(tmp_path):
    path = tmp_path / "attempts.sqlite"
    with pytest.raises(RuntimeError), recording(path, "run-one"):
        record("roster", "failed", code="provider_authentication", attempt=1)
        raise RuntimeError("private provider text")
    with recording(path, "run-two"):
        record("roster", "completed", count=20)
    with sqlite3.connect(path) as db:
        rows = db.execute("SELECT run_id, payload FROM events ORDER BY id").fetchall()
    assert [row[0] for row in rows] == [
        "run-one",
        "run-one",
        "run-one",
        "run-two",
        "run-two",
        "run-two",
    ]
    assert "private" not in str(rows)
    assert json.loads(rows[1][1])["code"] == "provider_authentication"
    assert json.loads(rows[2][1])["event"] == "failed"


def test_attempt_can_be_linked_to_exact_sandbox_request(tmp_path):
    path = tmp_path / "attempts.sqlite"
    with recording(path, "run-one"):
        record(
            "sandbox",
            "bound",
            request_id="00000000-0000-4000-8000-000000000000",
            fingerprint="a" * 64,
        )
    with sqlite3.connect(path) as db:
        row = db.execute("SELECT payload FROM events WHERE id=2").fetchone()
    assert json.loads(row[0])["fingerprint"] == "a" * 64


def test_unknown_diagnostic_fields_are_rejected(tmp_path):
    with recording(tmp_path / "attempts.sqlite", "run"), pytest.raises(ValueError):
        record("roster", "failed", policy_text="private")
