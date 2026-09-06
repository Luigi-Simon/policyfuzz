"""Offline gold-assisted assessment, explicitly ineligible for discovery gates.

Only revealed JSON members and a bound recorder result are accepted. The original
policy/run are immutable; gold policy semantics are never substituted. No model
stage or provider is imported or invoked. Publication is one no-replace directory
rename so readers never observe a partial score/provenance pair.
"""

from __future__ import annotations

import ctypes
import errno
import hashlib
import json
import os
import re
import shutil
import sys
import tempfile
from pathlib import Path

from app.core.artifacts import semantic_payload_projection
from app.core.hashing import canonical_sha256
from app.domain.models import (
    AnalyzeFindingsRequest,
    BenchmarkCorrectedSemantics,
    BenchmarkManifest,
    BenchmarkSourceLabels,
    EvaluatePolicyRequest,
    EvaluationReport,
    InputHashes,
    PolicyContract,
    PolicyDocument,
    PolicyIR,
    RunRecord,
    ScenarioSuite,
    ScoreBenchmarkRequest,
    SourceSpan,
)
from app.features.evaluation.benchmark import score_benchmark
from app.features.evaluation.engine import (
    ENGINE_VERSION,
    DeterministicEvaluationEngine,
    payload_hash,
)
from app.features.evaluation.findings import DeterministicFindingAnalyzer

_ARTIFACT_MODELS = {
    "source-labels.json": BenchmarkSourceLabels,
    "canonical-policy-ir.json": PolicyIR,
    "confirmed-contract.json": PolicyContract,
    "frozen-suite.json": ScenarioSuite,
    "expected-effects.json": EvaluationReport,
    "defect-manifest.json": BenchmarkManifest,
    "corrected-semantics.json": BenchmarkCorrectedSemantics,
}
# Same source commitment recipe as the frozen application manifest factory. Do not
# import the container here: constructing/configuring a provider is out of scope.
_ENGINE_FILES = (
    "assertions.py",
    "compliance.py",
    "engine.py",
    "errors.py",
    "findings.py",
    "metrics.py",
    "patches.py",
    "predicates.py",
    "regression.py",
    "resolution.py",
    "rule_validation.py",
    "signatures.py",
)


def current_engine_sha256() -> str:
    return canonical_sha256(
        {
            name: Path(__file__).with_name(name).read_text(encoding="utf-8")
            for name in _ENGINE_FILES
        }
    )


def _require(condition: bool, code: str) -> None:
    if not condition:
        raise ValueError(code)


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _no_symlinks(path: Path) -> None:
    absolute = path.absolute()
    _require(
        not any(p.is_symlink() for p in (absolute, *absolute.parents)),
        "ASSESSMENT_PATH_INVALID",
    )


def _read(path: Path, limit: int) -> bytes:
    _no_symlinks(path)
    _require(path.is_file(), "ASSESSMENT_INPUT_INVALID")
    with path.open("rb") as stream:
        data = stream.read(limit + 1)
    _require(len(data) <= limit, "ASSESSMENT_INPUT_TOO_LARGE")
    return data


def _json(data: bytes) -> object:
    def unique(pairs):
        value = {}
        for key, child in pairs:
            _require(key not in value, "ASSESSMENT_DUPLICATE_JSON_KEY")
            value[key] = child
        return value

    def constant(_value):
        raise ValueError("ASSESSMENT_INVALID_JSON_NUMBER")

    return json.loads(
        data.decode("utf-8"), object_pairs_hook=unique, parse_constant=constant
    )


def _source(document: PolicyDocument) -> str:
    offset = 0
    previous = 0
    for page in document.pages:
        _require(
            page.page > previous
            and page.start == offset
            and page.end == offset + len(page.text),
            "ASSESSMENT_SOURCE_OFFSETS",
        )
        offset, previous = page.end, page.page
    text = "".join(page.text for page in document.pages)
    _require(
        0 < len(text) <= 50000
        and _sha(text.encode("utf-8")) == document.document_sha256,
        "ASSESSMENT_SOURCE_HASH",
    )
    return text


def _span(document: PolicyDocument, span: SourceSpan) -> None:
    page = next((p for p in document.pages if p.page == span.page), None)
    _require(
        page is not None and page.start <= span.start < span.end <= page.end,
        "ASSESSMENT_CITATION_OFFSETS",
    )
    _require(
        page.text[span.start - page.start : span.end - page.start] == span.quote
        and _sha(span.quote.encode("utf-8")) == span.quote_sha256,
        "ASSESSMENT_CITATION_HASH",
    )


def _policy_source(policy: PolicyIR, document: PolicyDocument) -> None:
    _require(
        policy.document_sha256 == document.document_sha256
        and policy.kind == "compiled_baseline",
        "ASSESSMENT_POLICY_SOURCE",
    )
    for rule in policy.rules:
        _require(
            rule.provenance.kind == "text_citation", "ASSESSMENT_BASELINE_CITATION"
        )
        _span(document, rule.provenance.span)
    for clause in policy.unsupported_clauses:
        _span(document, clause.span)


def validate_revealed_benchmark(directory: Path, seal: dict) -> dict:
    """Validate all revealed members against their sealed content commitments."""
    hashes = seal.get("artifact_hashes")
    _require(
        isinstance(hashes, dict) and hashes.keys() == _ARTIFACT_MODELS.keys(),
        "ASSESSMENT_SEAL_ARTIFACTS",
    )
    artifacts = {}
    for name, model in _ARTIFACT_MODELS.items():
        raw = _read(directory / name, 2 * 1024 * 1024)
        _json(raw)
        value = model.model_validate_json(raw)
        _require(payload_hash(value) == hashes[name], "ASSESSMENT_SEAL_HASH_MISMATCH")
        artifacts[name] = value
    source = artifacts["source-labels.json"]
    policy = artifacts["canonical-policy-ir.json"]
    contract = artifacts["confirmed-contract.json"]
    suite = artifacts["frozen-suite.json"]
    expected = artifacts["expected-effects.json"]
    manifest = artifacts["defect-manifest.json"]
    corrected = artifacts["corrected-semantics.json"]
    _source(source.document)
    _policy_source(policy, source.document)
    _require(
        policy.review_status == "session_confirmed",
        "ASSESSMENT_GOLD_BASELINE_UNCONFIRMED",
    )
    _require(
        seal.get("source_policy_sha256")
        == policy.document_sha256
        == suite.document_sha256
        == manifest.document_sha256
        == corrected.document_sha256,
        "ASSESSMENT_GOLD_SOURCE_ANCHOR",
    )
    _require(
        payload_hash(contract)
        == suite.policy_contract_sha256
        == manifest.policy_contract_sha256,
        "ASSESSMENT_GOLD_CONTRACT_ANCHOR",
    )
    _require(
        suite.content_sha256 == payload_hash(suite)
        and suite.rule_set_sha256
        == canonical_sha256(semantic_payload_projection(policy)),
        "ASSESSMENT_GOLD_SUITE_ANCHOR",
    )
    _require(
        expected.inputs.policy_sha256
        == corrected.baseline_policy_sha256
        == payload_hash(policy)
        and expected.inputs.contract_sha256 == payload_hash(contract)
        and expected.inputs.suite_sha256 == payload_hash(suite),
        "ASSESSMENT_GOLD_REPORT_ANCHOR",
    )
    _require(
        manifest.engine_version
        == suite.engine_version
        == expected.engine_version
        == ENGINE_VERSION,
        "ASSESSMENT_GOLD_ENGINE_VERSION",
    )
    _require(
        manifest.required_dimensions == contract.required_dimensions,
        "ASSESSMENT_GOLD_DIMENSIONS",
    )
    for name, count in (
        ("rule_count", len(policy.rules)),
        ("scenario_count", len(suite.scenarios)),
        ("defect_count", len(manifest.defects)),
    ):
        _require(
            type(seal.get(name)) is int and seal[name] == count,
            "ASSESSMENT_SEAL_COUNTS",
        )
    _require(
        seal.get("defect_ids_sha256")
        == canonical_sha256(sorted(d.defect_id for d in manifest.defects)),
        "ASSESSMENT_SEAL_DEFECT_IDS",
    )
    rules = {r.rule_id for r in policy.rules}
    labelled = set()
    for label in source.labels:
        _span(source.document, label.source_span)
        _require(set(label.rule_ids) <= rules, "ASSESSMENT_SOURCE_LABELS")
        labelled.update(label.rule_ids)
    _require(labelled == rules, "ASSESSMENT_SOURCE_LABELS")
    frozen = {s.scenario_id: s for s in suite.scenarios}
    _require(
        bool(manifest.gold_scenarios)
        and len({s.scenario_id for s in manifest.gold_scenarios})
        == len(manifest.gold_scenarios),
        "ASSESSMENT_GOLD_CASE_IDS",
    )
    for gold in manifest.gold_scenarios:
        original = frozen.get(gold.scenario_id)
        _require(
            original is not None
            and original.facts == gold.facts
            and tuple(a for a in original.assertions if a.origin == "gold")
            == gold.assertions,
            "ASSESSMENT_GOLD_CASE_MISMATCH",
        )
    for defect in manifest.defects:
        for span in defect.source_spans:
            _span(source.document, span)
    return artifacts


def _rename_no_replace(source: Path, target: Path) -> None:
    """Atomic, exclusive directory publication; fail closed without OS support."""
    libc = ctypes.CDLL(None, use_errno=True)
    if sys.platform.startswith("linux") and hasattr(libc, "renameat2"):
        rename = libc.renameat2
        rename.argtypes = [
            ctypes.c_int,
            ctypes.c_char_p,
            ctypes.c_int,
            ctypes.c_char_p,
            ctypes.c_uint,
        ]
        rename.restype = ctypes.c_int
        result = rename(-100, os.fsencode(source), -100, os.fsencode(target), 1)
    elif sys.platform == "darwin" and hasattr(libc, "renamex_np"):
        rename = libc.renamex_np
        rename.argtypes = [ctypes.c_char_p, ctypes.c_char_p, ctypes.c_uint]
        rename.restype = ctypes.c_int
        result = rename(os.fsencode(source), os.fsencode(target), 4)
    else:
        raise OSError(
            errno.ENOTSUP, "atomic exclusive directory publication unsupported"
        )
    if result != 0:
        error = ctypes.get_errno()
        raise OSError(error, os.strerror(error))


def _publish_pair(output: Path, score: dict, provenance: dict) -> None:
    _no_symlinks(output)
    _require(not output.exists(), "ASSESSMENT_OUTPUT_EXISTS")
    parent = output.parent.resolve(strict=True)
    temporary = Path(tempfile.mkdtemp(dir=parent, prefix=f".{output.name}."))
    try:
        for name, value in (("score.json", score), ("provenance.json", provenance)):
            data = (
                json.dumps(
                    value, ensure_ascii=False, sort_keys=True, indent=2, allow_nan=False
                )
                + "\n"
            ).encode("utf-8")
            with (temporary / name).open("xb") as stream:
                stream.write(data)
                stream.flush()
                os.fsync(stream.fileno())
        directory = os.open(temporary, os.O_RDONLY)
        try:
            os.fsync(directory)
        finally:
            os.close(directory)
        _rename_no_replace(temporary, parent / output.name)
        directory = os.open(parent, os.O_RDONLY)
        try:
            os.fsync(directory)
        finally:
            os.close(directory)
    finally:
        if temporary.exists():
            shutil.rmtree(temporary)


def assess_gold(
    *,
    run_result: Path,
    run_metadata: Path,
    benchmark_dir: Path,
    schema_seal: Path,
    output: Path,
) -> None:
    """Publish a new assessment; never score original discovery or mutate its inputs."""
    from app.features.evaluation.benchmark_cli import _select_record_evidence

    raw = _read(run_result, 8 * 1024 * 1024)
    _json(raw)
    record = RunRecord.model_validate_json(raw)
    metadata_bytes = _read(run_metadata, 65536)
    metadata = _json(metadata_bytes)
    seal_bytes = _read(schema_seal, 65536)
    seal = _json(seal_bytes)
    _require(
        isinstance(metadata, dict) and isinstance(seal, dict),
        "ASSESSMENT_METADATA_INVALID",
    )
    _require(
        metadata.get("status") == "recorded"
        and metadata.get("error_code") is None
        and metadata.get("run_id") == record.run_id
        and metadata.get("result_bytes_sha256") == _sha(raw)
        and metadata.get("result_sha256") == payload_hash(record),
        "ASSESSMENT_RAW_RECORD_BINDING",
    )
    candidate = metadata.get("candidate")
    input_hashes = metadata.get("input_bytes_sha256")
    runtime = metadata.get("runtime")
    _require(
        isinstance(candidate, dict)
        and isinstance(input_hashes, dict)
        and isinstance(runtime, dict),
        "ASSESSMENT_METADATA_INVALID",
    )
    _require(
        seal.get("schema_version") == "1.0"
        and isinstance(seal.get("archive_sha256"), str)
        and re.fullmatch(r"[0-9a-f]{64}", seal["archive_sha256"]) is not None
        and seal["archive_sha256"] == candidate.get("schema_archive_sha256")
        and seal.get("source_policy_sha256") == candidate.get("source_policy_sha256")
        and _sha(seal_bytes) in input_hashes.values(),
        "ASSESSMENT_RECORDED_SEAL_BINDING",
    )
    engine_hash = current_engine_sha256()
    _require(
        record.manifest.engine_version
        == runtime.get("engine_version")
        == ENGINE_VERSION
        and record.manifest.engine_sha256
        == runtime.get("engine_sha256")
        == engine_hash,
        "ASSESSMENT_ENGINE_CHANGED",
    )
    artifacts = validate_revealed_benchmark(benchmark_dir, seal)
    gold_manifest = artifacts["defect-manifest.json"]
    original_evaluation, original_findings = _select_record_evidence(
        record.model_dump(mode="json"), gold_manifest
    )
    by_hash = {a.artifact_sha256: a.payload for a in record.artifacts}
    policy = by_hash[original_evaluation.inputs.policy_sha256]
    original_contract = by_hash[original_evaluation.inputs.contract_sha256]
    original_suite = by_hash[original_evaluation.inputs.suite_sha256]
    documents = [
        a.payload for a in record.artifacts if a.artifact_type == "policy_document"
    ]
    _require(len(documents) == 1, "ASSESSMENT_RECORDED_SOURCE")
    _require(
        _source(documents[0]) == _source(artifacts["source-labels.json"].document),
        "ASSESSMENT_RECORDED_SOURCE",
    )
    _policy_source(policy, documents[0])
    _require(
        record.stage in {"complete", "completed_no_findings", "completed_no_revision"},
        "ASSESSMENT_RUN_INCOMPLETE",
    )
    replay = DeterministicEvaluationEngine().evaluate(
        EvaluatePolicyRequest(
            policy=policy,
            contract=original_contract,
            suite=original_suite,
            inputs=original_evaluation.inputs,
            engine_version=ENGINE_VERSION,
        )
    )
    _require(replay == original_evaluation, "ASSESSMENT_ORIGINAL_EVALUATION_MISMATCH")
    replay_findings = DeterministicFindingAnalyzer().analyze(
        AnalyzeFindingsRequest(
            policy=policy,
            contract=original_contract,
            suite=original_suite,
            evaluation=replay,
        )
    )
    _require(
        replay_findings == original_findings, "ASSESSMENT_ORIGINAL_FINDINGS_MISMATCH"
    )
    gold_contract = artifacts["confirmed-contract.json"]
    gold_suite = artifacts["frozen-suite.json"]
    derived = ScenarioSuite(
        suite_id=f"post-run-gold-{canonical_sha256((payload_hash(record), payload_hash(gold_suite)))}",
        content_sha256="0" * 64,
        seed=gold_suite.seed,
        document_sha256=policy.document_sha256,
        policy_contract_sha256=payload_hash(gold_contract),
        rule_set_sha256=canonical_sha256(semantic_payload_projection(policy)),
        engine_version=ENGINE_VERSION,
        scenarios=gold_manifest.gold_scenarios,
    )
    derived = derived.model_copy(update={"content_sha256": payload_hash(derived)})
    assessment_manifest = {
        "assessment_kind": "post_run_gold_assessment",
        "headline_gate_eligible": False,
        "source_record_sha256": payload_hash(record),
        "schema_seal_bytes_sha256": _sha(seal_bytes),
        "engine_sha256": engine_hash,
        "derived_suite_sha256": payload_hash(derived),
        "gold_contract_sha256": payload_hash(gold_contract),
        "gold_manifest_sha256": payload_hash(gold_manifest),
    }
    evaluation = DeterministicEvaluationEngine().evaluate(
        EvaluatePolicyRequest(
            policy=policy,
            contract=gold_contract,
            suite=derived,
            engine_version=ENGINE_VERSION,
            inputs=InputHashes(
                policy_sha256=payload_hash(policy),
                contract_sha256=payload_hash(gold_contract),
                suite_sha256=payload_hash(derived),
                engine_sha256=engine_hash,
                run_manifest_sha256=canonical_sha256(assessment_manifest),
            ),
        )
    )
    findings = DeterministicFindingAnalyzer().analyze(
        AnalyzeFindingsRequest(
            policy=policy, contract=gold_contract, suite=derived, evaluation=evaluation
        )
    )
    score = score_benchmark(
        ScoreBenchmarkRequest(
            manifest=gold_manifest, evaluation=evaluation, findings=findings
        )
    )
    score_file = {
        "assessment_kind": "post_run_gold_assessment",
        "headline_gate_eligible": False,
        "first_run_discovery_measured": False,
        "label": "Post-run gold-assisted assessment — not first-run discovery recall",
        "score": score.model_dump(mode="json"),
    }
    provenance = {
        **assessment_manifest,
        "first_run_discovery_measured": False,
        "score_file_payload_sha256": canonical_sha256(score_file),
        "raw_record_bytes_sha256": _sha(raw),
        "recorder_metadata_bytes_sha256": _sha(metadata_bytes),
        "recorded_commit": metadata.get("commit"),
        "recorded_source_sha256": policy.document_sha256,
        "recorded_manifest_sha256": payload_hash(record.manifest),
        "schema_archive_sha256": seal["archive_sha256"],
        "sealed_artifact_hashes": seal["artifact_hashes"],
        "captured_policy_sha256": payload_hash(policy),
        "canonical_gold_policy_sha256": payload_hash(
            artifacts["canonical-policy-ir.json"]
        ),
        "original_contract_sha256": payload_hash(original_contract),
        "original_suite_sha256": payload_hash(original_suite),
        "original_evaluation_sha256": payload_hash(original_evaluation),
        "original_findings_sha256": payload_hash(original_findings),
        "sealed_gold_suite_sha256": payload_hash(gold_suite),
        "assessment_manifest": assessment_manifest,
        "captured_policy": policy.model_dump(mode="json"),
        "gold_contract": gold_contract.model_dump(mode="json"),
        "derived_suite": derived.model_dump(mode="json"),
        "evaluation": evaluation.model_dump(mode="json"),
        "findings": findings.model_dump(mode="json"),
    }
    _publish_pair(output, score_file, provenance)
