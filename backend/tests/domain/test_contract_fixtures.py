"""Canonical synthetic completed-view evidence and byte-level drift protection."""

import json
import os
import subprocess
import sys
from hashlib import sha256
from pathlib import Path

from app.core.hashing import canonical_sha256
from app.domain import contract_fixtures as fixtures
from app.domain.models import RunView

BACKEND = Path(__file__).resolve().parents[2]


def cli(*args, seed="1"):
    return subprocess.run(
        [sys.executable, "-m", "app.domain.contract_fixtures", *map(str, args)],
        cwd=BACKEND,
        env={**os.environ, "PYTHONHASHSEED": seed},
        capture_output=True,
        text=True,
        check=False,
    )


def test_fixture_is_real_completed_run_view_with_every_public_section():
    view = fixtures.build_completed_run_view()
    assert isinstance(view, RunView)
    assert RunView.model_validate_json(fixtures.completed_fixture_json()) == view
    assert view.stage == view.terminal_status == "complete"
    assert view.mode == "cached"
    assert view.pending_confirmation is None and view.error is None
    assert view.allowed_actions == ("delete_run",)
    assert view.decision_at.isoformat() == "2026-09-04T12:00:00+00:00"
    for field in (
        "events",
        "artifacts",
        "findings",
        "unsupported_clauses",
        "rejections",
        "traces",
    ):
        assert getattr(view, field), field
    assert "SYNTHETIC HACKATHON SAMPLE" in fixtures.completed_fixture_json()
    assert view.coverage.scenario_count == view.baseline_metrics.scenario_count == 6
    assert view.coverage.covered_rules == view.coverage.total_rules > 0
    assert view.coverage.covered_invariants == view.coverage.total_invariants >= 3
    assert {trace.phase for trace in view.traces} == {"baseline", "revised"}
    assert {trace.partition for trace in view.traces} == {"visible"}
    assert view.holdout_evidence.partition == "holdout"
    assert view.holdout_evidence.scenario_count == 1


def test_fixture_counts_transitions_gates_and_input_anchors_are_consistent():
    view = fixtures.build_completed_run_view()
    comparison = view.comparison_metrics
    assert view.baseline_metrics == comparison.baseline
    for metrics in (comparison.baseline, comparison.revised):
        counts = metrics.effect_states.model_dump(exclude={"schema_version"})
        assert set(counts) == {
            "VALUE",
            "GAP",
            "NOT_APPLICABLE",
            "CONFLICT",
            "INCONCLUSIVE",
            "ERROR",
        }
        assert all(value > 0 for value in counts.values())
        assert sum(counts.values()) == metrics.scenario_count * 5
    transition_counts = comparison.assertion_transition_counts.model_dump(
        exclude={"schema_version"}
    )
    assert set(transition_counts) == {
        "pass_to_pass",
        "fail_to_pass",
        "pass_to_fail",
        "fail_to_fail",
        "inconclusive_or_error",
    }
    assert all(value > 0 for value in transition_counts.values())
    assert sum(transition_counts.values()) == 5
    report = comparison.acceptance
    count = report.counts
    gates = {
        "suite_hash_matches": report.baseline_inputs.suite_sha256
        == report.revised_inputs.suite_sha256,
        "all_target_findings_fixed": count.fixed_target_findings
        == count.target_findings,
        "zero_new_failures_outside_targets": count.new_failures_outside_targets == 0,
        "zero_protected_regressions": count.protected_regressions == 0,
        "no_increase_in_gap_conflict_inconclusive_or_error": count.revised_gap_conflict_inconclusive_or_error
        <= count.baseline_gap_conflict_inconclusive_or_error,
        "unrelated_rules_unchanged": count.unrelated_rule_changes == 0,
        "holdout_not_worse": count.holdout_regressions == 0,
    }
    for name, value in gates.items():
        assert getattr(report, name) == value
    assert (
        comparison.patch_accepted
        == report.patch_accepted
        == all(gates.values())
        is False
    )
    assert comparison.protected_regressions == count.protected_regressions == 1
    assert (
        comparison.new_failures_outside_targets
        == count.new_failures_outside_targets
        == 1
    )
    for name in (
        "suite_sha256",
        "engine_sha256",
        "contract_sha256",
        "run_manifest_sha256",
    ):
        assert getattr(report.baseline_inputs, name) == getattr(
            report.revised_inputs, name
        )
    assert report.baseline_inputs.policy_sha256 != report.revised_inputs.policy_sha256
    assert report.baseline_inputs == fixtures.fixture_input_hashes("baseline")
    assert report.revised_inputs == fixtures.fixture_input_hashes("revised")
    assert (
        fixtures.SOURCE_SHA256
        == sha256(fixtures.SYNTHETIC_SOURCE.encode("utf-8")).hexdigest()
    )
    assert report.baseline_inputs.suite_sha256 == canonical_sha256(
        fixtures.SYNTHETIC_SUITE_ANCHOR
    )
    assert report.baseline_inputs.engine_sha256 == canonical_sha256(
        fixtures.SYNTHETIC_ENGINE_ANCHOR
    )
    for phase, metrics in (
        ("baseline", comparison.baseline),
        ("revised", comparison.revised),
    ):
        visible = [
            result.status
            for trace in view.traces
            if trace.phase == phase
            for result in trace.resolved_effects
        ]
        holdout = getattr(view.holdout_evidence, f"{phase}_effect_states")
        for state, value in metrics.effect_states.model_dump(
            exclude={"schema_version"}
        ).items():
            assert visible.count(state) + getattr(holdout, state) == value


def test_every_fixture_citation_is_an_exact_synthetic_source_slice_and_digest():
    data = json.loads(fixtures.completed_fixture_json())
    spans = []

    def walk(value):
        if isinstance(value, dict):
            if "quote_sha256" in value:
                spans.append(value)
            for child in value.values():
                walk(child)
        elif isinstance(value, list):
            for child in value:
                walk(child)

    walk(data)
    assert spans
    for span in spans:
        quote = fixtures.SYNTHETIC_SOURCE[span["start"] : span["end"]]
        assert span["page"] == 1
        assert span["quote"] == quote
        assert span["quote_sha256"] == sha256(quote.encode("utf-8")).hexdigest()
    for trace in fixtures.build_completed_run_view().traces:
        assert trace.trace_sha256 == canonical_sha256(
            trace.model_dump(mode="python", exclude={"trace_sha256"})
        )


def test_fixture_bytes_are_identical_across_processes_and_check_is_nonmutating(
    tmp_path,
):
    first, second = tmp_path / "first.json", tmp_path / "second.json"
    assert cli("--output", first, seed="1").returncode == 0
    assert cli("--output", second, seed="932").returncode == 0
    assert first.read_bytes() == second.read_bytes()
    assert cli("--check", first).returncode == 0
    before = first.stat().st_mtime_ns
    assert cli("--check", first).returncode == 0
    assert first.stat().st_mtime_ns == before
    first.write_text("{}\n")
    assert cli("--check", first).returncode != 0
    assert first.read_text() == "{}\n"
    first.unlink()
    assert cli("--check", first).returncode != 0
    assert not first.exists()


def test_fixture_privacy_graph_contains_only_aggregate_acceptance_evidence():
    schema = RunView.model_json_schema()
    assert (
        not {
            "AssertionTransition",
            "RegressionReport",
            "BenchmarkManifest",
            "Scenario",
            "ScenarioFacts",
            "RunManifest",
            "PolicyDocument",
        }
        & schema["$defs"].keys()
    )
    comparison = fixtures.build_completed_run_view().comparison_metrics.model_dump()
    serialized = json.dumps(comparison)
    for key in (
        "assertion_id",
        "gold_label_id",
        "scenario_id",
        "prompt",
        "assertion_transitions",
    ):
        assert f'"{key}"' not in serialized


def test_fixture_artifact_digest_and_coverage_match_displayed_evidence():
    view = fixtures.build_completed_run_view()
    assert view.artifacts[0].artifact.artifact_sha256 == canonical_sha256(
        view.comparison_metrics.acceptance
    )
    assert view.events[0].artifact == view.artifacts[0].artifact
    fired_rules = {rule_id for trace in view.traces for rule_id in trace.fired_rule_ids}
    assert len(fired_rules) == view.coverage.covered_rules
    for trace in view.traces:
        for result in trace.resolved_effects:
            if result.status == "CONFLICT":
                assert len(result.applicable_rule_ids) >= 2


def test_committed_completed_fixture_matches_builder():
    target = BACKEND.parent / "contracts/fixtures/run-view.completed.json"
    assert target.read_text(encoding="utf-8") == fixtures.completed_fixture_json()
