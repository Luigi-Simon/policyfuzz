"""Deliberately synthetic benchmark fixtures; never open actual blind material."""

import json

import pytest
from pydantic import ValidationError

from app.domain import models


def test_benchmark_wrappers_are_public_and_reject_invalid_links():
    assert hasattr(models, "BenchmarkSourceLabels")
    span = {"page": 1, "start": 0, "end": 1, "quote": "x", "quote_sha256": "a" * 64}
    with pytest.raises(ValidationError):
        models.BenchmarkSourceLabel.model_validate_json(
            json.dumps(
                {"label_id": "synthetic-label", "source_span": span, "rule_ids": []}
            )
        )
    draft = {
        "description": "Synthetic rule",
        "when": [{"field": "receipt_present", "operator": "eq", "value": True}],
        "effects": [{"dimension": "eligibility", "value": "allow"}],
        "overrides": [{"dimension": "eligibility", "target_rule_id": "missing"}],
    }
    with pytest.raises(ValidationError):
        models.BenchmarkCorrectedSemantics.model_validate_json(
            json.dumps(
                {
                    "document_sha256": "a" * 64,
                    "baseline_policy_sha256": "b" * 64,
                    "rules": [{"rule_id": "rule-1", "revision": 1, "rule": draft}],
                }
            )
        )


def test_validator_has_exact_public_mapping():
    from scripts import validate_and_seal_blind_contracts as validator

    assert {
        name: model.__name__ for name, model in validator.ARCHIVE_MODELS.items()
    } == {
        "source-labels.json": "BenchmarkSourceLabels",
        "canonical-policy-ir.json": "PolicyIR",
        "confirmed-contract.json": "PolicyContract",
        "frozen-suite.json": "ScenarioSuite",
        "expected-effects.json": "EvaluationReport",
        "defect-manifest.json": "BenchmarkManifest",
        "corrected-semantics.json": "BenchmarkCorrectedSemantics",
    }


import hashlib
import subprocess
import sys
from copy import deepcopy
from datetime import UTC, datetime
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile, ZipInfo

NAMES = (
    "source-labels.json",
    "canonical-policy-ir.json",
    "confirmed-contract.json",
    "frozen-suite.json",
    "expected-effects.json",
    "defect-manifest.json",
    "corrected-semantics.json",
)
STAMP = "2026-01-01T00:00:00Z"
H = "a" * 64


def raw_hash(value):
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def model_hash(name, value, semantic=False):
    from scripts.validate_and_seal_blind_contracts import ARCHIVE_MODELS

    from app.core.artifacts import (
        complete_payload_projection,
        semantic_payload_projection,
    )
    from app.core.hashing import canonical_sha256

    model = ARCHIVE_MODELS[name].model_validate_json(json.dumps(value))
    projection = (
        semantic_payload_projection if semantic else complete_payload_projection
    )
    return canonical_sha256(projection(model))


def synthetic_payloads():
    # Human-authored golden semantics: eight receipt-present clauses; 15 gold cases.
    text = "".join(f"Synthetic clause {i}: allow with receipt.\n" for i in range(8))
    source_hash = raw_hash(text)
    spans = []
    position = 0
    for line in text.splitlines(keepends=True):
        spans.append(
            {
                "page": 1,
                "start": position,
                "end": position + len(line),
                "quote": line,
                "quote_sha256": raw_hash(line),
            }
        )
        position += len(line)
    predicate = {"field": "receipt_present", "operator": "eq", "value": True}
    rules = [
        {
            "rule_id": f"rule-{i}",
            "revision": 0,
            "description": f"Synthetic rule {i}",
            "when": [predicate],
            "effects": [{"dimension": "eligibility", "value": "allow"}],
            "provenance": {
                "kind": "text_citation",
                "citation_id": f"citation-{i}",
                "span": span,
            },
        }
        for i, span in enumerate(spans)
    ]
    baseline = {
        "policy_id": "synthetic-policy",
        "document_sha256": source_hash,
        "kind": "compiled_baseline",
        "review_status": "session_confirmed",
        "rules": rules,
    }
    source = {
        "document": {
            "document_id": "synthetic-document",
            "title": "Synthetic fixture only",
            "source_type": "bundled_sample",
            "document_sha256": source_hash,
            "pages": [{"page": 1, "text": text, "start": 0, "end": len(text)}],
        },
        "labels": [
            {"label_id": f"label-{i}", "source_span": span, "rule_ids": [f"rule-{i}"]}
            for i, span in enumerate(spans)
        ],
    }
    invariants = [
        {
            "invariant_id": f"invariant-{i}",
            "description": "Synthetic invariant",
            "when": [predicate],
            "severity": "low",
            "assertion": {
                "assertion_id": f"invariant-assertion-{i}",
                "target_kind": "effect_value",
                "dimension": "eligibility",
                "operator": "eq",
                "expected_value": "allow",
                "origin": "session_confirmed",
                "source_invariant_id": f"invariant-{i}",
            },
        }
        for i in range(3)
    ]
    contract = {
        "contract_id": "synthetic-contract",
        "required_dimensions": ["eligibility"],
        "invariants": invariants,
    }
    contract_hash = model_hash(NAMES[2], contract)
    baseline_hash = model_hash(NAMES[1], baseline)
    semantic_hash = model_hash(NAMES[1], baseline, True)
    scenarios = [
        {
            "scenario_id": f"scenario-{i}",
            "category": "normal",
            "origins": ["gold"],
            "facts": {
                "employee_role": "employee",
                "expense_category": "meal",
                "amount_minor": i,
                "destination_type": "domestic",
                "booking_days_before": 1,
                "receipt_present": True,
                "approval_roles_present": [],
                "prior_same_day_category_spend_minor": 0,
            },
            "target_rule_ids": [f"rule-{i % 8}"],
            "target_invariant_ids": [f"invariant-{i % 3}"],
            "assertions": [
                {
                    "assertion_id": f"assertion-{i}",
                    "target_kind": "effect_value",
                    "dimension": "eligibility",
                    "operator": "eq",
                    "expected_value": "allow",
                    "origin": "gold",
                    "gold_label_id": f"label-{i % 8}",
                }
            ],
            "protected": i == 0,
            "partition": "holdout" if i >= 10 else "visible",
        }
        for i in range(15)
    ]
    suite = {
        "suite_id": "synthetic-suite",
        "content_sha256": H,
        "seed": 1,
        "document_sha256": source_hash,
        "policy_contract_sha256": contract_hash,
        "rule_set_sha256": semantic_hash,
        "engine_version": "synthetic-v1",
        "scenarios": scenarios,
    }
    suite["content_sha256"] = model_hash(NAMES[3], suite)
    results = [
        {
            "scenario_id": item["scenario_id"],
            "verdict": "PASS",
            "assertion_results": [
                {
                    "assertion_id": f"assertion-{i}",
                    "status": "PASS",
                    "actual_value": "allow",
                }
            ],
            "trace": {
                "scenario_id": item["scenario_id"],
                "fired_rule_ids": [f"rule-{j}" for j in range(8)],
                "predicate_results": [],
                "resolved_effects": [
                    {"dimension": "eligibility", "status": "VALUE", "value": "allow"}
                ],
                "compliance_values": [],
                "source_citations": [],
                "trace_sha256": H,
            },
        }
        for i, item in enumerate(scenarios)
    ]
    from app.core.artifacts import complete_payload_projection
    from app.core.hashing import canonical_sha256

    for result in results:
        trace = models.EvaluationTrace.model_validate_json(json.dumps(result["trace"]))
        result["trace"]["trace_sha256"] = canonical_sha256(
            complete_payload_projection(trace)
        )
    report = {
        "report_id": "synthetic-report",
        "inputs": {
            "policy_sha256": baseline_hash,
            "contract_sha256": contract_hash,
            "suite_sha256": suite["content_sha256"],
            "engine_sha256": H,
            "run_manifest_sha256": H,
        },
        "engine_version": "synthetic-v1",
        "results": results,
        "coverage": {},
    }
    defects = [
        {
            "defect_id": f"defect-{i}",
            "finding_type": "structural_gap",
            "dimension": "eligibility",
            "target_ids": [f"rule-{i}"],
            "severity": "low",
            "source_spans": [spans[i]],
            "semantic_signature_sha256": H,
            "permitted_witness_ids": [f"scenario-{i}"],
            "expected_finding_fingerprint_sha256": H,
        }
        for i in range(3)
    ]
    manifest = {
        "benchmark_id": "synthetic-benchmark",
        "document_sha256": source_hash,
        "policy_contract_sha256": contract_hash,
        "engine_version": "synthetic-v1",
        "sealed_at": STAMP,
        "seal_sha256": H,
        "defects": defects,
        "gold_scenarios": scenarios,
        "required_dimensions": ["eligibility"],
    }
    corrected = {
        "document_sha256": source_hash,
        "baseline_policy_sha256": baseline_hash,
        "rules": [
            {
                "rule_id": r["rule_id"],
                "revision": 1,
                "rule": {k: r[k] for k in ("description", "when", "effects")},
            }
            for r in rules
        ],
    }
    return dict(
        zip(
            NAMES,
            (source, baseline, contract, suite, report, manifest, corrected),
            strict=True,
        )
    )


def synthetic_inputs(tmp_path, payloads=None):
    from app.core.hashing import canonical_sha256

    payloads = synthetic_payloads() if payloads is None else payloads
    archive = tmp_path / "synthetic.zip"
    write_archive(archive, payloads)
    seal = tmp_path / "synthetic-source-seal.json"
    ids = [f"defect-{i}" for i in range(3)]
    seal.write_text(
        json.dumps(
            {
                "archive_sha256": H,
                "policy_sha256": payloads[NAMES[0]]["document"]["document_sha256"],
                "manifest_sha256": "b" * 64,
                "defect_ids_sha256": canonical_sha256(ids),
                "defect_count": 3,
                "created_at": STAMP,
                "custodian_role": "Synthetic custodian",
            }
        )
    )
    ids_path = tmp_path / "synthetic-ids.json"
    ids_path.write_text(json.dumps(ids))
    return {
        "archive": archive,
        "source_seal": seal,
        "defect_ids_file": ids_path,
        "output": tmp_path / "result.json",
    }


def write_archive(path, payloads):
    with ZipFile(path, "w", compression=ZIP_DEFLATED) as archive:
        for name, value in payloads.items():
            archive.writestr(name, json.dumps(value))


def run_validator(inputs):
    from scripts.validate_and_seal_blind_contracts import (
        validate_and_seal_blind_contracts,
    )

    return validate_and_seal_blind_contracts(
        **inputs, created_at=datetime(2026, 1, 2, tzinfo=UTC)
    )


def assert_rejected(inputs, expected_code=None):
    from scripts.validate_and_seal_blind_contracts import BlindContractError

    before = {
        key: value.read_bytes() for key, value in inputs.items() if key != "output"
    }
    with pytest.raises(BlindContractError) as error:
        run_validator(inputs)
    assert str(error.value).startswith("BLIND_")
    if expected_code is not None:
        assert str(error.value) == expected_code
    assert "Synthetic" not in str(error.value)
    assert not inputs["output"].exists()
    assert before == {
        key: value.read_bytes() for key, value in inputs.items() if key != "output"
    }


def test_accepts_real_synthetic_zip_and_writes_only_public_ledger(tmp_path):
    inputs = synthetic_inputs(tmp_path)
    result = run_validator(inputs)
    assert set(result) == {
        "schema_version",
        "archive_sha256",
        "artifact_hashes",
        "source_policy_sha256",
        "defect_ids_sha256",
        "rule_count",
        "scenario_count",
        "defect_count",
        "created_at",
        "custodian_role",
    }
    assert set(result["artifact_hashes"]) == set(NAMES)
    assert (
        result["archive_sha256"]
        == hashlib.sha256(inputs["archive"].read_bytes()).hexdigest()
    )
    assert (result["rule_count"], result["scenario_count"], result["defect_count"]) == (
        8,
        15,
        3,
    )
    assert result["custodian_role"] == "Person 5 — Product and demo lead"
    assert json.loads(inputs["output"].read_text()) == result
    assert "Synthetic" not in inputs["output"].read_text()
    for name, payload in synthetic_payloads().items():
        assert result["artifact_hashes"][name] == model_hash(name, payload)


@pytest.mark.parametrize("name", NAMES)
@pytest.mark.parametrize("failure", ["missing", "schema"])
def test_each_member_is_required_and_schema_validated(tmp_path, name, failure):
    payloads = synthetic_payloads()
    inputs = synthetic_inputs(tmp_path, payloads)
    if failure == "missing":
        del payloads[name]
    else:
        payloads[name]["private-unknown-field"] = "Synthetic secret sentinel"
    write_archive(inputs["archive"], payloads)
    assert_rejected(inputs)


@pytest.mark.parametrize(
    "name,path,value",
    [
        (NAMES[0], ("document", "pages", 0, "text"), "Synthetic wrong source"),
        (NAMES[0], ("labels", 0, "source_span", "quote_sha256"), H),
        (NAMES[0], ("labels", 0, "rule_ids"), ["missing"]),
        (NAMES[0], ("labels",), []),
        (
            NAMES[1],
            ("rules", 0, "provenance", "span", "quote"),
            "Synthetic wrong quote",
        ),
        (NAMES[1], ("rules", 0, "provenance", "span", "page"), 2),
        (NAMES[1], ("review_status",), "provisional"),
        (NAMES[1], ("document_sha256",), H),
        (NAMES[3], ("document_sha256",), H),
        (NAMES[3], ("policy_contract_sha256",), H),
        (NAMES[3], ("rule_set_sha256",), H),
        (NAMES[3], ("content_sha256",), H),
        (NAMES[3], ("engine_version",), "other-engine"),
        (NAMES[3], ("scenarios", 0, "protected"), False),
        (NAMES[4], ("inputs", "policy_sha256"), H),
        (NAMES[4], ("inputs", "contract_sha256"), H),
        (NAMES[4], ("inputs", "suite_sha256"), H),
        (NAMES[4], ("engine_version",), "other-engine"),
        (NAMES[4], ("results", 0, "trace", "resolved_effects"), []),
        (
            NAMES[4],
            ("results", 0, "assertion_results", 0, "assertion_id"),
            "fabricated-oracle",
        ),
        (NAMES[4], ("results", 0, "trace", "scenario_id"), "fabricated-scenario"),
        (NAMES[5], ("seal_sha256",), "c" * 64),
        (NAMES[5], ("defects", 0, "source_spans"), []),
        (NAMES[5], ("defects", 0, "semantic_signature_sha256"), None),
        (NAMES[5], ("defects", 0, "expected_finding_fingerprint_sha256"), None),
        (NAMES[5], ("defects", 0, "permitted_witness_ids"), ["missing"]),
        (NAMES[5], ("defects", 0, "partition"), "holdout"),
        (NAMES[5], ("gold_scenarios", 0, "facts", "amount_minor"), 9000),
        (NAMES[6], ("baseline_policy_sha256",), H),
        (NAMES[6], ("document_sha256",), H),
    ],
)
def test_tampered_anchors_citations_and_oracles_fail(tmp_path, name, path, value):
    payloads = synthetic_payloads()
    inputs = synthetic_inputs(tmp_path, payloads)
    target = payloads[name]
    for part in path[:-1]:
        target = target[part]
    target[path[-1]] = value
    write_archive(inputs["archive"], payloads)
    assert_rejected(inputs)


@pytest.mark.parametrize(
    "field,value",
    [
        ("policy_sha256", H),
        ("defect_ids_sha256", H),
        ("archive_sha256", "bad"),
        ("manifest_sha256", "bad"),
        ("defect_count", 2),
        ("created_at", "2026-01-01T00:00:00"),
        ("defect_count", True),
    ],
)
def test_source_seal_is_validated(tmp_path, field, value):
    inputs = synthetic_inputs(tmp_path)
    seal = json.loads(inputs["source_seal"].read_text())
    seal[field] = value
    inputs["source_seal"].write_text(json.dumps(seal))
    assert_rejected(inputs)


@pytest.mark.parametrize(
    "value",
    [
        ["defect-2", "defect-1", "defect-0"],
        ["defect-0"] * 3,
        ["defect-0", "defect-1", "new-defect"],
        ["private invalid"] * 3,
    ],
)
def test_defect_ids_are_sorted_unique_and_seal_bound(tmp_path, value):
    inputs = synthetic_inputs(tmp_path)
    inputs["defect_ids_file"].write_text(json.dumps(value))
    assert_rejected(inputs)


def test_no_overwrite(tmp_path):
    from scripts.validate_and_seal_blind_contracts import BlindContractError

    inputs = synthetic_inputs(tmp_path)
    inputs["output"].write_text("existing sentinel")
    with pytest.raises(BlindContractError, match="BLIND_OUTPUT_EXISTS"):
        run_validator(inputs)
    assert inputs["output"].read_text() == "existing sentinel"


@pytest.mark.parametrize("input_name", ["archive", "defect_ids_file"])
def test_all_private_inputs_must_be_external(tmp_path, input_name):
    from scripts.validate_and_seal_blind_contracts import (
        BlindContractError,
        validate_and_seal_blind_contracts,
    )

    inputs = synthetic_inputs(tmp_path)
    repo = tmp_path / "simulated-repository"
    repo.mkdir()
    private = repo / inputs[input_name].name
    private.write_bytes(inputs[input_name].read_bytes())
    inputs[input_name] = private
    with pytest.raises(BlindContractError, match="BLIND_INPUT_CUSTODY"):
        validate_and_seal_blind_contracts(**inputs, repository_root=repo)
    assert not inputs["output"].exists()


@pytest.mark.parametrize(
    "failure",
    [
        "duplicate",
        "traversal",
        "unexpected",
        "symlink",
        "malformed",
        "duplicate_json",
        "nonfinite",
        "oversize",
    ],
)
def test_archive_security_rejections(tmp_path, failure):
    inputs = synthetic_inputs(tmp_path)
    if failure == "malformed":
        inputs["archive"].write_bytes(b"not a zip Synthetic sentinel")
    elif failure == "oversize":
        with ZipFile(inputs["archive"], "a", compression=ZIP_DEFLATED) as archive:
            archive.writestr("oversize.json", b"x" * (2 * 1024 * 1024 + 1))
    else:
        payloads = synthetic_payloads()
        with ZipFile(inputs["archive"], "w") as archive:
            for name, value in payloads.items():
                encoded = json.dumps(value)
                info = name
                if name == NAMES[0]:
                    if failure == "traversal":
                        info = "../source-labels.json"
                    elif failure == "unexpected":
                        info = "unexpected.json"
                    elif failure == "symlink":
                        info = ZipInfo(name)
                        info.create_system = 3
                        info.external_attr = 0o120777 << 16
                    elif failure == "duplicate_json":
                        encoded = '{"document":{},"document":{}}'
                    elif failure == "nonfinite":
                        encoded = '{"document": NaN}'
                archive.writestr(info, encoded)
            if failure == "duplicate":
                with pytest.warns(UserWarning):
                    archive.writestr(NAMES[0], "{}")
    assert_rejected(inputs)


def test_cli_failure_never_echoes_private_contents_or_paths(tmp_path):
    inputs = synthetic_inputs(tmp_path)
    inputs["source_seal"].write_text("Synthetic highly private sentinel")
    script = (
        Path(__file__).resolve().parents[3]
        / "scripts"
        / "validate_and_seal_blind_contracts.py"
    )
    command = [sys.executable, str(script)]
    for key, value in inputs.items():
        command.extend(["--" + key.replace("_", "-"), str(value)])
    result = subprocess.run(command, capture_output=True, text=True, check=False)
    assert result.returncode == 2
    assert result.stdout == ""
    assert result.stderr.startswith("BLIND_")
    assert "Synthetic" not in result.stderr
    assert str(tmp_path) not in result.stderr
    assert "Traceback" not in result.stderr
    assert not inputs["output"].exists()


@pytest.mark.parametrize(
    "failure", ["encrypted", "exact_oversize", "expanded_total", "nul_name"]
)
def test_zip_bounds_and_hidden_entry_metadata(tmp_path, failure):
    inputs = synthetic_inputs(tmp_path)
    if failure == "encrypted":
        data = bytearray(inputs["archive"].read_bytes())
        position = 0
        while True:
            position = data.find(b"PK\x01\x02", position)
            if position == -1:
                break
            data[position + 8] |= 1
            position += 4
        inputs["archive"].write_bytes(data)
    elif failure == "nul_name":
        with ZipFile(inputs["archive"], "w") as archive:
            for name, value in synthetic_payloads().items():
                archive.writestr(
                    name + ("Xprivate" if name == NAMES[0] else ""), json.dumps(value)
                )
        inputs["archive"].write_bytes(
            inputs["archive"].read_bytes().replace(b".jsonXprivate", b".json\0private")
        )
    else:
        with ZipFile(inputs["archive"], "w", compression=ZIP_DEFLATED) as archive:
            for name, value in synthetic_payloads().items():
                data = json.dumps(value)
                if failure == "exact_oversize" and name == NAMES[0]:
                    data += " " * (2 * 1024 * 1024)
                elif failure == "expanded_total":
                    data += " " * (1300 * 1024)
                archive.writestr(name, data)
    assert_rejected(inputs)


def test_fake_effect_oracle_cannot_score_unasserted_frozen_case(tmp_path):
    payloads = synthetic_payloads()
    inputs = synthetic_inputs(tmp_path, payloads)
    payloads[NAMES[3]]["scenarios"][0]["assertions"] = []
    payloads[NAMES[5]]["gold_scenarios"][0]["assertions"] = []
    payloads[NAMES[3]]["content_sha256"] = model_hash(NAMES[3], payloads[NAMES[3]])
    payloads[NAMES[4]]["inputs"]["suite_sha256"] = payloads[NAMES[3]]["content_sha256"]
    write_archive(inputs["archive"], payloads)
    assert_rejected(inputs)


@pytest.mark.parametrize(
    "failure",
    [
        "missing_scenario",
        "extra_scenario",
        "duplicate_assertion",
        "missing_assertion",
        "duplicate_dimension",
    ],
)
def test_report_must_cover_exact_frozen_cases_and_assertions(tmp_path, failure):
    payloads = synthetic_payloads()
    inputs = synthetic_inputs(tmp_path, payloads)
    results = payloads[NAMES[4]]["results"]
    if failure == "missing_scenario":
        results.pop()
    elif failure == "extra_scenario":
        extra = deepcopy(results[0])
        extra["scenario_id"] = extra["trace"]["scenario_id"] = "extra-scenario"
        results.append(extra)
    elif failure == "duplicate_assertion":
        results[0]["assertion_results"] *= 2
    elif failure == "missing_assertion":
        results[0]["assertion_results"] = []
        results[0]["verdict"] = "UNSCORED"
    else:
        results[0]["trace"]["resolved_effects"] *= 2
    write_archive(inputs["archive"], payloads)
    assert_rejected(inputs)


def test_contiguous_multi_page_source_is_accepted(tmp_path):
    payloads = synthetic_payloads()
    document = payloads[NAMES[0]]["document"]
    text = document["pages"][0]["text"]
    split = len(text.splitlines(keepends=True)[0]) * 4
    document["pages"] = [
        {"page": 1, "text": text[:split], "start": 0, "end": split},
        {"page": 2, "text": text[split:], "start": split, "end": len(text)},
    ]
    for i in range(4, 8):
        payloads[NAMES[0]]["labels"][i]["source_span"]["page"] = 2
        payloads[NAMES[1]]["rules"][i]["provenance"]["span"]["page"] = 2
    # Rebind the changed citation payload through the published projections.
    baseline_hash = model_hash(NAMES[1], payloads[NAMES[1]])
    payloads[NAMES[6]]["baseline_policy_sha256"] = baseline_hash
    payloads[NAMES[4]]["inputs"]["policy_sha256"] = baseline_hash
    payloads[NAMES[3]]["rule_set_sha256"] = model_hash(
        NAMES[1], payloads[NAMES[1]], True
    )
    payloads[NAMES[3]]["content_sha256"] = model_hash(NAMES[3], payloads[NAMES[3]])
    payloads[NAMES[4]]["inputs"]["suite_sha256"] = payloads[NAMES[3]]["content_sha256"]
    inputs = synthetic_inputs(tmp_path, payloads)
    assert run_validator(inputs)["scenario_count"] == 15


@pytest.mark.parametrize("failure", ["cycle", "duplicate", "empty", "wrong_dimension"])
def test_corrected_semantics_graph_is_schema_validated(failure):
    value = synthetic_payloads()[NAMES[6]]
    if failure == "cycle":
        for i, target in [(0, "rule-1"), (1, "rule-0")]:
            value["rules"][i]["rule"]["overrides"] = [
                {"dimension": "eligibility", "target_rule_id": target}
            ]
    elif failure == "duplicate":
        value["rules"][1]["rule_id"] = value["rules"][0]["rule_id"]
    elif failure == "empty":
        value["rules"] = []
    else:
        value["rules"][1]["rule"]["effects"] = [
            {"dimension": "claim_cap_minor", "value": 100}
        ]
        value["rules"][0]["rule"]["overrides"] = [
            {"dimension": "eligibility", "target_rule_id": "rule-1"}
        ]
    with pytest.raises(ValidationError):
        models.BenchmarkCorrectedSemantics.model_validate_json(json.dumps(value))


def rebind_payloads(payloads):
    baseline_hash = model_hash(NAMES[1], payloads[NAMES[1]])
    payloads[NAMES[6]]["baseline_policy_sha256"] = baseline_hash
    payloads[NAMES[4]]["inputs"]["policy_sha256"] = baseline_hash
    payloads[NAMES[3]]["rule_set_sha256"] = model_hash(
        NAMES[1], payloads[NAMES[1]], True
    )
    payloads[NAMES[3]]["content_sha256"] = model_hash(NAMES[3], payloads[NAMES[3]])
    payloads[NAMES[4]]["inputs"]["suite_sha256"] = payloads[NAMES[3]]["content_sha256"]


def test_unsupported_source_clauses_require_labels_and_exact_citations(tmp_path):
    payloads = synthetic_payloads()
    span = deepcopy(payloads[NAMES[0]]["labels"][0]["source_span"])
    payloads[NAMES[1]]["unsupported_clauses"] = [
        {
            "clause_id": "unsupported-1",
            "span": span,
            "reason_code": "ambiguous_language",
            "affected_dimensions": ["eligibility"],
            "review_status": "session_confirmed",
        }
    ]
    payloads[NAMES[0]]["labels"].append(
        {
            "label_id": "unsupported-label",
            "source_span": span,
            "rule_ids": [],
            "unsupported_clause_id": "unsupported-1",
        }
    )
    rebind_payloads(payloads)
    inputs = synthetic_inputs(tmp_path, payloads)
    assert run_validator(inputs)["rule_count"] == 8
    inputs["output"].unlink()
    payloads[NAMES[0]]["labels"].pop()
    write_archive(inputs["archive"], payloads)
    assert_rejected(inputs)


def test_unprotected_suite_fails_even_with_recomputed_anchors(tmp_path):
    payloads = synthetic_payloads()
    payloads[NAMES[3]]["scenarios"][0]["protected"] = False
    payloads[NAMES[5]]["gold_scenarios"][0]["protected"] = False
    rebind_payloads(payloads)
    assert_rejected(synthetic_inputs(tmp_path, payloads))


@pytest.mark.parametrize("rule_count", [7, 11])
def test_baseline_requires_eight_to_ten_rules(tmp_path, rule_count):
    payloads = synthetic_payloads()
    if rule_count == 7:
        payloads[NAMES[1]]["rules"].pop()
    else:
        for i in range(8, 11):
            rule = deepcopy(payloads[NAMES[1]]["rules"][0])
            rule["rule_id"] = f"rule-{i}"
            payloads[NAMES[1]]["rules"].append(rule)
    rebind_payloads(payloads)
    assert_rejected(synthetic_inputs(tmp_path, payloads))


def test_cli_argument_errors_are_safe(capsys):
    from scripts.validate_and_seal_blind_contracts import main

    with pytest.raises(SystemExit) as error:
        main(["--Synthetic-private-argument"])
    assert error.value.code == 2
    captured = capsys.readouterr()
    assert captured.out == ""
    assert captured.err == "BLIND_CLI_ARGUMENTS\n"


def test_gate_a2_accepts_public_source_seal_in_repository(tmp_path):
    from scripts.validate_and_seal_blind_contracts import (
        validate_and_seal_blind_contracts,
    )

    inputs = synthetic_inputs(tmp_path)
    repo = tmp_path / "synthetic-repository"
    public_seal = repo / "submission" / "evidence" / "blind-seal.json"
    public_seal.parent.mkdir(parents=True)
    public_seal.write_bytes(inputs["source_seal"].read_bytes())
    inputs["source_seal"] = public_seal
    before = {key: path.read_bytes() for key, path in inputs.items() if key != "output"}
    ledger = validate_and_seal_blind_contracts(**inputs, repository_root=repo)
    assert ledger["scenario_count"] == 15
    assert json.loads(inputs["output"].read_text()) == ledger
    assert before == {
        key: path.read_bytes() for key, path in inputs.items() if key != "output"
    }


@pytest.mark.parametrize("tamper", ["digest", "content"])
def test_embedded_trace_hash_rejects_tampering_without_mutation(tmp_path, tamper):
    payloads = synthetic_payloads()
    inputs = synthetic_inputs(tmp_path, payloads)
    trace = payloads[NAMES[4]]["results"][0]["trace"]
    if tamper == "digest":
        trace["trace_sha256"] = "f" * 64
    else:
        trace["resolved_effects"][0]["value"] = "deny"
    write_archive(inputs["archive"], payloads)
    assert_rejected(inputs, expected_code="BLIND_TRACE_HASH")
