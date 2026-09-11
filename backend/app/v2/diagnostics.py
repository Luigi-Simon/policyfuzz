"""Local attempt metadata, including failures before a native job exists.

Only fixed codes, counts and stage names are accepted. No exception text, policy,
seed, provider output or credentials are written. Context isolation keeps parallel
requests and cancelled tasks from contaminating another run's incident record.
"""

import json
import logging
import re
import sqlite3
from contextlib import contextmanager
from contextvars import ContextVar
from datetime import UTC, datetime
from pathlib import Path

_context = ContextVar("v2_diagnostics", default=None)
_FIELDS = {"code", "attempt", "count", "request_id", "fingerprint"}
_TOKEN = re.compile(r"[a-z][a-z0-9_]{0,63}\Z")
_IDENTITY = {
    "request_id": re.compile(r"[0-9a-f-]{36}\Z"),
    "fingerprint": re.compile(r"[0-9a-f]{64}\Z"),
}


def record(stage, event, **fields):
    if set(fields) - _FIELDS or not all(_TOKEN.fullmatch(v) for v in (stage, event)):
        raise ValueError("Unsupported diagnostic metadata")
    for key, value in fields.items():
        pattern = _IDENTITY.get(key, _TOKEN if key == "code" else None)
        valid = (
            isinstance(value, str) and pattern.fullmatch(value)
            if pattern
            else type(value) is int and 0 <= value <= 10000
        )
        if not valid:
            raise ValueError("Invalid diagnostic value")
    context = _context.get()
    if context is None:
        return
    path, run_id = context
    try:
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        with sqlite3.connect(path, timeout=2) as db:
            db.execute(
                "CREATE TABLE IF NOT EXISTS events (id INTEGER PRIMARY KEY, run_id TEXT NOT NULL, timestamp TEXT NOT NULL, payload TEXT NOT NULL)"
            )
            db.execute(
                "INSERT INTO events(run_id, timestamp, payload) VALUES (?, ?, ?)",
                (
                    run_id,
                    datetime.now(UTC).isoformat(),
                    json.dumps({"stage": stage, "event": event, **fields}),
                ),
            )
    except (OSError, sqlite3.Error):
        logging.getLogger(__name__).error(
            "diagnostics_write_failed: local attempt metadata could not be saved"
        )


@contextmanager
def recording(path, run_id):
    token = _context.set((path, run_id) if path is not None else None)
    try:
        record("workflow", "started")
        yield
    except BaseException:
        record("workflow", "failed")
        raise
    else:
        record("workflow", "finished")
    finally:
        _context.reset(token)
