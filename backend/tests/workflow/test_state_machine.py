"""Behavioral coverage for every workflow-state transition."""

from datetime import UTC, datetime, timedelta

import pytest

from app.domain.models import ArtifactRef, GenerationConfig, RunManifest
from app.workflow.errors import InvalidRunStateError
from app.workflow.state_machine import allowed_actions, stage_summary, transition_to
from app.workflow.types import StoredRun

HASH = "a" * 64
STAGES = (
    "queued",
    "ingesting",
    "extracting",
    "awaiting_contract",
    "generating_initial_tests",
    "provisional_execution",
    "targeting_coverage",
    "freezing_suite",
    "baseline_execution",
    "analyzing",
    "awaiting_finding_review",
    "drafting_revision",
    "awaiting_revision_confirmation",
    "applying_revision",
    "retesting",
    "complete",
    "completed_no_findings",
    "completed_no_revision",
    "contract_rejected",
    "revision_rejected",
    "coverage_limit_exceeded",
    "failed",
)
SUCCESSORS = {
    "queued": {"ingesting", "failed"},
    "ingesting": {"extracting", "failed"},
    "extracting": {"awaiting_contract", "failed"},
    "awaiting_contract": {
        "generating_initial_tests",
        "contract_rejected",
        "failed",
    },
    "generating_initial_tests": {"provisional_execution", "failed"},
    "provisional_execution": {
        "targeting_coverage",
        "freezing_suite",
        "coverage_limit_exceeded",
        "failed",
    },
    "targeting_coverage": {"freezing_suite", "coverage_limit_exceeded", "failed"},
    "freezing_suite": {"baseline_execution", "failed"},
    "baseline_execution": {"analyzing", "failed"},
    "analyzing": {"awaiting_finding_review", "completed_no_findings", "failed"},
    "awaiting_finding_review": {"drafting_revision", "completed_no_revision", "failed"},
    "drafting_revision": {"awaiting_revision_confirmation", "failed"},
    "awaiting_revision_confirmation": {
        "applying_revision",
        "revision_rejected",
        "failed",
    },
    "applying_revision": {"retesting", "failed"},
    "retesting": {"complete", "failed"},
    "complete": set(),
    "completed_no_findings": set(),
    "completed_no_revision": set(),
    "contract_rejected": set(),
    "revision_rejected": set(),
    "coverage_limit_exceeded": set(),
    "failed": set(),
}


class FakeClock:
    def wall_now(self) -> datetime:
        return datetime(2026, 9, 6, 0, 1, tzinfo=UTC)

    def monotonic(self) -> float:
        return 0.0


def make_run(stage: str) -> StoredRun:
    now = datetime(2026, 9, 6, tzinfo=UTC)
    return StoredRun(
        run_id="run-1",
        stage=stage,
        manifest=RunManifest(
            manifest_id="manifest-1",
            run_id="run-1",
            engine_version="1.0",
            engine_sha256=HASH,
            prompt_hashes=(),
            provider="fake",
            model_identifier="offline",
            generation_config=GenerationConfig(),
            random_seed=42,
            started_at=now,
            mode="cached",
        ),
        created_at=now,
        expires_at=now + timedelta(hours=1),
    )


@pytest.mark.parametrize(
    ("source", "target"),
    [(source, target) for source in STAGES for target in STAGES],
)
def test_every_stage_pair_is_accepted_only_when_the_workflow_permits_it(
    source: str, target: str
) -> None:
    record = make_run(source)
    if target in SUCCESSORS[source]:
        transitioned = transition_to(record, target, clock=FakeClock())
        assert transitioned.stage == target
        assert transitioned.events[-1].stage == target
    else:
        with pytest.raises(InvalidRunStateError) as exc_info:
            transition_to(record, target, clock=FakeClock())
        assert exc_info.value.current_stage == source
        assert exc_info.value.allowed_actions == allowed_actions(source)


def test_targeting_cycle_is_bounded_in_the_graph_but_can_freeze_or_fail_coverage() -> (
    None
):
    targeting = transition_to(
        make_run("provisional_execution"), "targeting_coverage", clock=FakeClock()
    )
    with pytest.raises(InvalidRunStateError):
        transition_to(targeting, "provisional_execution", clock=FakeClock())
    with pytest.raises(InvalidRunStateError):
        transition_to(targeting, "targeting_coverage", clock=FakeClock())
    assert (
        transition_to(targeting, "freezing_suite", clock=FakeClock()).stage
        == "freezing_suite"
    )
    assert (
        transition_to(targeting, "coverage_limit_exceeded", clock=FakeClock()).stage
        == "coverage_limit_exceeded"
    )


@pytest.mark.parametrize(
    ("stage", "actions"),
    [
        ("awaiting_contract", ("confirm_contract", "delete_run")),
        ("awaiting_finding_review", ("select_findings", "delete_run")),
        ("awaiting_revision_confirmation", ("confirm_revision", "delete_run")),
        ("ingesting", ("delete_run",)),
        ("complete", ("delete_run",)),
        ("failed", ("delete_run",)),
    ],
)
def test_allowed_actions_expose_only_commands_valid_for_the_current_pause(
    stage: str, actions: tuple[str, ...]
) -> None:
    assert allowed_actions(stage) == actions


@pytest.mark.parametrize(
    ("stage", "summary"),
    [
        ("provisional_execution", "Provisional suite execution started."),
        ("baseline_execution", "Baseline execution started."),
        ("analyzing", "Finding analysis started."),
        ("applying_revision", "Revision application started."),
        ("retesting", "Revision retest started."),
    ],
)
def test_work_stage_summaries_describe_entry_without_claiming_completion(
    stage: str, summary: str
) -> None:
    assert stage_summary(stage) == summary


def test_transition_appends_a_fixed_public_event_and_optional_artifact() -> None:
    artifact = ArtifactRef(
        artifact_type="policy_document",
        artifact_sha256=HASH,
        semantic_sha256=HASH,
    )

    result = transition_to(
        make_run("queued"), "ingesting", clock=FakeClock(), artifact=artifact
    )

    event = result.events[-1]
    assert event.timestamp == datetime(2026, 9, 6, 0, 1, tzinfo=UTC)
    assert event.action_summary == "Policy ingestion started."
    assert event.artifact == artifact
    assert event.error_id is None

    extracting = transition_to(result, "extracting", clock=FakeClock())
    awaiting = transition_to(extracting, "awaiting_contract", clock=FakeClock())
    assert (
        awaiting.events[-1].action_summary
        == "Review the policy contract and invariant severities."
    )


@pytest.mark.parametrize(
    ("source", "terminal"),
    [
        ("awaiting_contract", "contract_rejected"),
        ("analyzing", "completed_no_findings"),
        ("awaiting_finding_review", "completed_no_revision"),
        ("awaiting_revision_confirmation", "revision_rejected"),
        ("targeting_coverage", "coverage_limit_exceeded"),
        ("retesting", "complete"),
    ],
)
def test_approved_terminal_outcomes_are_reachable_and_immutable(
    source: str, terminal: str
) -> None:
    stopped = transition_to(make_run(source), terminal, clock=FakeClock())
    for target in STAGES:
        with pytest.raises(InvalidRunStateError):
            transition_to(stopped, target, clock=FakeClock())


@pytest.mark.parametrize("source", STAGES[:15])
def test_every_active_stage_can_fail(source: str) -> None:
    assert (
        transition_to(make_run(source), "failed", clock=FakeClock()).stage == "failed"
    )
