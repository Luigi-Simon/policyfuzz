"""Filesystem run store. Each run is a folder of JSON artifacts."""

from __future__ import annotations

import json
from pathlib import Path

from app.config import Settings, get_settings
from app.contracts.run import RunRecord


class RunStore:
    def __init__(self, settings: Settings | None = None):
        self.settings = settings or get_settings()
        self.root = self.settings.data_dir / "runs"
        self.root.mkdir(parents=True, exist_ok=True)

    def _dir(self, run_id: str) -> Path:
        return self.root / run_id

    def save(self, record: RunRecord) -> RunRecord:
        folder = self._dir(record.run_id)
        folder.mkdir(parents=True, exist_ok=True)
        payload = record.model_dump(mode="json")
        (folder / "run.json").write_text(
            json.dumps(payload, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        if record.document:
            (folder / "document.json").write_text(
                record.document.model_dump_json(indent=2),
                encoding="utf-8",
            )
        if record.ir:
            (folder / "policy_ir.json").write_text(
                record.ir.model_dump_json(indent=2),
                encoding="utf-8",
            )
        if record.suite:
            (folder / "scenario_suite.json").write_text(
                record.suite.model_dump_json(indent=2),
                encoding="utf-8",
            )
        if record.evaluation:
            (folder / "evaluation.json").write_text(
                record.evaluation.model_dump_json(indent=2),
                encoding="utf-8",
            )
        if record.effectiveness:
            (folder / "effectiveness.json").write_text(
                record.effectiveness.model_dump_json(indent=2),
                encoding="utf-8",
            )
        if record.mirofish:
            (folder / "mirofish.json").write_text(
                record.mirofish.model_dump_json(indent=2),
                encoding="utf-8",
            )
            (folder / record.mirofish.seed_filename).write_text(
                record.mirofish.seed_markdown,
                encoding="utf-8",
            )
            (folder / "mirofish_prompt.txt").write_text(
                record.mirofish.simulation_requirement,
                encoding="utf-8",
            )
        return record

    def get(self, run_id: str) -> RunRecord | None:
        path = self._dir(run_id) / "run.json"
        if not path.exists():
            return None
        return RunRecord.model_validate_json(path.read_text(encoding="utf-8"))

    def list(self, limit: int = 50) -> list[RunRecord]:
        records: list[RunRecord] = []
        for folder in sorted(self.root.iterdir(), reverse=True):
            path = folder / "run.json"
            if path.exists():
                records.append(RunRecord.model_validate_json(path.read_text(encoding="utf-8")))
            if len(records) >= limit:
                break
        return records

    def save_source_bytes(self, run_id: str, filename: str, payload: bytes) -> Path:
        folder = self._dir(run_id)
        folder.mkdir(parents=True, exist_ok=True)
        target = folder / filename
        target.write_bytes(payload)
        return target
