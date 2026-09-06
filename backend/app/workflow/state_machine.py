"""Explicit finite-state transitions for a bounded PolicyFuzz run."""

from app.domain.models import ArtifactRef, RunAction, RunEvent, RunStage

from .errors import InvalidRunStateError
from .types import Clock, StoredRun

_DELETE_ONLY: tuple[RunAction, ...] = ("delete_run",)
_ACTIONS: dict[RunStage, tuple[RunAction, ...]] = {
    "awaiting_contract": ("confirm_contract", "delete_run"),
    "awaiting_finding_review": ("select_findings", "delete_run"),
    "awaiting_revision_confirmation": ("confirm_revision", "delete_run"),
}

_TRANSITIONS: dict[RunStage, frozenset[RunStage]] = {
    "queued": frozenset({"ingesting", "failed"}),
    "ingesting": frozenset({"extracting", "failed"}),
    "extracting": frozenset({"awaiting_contract", "failed"}),
    "awaiting_contract": frozenset(
        {"generating_initial_tests", "contract_rejected", "failed"}
    ),
    "generating_initial_tests": frozenset({"provisional_execution", "failed"}),
    "provisional_execution": frozenset(
        {"targeting_coverage", "freezing_suite", "coverage_limit_exceeded", "failed"}
    ),
    "targeting_coverage": frozenset(
        {"freezing_suite", "coverage_limit_exceeded", "failed"}
    ),
    "freezing_suite": frozenset({"baseline_execution", "failed"}),
    "baseline_execution": frozenset({"analyzing", "failed"}),
    "analyzing": frozenset(
        {"awaiting_finding_review", "completed_no_findings", "failed"}
    ),
    "awaiting_finding_review": frozenset(
        {"drafting_revision", "completed_no_revision", "failed"}
    ),
    "drafting_revision": frozenset({"awaiting_revision_confirmation", "failed"}),
    "awaiting_revision_confirmation": frozenset(
        {"applying_revision", "revision_rejected", "failed"}
    ),
    "applying_revision": frozenset({"retesting", "failed"}),
    "retesting": frozenset({"complete", "failed"}),
    "complete": frozenset(),
    "completed_no_findings": frozenset(),
    "completed_no_revision": frozenset(),
    "contract_rejected": frozenset(),
    "revision_rejected": frozenset(),
    "coverage_limit_exceeded": frozenset(),
    "failed": frozenset(),
}

_EVENT_SUMMARIES: dict[RunStage, str] = {
    "queued": "Run queued.",
    "ingesting": "Policy ingestion started.",
    "extracting": "Policy extraction started.",
    "awaiting_contract": "Review the policy contract and invariant severities.",
    "generating_initial_tests": "Initial test generation started.",
    "provisional_execution": "Provisional suite execution started.",
    "targeting_coverage": "Targeted coverage pass started.",
    "freezing_suite": "Scenario suite freezing started.",
    "baseline_execution": "Baseline execution started.",
    "analyzing": "Finding analysis started.",
    "awaiting_finding_review": "Findings are ready for review.",
    "drafting_revision": "Revision drafting started.",
    "awaiting_revision_confirmation": "Revision is ready for review.",
    "applying_revision": "Revision application started.",
    "retesting": "Revision retest started.",
    "complete": "Run completed.",
    "completed_no_findings": "Run completed with no reviewable findings.",
    "completed_no_revision": "Run completed without a revision.",
    "contract_rejected": "Policy contract was rejected.",
    "revision_rejected": "Revision was rejected.",
    "coverage_limit_exceeded": "Run stopped at the coverage limit.",
    "failed": "Run failed.",
}


def allowed_actions(stage: RunStage) -> tuple[RunAction, ...]:
    """Return the commands exposed at a stage, always including deletion."""

    return _ACTIONS.get(stage, _DELETE_ONLY)


def stage_summary(stage: RunStage) -> str:
    """Return the fixed public summary describing entry into a stage."""

    return _EVENT_SUMMARIES[stage]


def transition_to(
    record: StoredRun,
    stage: RunStage,
    *,
    clock: Clock,
    artifact: ArtifactRef | None = None,
) -> StoredRun:
    """Advance one legal edge and append its fixed, display-safe event."""

    if stage not in _TRANSITIONS[record.stage]:
        raise InvalidRunStateError(
            current_stage=record.stage,
            allowed_actions=allowed_actions(record.stage),
        )
    event = RunEvent(
        timestamp=clock.wall_now(),
        stage=stage,
        action_summary=stage_summary(stage),
        artifact=artifact,
    )
    return StoredRun.model_validate(
        record.model_dump(mode="python")
        | {"stage": stage, "events": (*record.events, event)}
    )
