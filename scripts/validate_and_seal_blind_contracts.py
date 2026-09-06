#!/usr/bin/env python3
"""Validate a schema-bound benchmark and exclusively write a public hash ledger.

ARCHIVE_MODELS is the stable seven-member, plain-JSON member-to-model contract.
Source text is the concatenation of page text with contiguous global offsets.
Raw source, quotes, and ZIP bytes use SHA-256; artifact hashes use canonical
complete payload projections, and the rule-set anchor uses the semantic one.
The source seal's archive hash identifies the earlier Gate A1 custody archive,
not this archive. Its manifest byte hash is not a schema-bound manifest hash.

Bounds: ZIP bytes <= 8 MiB; each expanded member <= 2 MiB; total expanded bytes
<= 8 MiB; metadata files <= 64 KiB; source <= 50,000 characters. Members are
read with bounded decompression and never extracted. Only stored and deflated
ZIP entries are accepted. Validation checks schemas, citations, crosslinks,
counts and custody; it executes no evaluator and makes no semantic correctness
or actual performance claim. Private archive and defect-ID paths must be outside
the repository; the public Gate A1 source seal may reside within it.
"""

from __future__ import annotations

import argparse
import hashlib
import io
import json
import os
import re
import stat
import sys
from collections.abc import Sequence
from datetime import UTC, datetime
from pathlib import Path
from types import MappingProxyType
from typing import Literal
from zipfile import ZIP_DEFLATED, ZIP_STORED, BadZipFile, ZipFile
from zlib import error as ZlibError

# Support the documented direct CLI without requiring an editable installation.
_REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
if str(_REPOSITORY_ROOT / "backend") not in sys.path:
    sys.path.insert(0, str(_REPOSITORY_ROOT / "backend"))

from app.core.artifacts import (
    complete_payload_projection,
    semantic_payload_projection,
)
from app.core.hashing import canonical_sha256
from app.domain.models import (
    BenchmarkCorrectedSemantics,
    BenchmarkManifest,
    BenchmarkSourceLabels,
    EvaluationReport,
    PolicyContract,
    PolicyIR,
    ScenarioSuite,
    Sha256,
    SourceSpan,
    StrictModel,
    Timestamp,
)

ARCHIVE_MODELS = MappingProxyType(
    {
        "source-labels.json": BenchmarkSourceLabels,
        "canonical-policy-ir.json": PolicyIR,
        "confirmed-contract.json": PolicyContract,
        "frozen-suite.json": ScenarioSuite,
        "expected-effects.json": EvaluationReport,
        "defect-manifest.json": BenchmarkManifest,
        "corrected-semantics.json": BenchmarkCorrectedSemantics,
    }
)
MAX_ARCHIVE_BYTES = 8 * 1024 * 1024
MAX_MEMBER_BYTES = 2 * 1024 * 1024
MAX_EXPANDED_BYTES = 8 * 1024 * 1024
MAX_METADATA_BYTES = 64 * 1024
CUSTODIAN_ROLE = "Person 5 — Product and demo lead"


class BlindContractError(ValueError):
    """Fixed public error code, without private values or validation details."""


class _SourceSeal(StrictModel):
    archive_sha256: Sha256
    policy_sha256: Sha256
    manifest_sha256: Sha256
    defect_ids_sha256: Sha256
    defect_count: Literal[3]
    created_at: Timestamp
    custodian_role: str


class _SafeParser(argparse.ArgumentParser):
    def error(self, message: str) -> None:
        self.exit(2, "BLIND_CLI_ARGUMENTS\n")


def _require(condition: bool, code: str) -> None:
    if not condition:
        raise BlindContractError(code)


def _strict_json(data: bytes) -> object:
    def unique_keys(pairs: list[tuple[str, object]]) -> dict[str, object]:
        result: dict[str, object] = {}
        for key, value in pairs:
            _require(key not in result, "BLIND_JSON_INVALID")
            result[key] = value
        return result

    def reject_constant(value: str) -> object:
        raise BlindContractError("BLIND_JSON_INVALID")

    return json.loads(
        data.decode("utf-8"),
        object_pairs_hook=unique_keys,
        parse_constant=reject_constant,
    )


def _read_regular(path: Path, limit: int) -> bytes:
    resolved = path.resolve(strict=True)
    _require(resolved.is_file(), "BLIND_INPUT_INVALID")
    with resolved.open("rb") as stream:
        data = stream.read(limit + 1)
    _require(len(data) <= limit, "BLIND_INPUT_TOO_LARGE")
    return data


def _read_external(path: Path, repository_root: Path, limit: int) -> bytes:
    resolved = path.resolve(strict=True)
    _require(
        not resolved.is_relative_to(repository_root.resolve()), "BLIND_INPUT_CUSTODY"
    )
    return _read_regular(resolved, limit)


def _read_models(data: bytes) -> dict[str, StrictModel]:
    with ZipFile(io.BytesIO(data)) as archive:
        entries = archive.infolist()
        names = [entry.filename for entry in entries]
        _require(
            len(names) == 7 and set(names) == set(ARCHIVE_MODELS),
            "BLIND_ARCHIVE_MEMBERS",
        )
        total = 0
        result: dict[str, StrictModel] = {}
        for entry in entries:
            mode = entry.external_attr >> 16
            _require(
                entry.orig_filename == entry.filename
                and not entry.is_dir()
                and not stat.S_ISLNK(mode)
                and stat.S_IFMT(mode) in (0, stat.S_IFREG)
                and not entry.flag_bits & 1
                and entry.compress_type in (ZIP_STORED, ZIP_DEFLATED),
                "BLIND_ARCHIVE_ENTRY",
            )
            _require(
                0 <= entry.file_size <= MAX_MEMBER_BYTES, "BLIND_ARCHIVE_TOO_LARGE"
            )
            total += entry.file_size
            _require(total <= MAX_EXPANDED_BYTES, "BLIND_ARCHIVE_TOO_LARGE")
            with archive.open(entry) as stream:
                payload = stream.read(MAX_MEMBER_BYTES + 1)
            _require(
                len(payload) == entry.file_size and len(payload) <= MAX_MEMBER_BYTES,
                "BLIND_ARCHIVE_TOO_LARGE",
            )
            _strict_json(payload)
            result[entry.filename] = ARCHIVE_MODELS[entry.filename].model_validate_json(
                payload
            )
        return result


def _digest(model: StrictModel) -> str:
    return canonical_sha256(complete_payload_projection(model))


def _validate_links(
    artifacts: dict[str, StrictModel], seal: _SourceSeal, ids: list[str]
) -> tuple[int, int]:
    source = artifacts["source-labels.json"]
    baseline = artifacts["canonical-policy-ir.json"]
    contract = artifacts["confirmed-contract.json"]
    suite = artifacts["frozen-suite.json"]
    report = artifacts["expected-effects.json"]
    manifest = artifacts["defect-manifest.json"]
    corrected = artifacts["corrected-semantics.json"]
    document = source.document
    pages = {page.page: page for page in document.pages}
    offset = 0
    previous_page = 0
    for page in document.pages:
        _require(
            page.page > previous_page
            and page.start == offset
            and page.end == offset + len(page.text),
            "BLIND_SOURCE_OFFSETS",
        )
        offset = page.end
        previous_page = page.page
    text = "".join(page.text for page in document.pages)
    _require(0 < len(text) <= 50_000, "BLIND_SOURCE_LENGTH")
    source_hash = hashlib.sha256(text.encode("utf-8")).hexdigest()
    _require(
        source_hash == seal.policy_sha256 == document.document_sha256,
        "BLIND_SOURCE_HASH",
    )

    def check_span(span: SourceSpan) -> None:
        page = pages.get(span.page)
        _require(
            page is not None and page.start <= span.start < span.end <= page.end,
            "BLIND_CITATION_INVALID",
        )
        _require(
            page.text[span.start - page.start : span.end - page.start] == span.quote
            and hashlib.sha256(span.quote.encode("utf-8")).hexdigest()
            == span.quote_sha256,
            "BLIND_CITATION_INVALID",
        )

    _require(
        baseline.kind == "compiled_baseline"
        and baseline.review_status == "session_confirmed",
        "BLIND_BASELINE_STATUS",
    )
    _require(
        8 <= len(baseline.rules) <= 10
        and len(suite.scenarios) == 15
        and len(manifest.defects) == 3,
        "BLIND_COUNTS",
    )
    _require(
        baseline.document_sha256
        == source_hash
        == suite.document_sha256
        == manifest.document_sha256
        == corrected.document_sha256,
        "BLIND_DOCUMENT_ANCHOR",
    )
    rules = {rule.rule_id: rule for rule in baseline.rules}
    unsupported = {clause.clause_id: clause for clause in baseline.unsupported_clauses}
    _require(
        len(unsupported) == len(baseline.unsupported_clauses), "BLIND_SOURCE_LABELS"
    )
    for rule in baseline.rules:
        check_span(rule.provenance.span)
    for clause in baseline.unsupported_clauses:
        check_span(clause.span)
        _require(clause.review_status == "session_confirmed", "BLIND_BASELINE_STATUS")
    labelled_rules: set[str] = set()
    labelled_clauses: set[str] = set()
    for label in source.labels:
        check_span(label.source_span)
        _require(set(label.rule_ids) <= rules.keys(), "BLIND_SOURCE_LABELS")
        labelled_rules.update(label.rule_ids)
        if label.unsupported_clause_id is not None:
            _require(label.unsupported_clause_id in unsupported, "BLIND_SOURCE_LABELS")
            labelled_clauses.add(label.unsupported_clause_id)
    _require(
        labelled_rules == rules.keys() and labelled_clauses == unsupported.keys(),
        "BLIND_SOURCE_LABELS",
    )
    _require(
        sorted(defect.defect_id for defect in manifest.defects) == ids,
        "BLIND_DEFECT_IDS",
    )
    _require(manifest.seal_sha256 == seal.archive_sha256, "BLIND_SOURCE_SEAL_ANCHOR")
    contract_hash, baseline_hash, suite_hash = (
        _digest(contract),
        _digest(baseline),
        _digest(suite),
    )
    _require(
        suite.policy_contract_sha256
        == manifest.policy_contract_sha256
        == contract_hash,
        "BLIND_CONTRACT_ANCHOR",
    )
    _require(
        suite.rule_set_sha256
        == canonical_sha256(semantic_payload_projection(baseline)),
        "BLIND_RULE_SET_ANCHOR",
    )
    _require(suite.content_sha256 == suite_hash, "BLIND_SUITE_HASH")
    _require(
        corrected.baseline_policy_sha256 == baseline_hash, "BLIND_CORRECTED_ANCHOR"
    )
    _require(
        report.inputs.policy_sha256 == baseline_hash
        and report.inputs.contract_sha256 == contract_hash
        and report.inputs.suite_sha256 == suite_hash,
        "BLIND_REPORT_ANCHOR",
    )
    _require(
        suite.engine_version == manifest.engine_version == report.engine_version,
        "BLIND_ENGINE_ANCHOR",
    )
    _require(
        manifest.required_dimensions == contract.required_dimensions,
        "BLIND_REQUIRED_DIMENSIONS",
    )
    scenarios = {scenario.scenario_id: scenario for scenario in suite.scenarios}
    _require(
        any(
            scenario.protected and scenario.category == "normal"
            for scenario in suite.scenarios
        ),
        "BLIND_PROTECTED_CASE",
    )
    invariants = {item.invariant_id for item in contract.invariants}
    labels = {item.label_id for item in source.labels}
    for scenario in suite.scenarios:
        _require(
            set(scenario.target_rule_ids) <= rules.keys()
            and set(scenario.target_invariant_ids) <= invariants,
            "BLIND_SCENARIO_TARGETS",
        )
        for assertion in scenario.assertions:
            if assertion.origin == "gold":
                _require(assertion.gold_label_id in labels, "BLIND_ASSERTION_SOURCE")
            elif assertion.origin == "session_confirmed":
                _require(
                    assertion.source_invariant_id in invariants,
                    "BLIND_ASSERTION_SOURCE",
                )
    gold = {scenario.scenario_id: scenario for scenario in manifest.gold_scenarios}
    frozen_gold = {
        scenario.scenario_id: scenario
        for scenario in suite.scenarios
        if "gold" in scenario.origins
    }
    _require(
        len(gold) == len(manifest.gold_scenarios) and gold.keys() == frozen_gold.keys(),
        "BLIND_GOLD_SCENARIOS",
    )
    _require(
        all(_digest(gold[key]) == _digest(frozen_gold[key]) for key in gold),
        "BLIND_GOLD_SCENARIOS",
    )
    _require(
        {result.scenario_id for result in report.results} == scenarios.keys(),
        "BLIND_REPORT_SCENARIOS",
    )
    for result in report.results:
        _require(result.trace.trace_sha256 == _digest(result.trace), "BLIND_TRACE_HASH")
        scenario = scenarios[result.scenario_id]
        dimensions = [effect.dimension for effect in result.trace.resolved_effects]
        _require(
            len(set(dimensions)) == len(dimensions)
            and contract.required_dimensions <= set(dimensions),
            "BLIND_REPORT_DIMENSIONS",
        )
        expected = {assertion.assertion_id for assertion in scenario.assertions}
        actual = [assertion.assertion_id for assertion in result.assertion_results]
        _require(
            set(actual) == expected and len(actual) == len(expected),
            "BLIND_REPORT_ASSERTIONS",
        )
        _require(
            result.verdict not in ("PASS", "FAIL") or bool(expected),
            "BLIND_REPORT_ORACLE",
        )
        _require(set(result.trace.fired_rule_ids) <= rules.keys(), "BLIND_TRACE_LINKS")
        for predicate in result.trace.predicate_results:
            _require(
                predicate.rule_id in rules
                and predicate.predicate_index < len(rules[predicate.rule_id].when),
                "BLIND_TRACE_LINKS",
            )
        for effect in result.trace.resolved_effects:
            _require(
                set(effect.applicable_rule_ids) <= rules.keys()
                and set(effect.overridden_rule_ids) <= rules.keys()
                and set(effect.unsupported_clause_ids) <= unsupported.keys(),
                "BLIND_TRACE_LINKS",
            )
        for citation in result.trace.source_citations:
            _require(citation.kind == "text_citation", "BLIND_CITATION_INVALID")
            check_span(citation.span)
    for defect in manifest.defects:
        _require(
            bool(defect.source_spans)
            and defect.semantic_signature_sha256 is not None
            and bool(defect.permitted_witness_ids)
            and bool(defect.target_ids)
            and defect.expected_finding_fingerprint_sha256 is not None,
            "BLIND_DEFECT_METADATA",
        )
        _require(
            len(set(defect.permitted_witness_ids)) == len(defect.permitted_witness_ids),
            "BLIND_DEFECT_METADATA",
        )
        _require(
            set(defect.target_ids) <= rules.keys() | invariants | unsupported.keys(),
            "BLIND_DEFECT_TARGETS",
        )
        for span in defect.source_spans:
            check_span(span)
        for witness_id in defect.permitted_witness_ids:
            _require(
                witness_id in scenarios
                and scenarios[witness_id].partition == defect.partition,
                "BLIND_DEFECT_WITNESSES",
            )
    return len(rules), len(scenarios)


def validate_and_seal_blind_contracts(
    *,
    archive: Path,
    source_seal: Path,
    defect_ids_file: Path,
    output: Path,
    repository_root: Path = _REPOSITORY_ROOT,
    created_at: datetime | None = None,
) -> dict[str, object]:
    """Validate seven external artifacts; exclusively create a public ledger.

    Raises only BlindContractError with fixed safe codes for validation/I/O
    failures. A failed validation never creates a ledger or modifies an input.
    """
    try:
        output = Path(output)
        _require(not os.path.lexists(output), "BLIND_OUTPUT_EXISTS")
        archive_data = _read_external(
            Path(archive), Path(repository_root), MAX_ARCHIVE_BYTES
        )
        seal_data = _read_regular(Path(source_seal), MAX_METADATA_BYTES)
        ids_data = _read_external(
            Path(defect_ids_file), Path(repository_root), MAX_METADATA_BYTES
        )
        seal_value = _strict_json(seal_data)
        _require(
            isinstance(seal_value, dict)
            and type(seal_value.get("defect_count")) is int,
            "BLIND_SOURCE_SEAL_INVALID",
        )
        seal = _SourceSeal.model_validate_json(seal_data)
        ids = _strict_json(ids_data)
        _require(
            isinstance(ids, list)
            and len(ids) == 3
            and all(
                isinstance(item, str)
                and re.fullmatch(r"[a-z0-9]+(?:[-_][a-z0-9]+)*", item)
                for item in ids
            ),
            "BLIND_DEFECT_IDS",
        )
        _require(ids == sorted(set(ids)), "BLIND_DEFECT_IDS")
        ids_hash = canonical_sha256(ids)
        _require(ids_hash == seal.defect_ids_sha256, "BLIND_DEFECT_IDS_HASH")
        artifacts = _read_models(archive_data)
        rule_count, scenario_count = _validate_links(artifacts, seal, ids)
        timestamp = created_at or datetime.now(UTC)
        _require(
            timestamp.tzinfo is not None and timestamp.utcoffset() is not None,
            "BLIND_TIMESTAMP_INVALID",
        )
        ledger: dict[str, object] = {
            "schema_version": "1.0",
            "archive_sha256": hashlib.sha256(archive_data).hexdigest(),
            "artifact_hashes": {
                name: _digest(model) for name, model in artifacts.items()
            },
            "source_policy_sha256": seal.policy_sha256,
            "defect_ids_sha256": ids_hash,
            "rule_count": rule_count,
            "scenario_count": scenario_count,
            "defect_count": 3,
            "created_at": timestamp.astimezone(UTC)
            .replace(microsecond=0)
            .isoformat()
            .replace("+00:00", "Z"),
            "custodian_role": CUSTODIAN_ROLE,
        }
        encoded = (
            json.dumps(ledger, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
        )
        output.parent.mkdir(parents=True, exist_ok=True)
        try:
            with output.open("x", encoding="utf-8", newline="\n") as stream:
                try:
                    stream.write(encoded)
                    stream.flush()
                except OSError:
                    output.unlink(missing_ok=True)
                    raise
        except FileExistsError:
            raise BlindContractError("BLIND_OUTPUT_EXISTS") from None
        return ledger
    except BlindContractError:
        raise
    except (
        ValueError,
        TypeError,
        OSError,
        RuntimeError,
        RecursionError,
        OverflowError,
        KeyError,
        EOFError,
        BadZipFile,
        ZlibError,
    ):
        raise BlindContractError("BLIND_VALIDATION_FAILED") from None


def main(argv: Sequence[str] | None = None) -> int:
    parser = _SafeParser(description=__doc__)
    for name in ("archive", "source-seal", "defect-ids-file", "output"):
        parser.add_argument("--" + name, required=True, type=Path)
    args = parser.parse_args(argv)
    try:
        validate_and_seal_blind_contracts(**vars(args))
    except BlindContractError as error:
        sys.stderr.write(str(error) + "\n")
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
