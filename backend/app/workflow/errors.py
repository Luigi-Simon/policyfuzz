"""Safe typed failures shared by workflow storage and coordination."""

from app.domain.models import PublicError, RunAction, RunStage


class WorkflowError(Exception):
    """A safe public error plus optional action-conflict context."""

    __slots__ = ("allowed_actions", "current_stage", "public_error")
    _token = "workflow_error"

    def __init__(
        self,
        public_error: PublicError,
        *,
        current_stage: RunStage | None = None,
        allowed_actions: tuple[RunAction, ...] = (),
    ) -> None:
        self.public_error = PublicError.model_validate(public_error)
        self.current_stage = current_stage
        self.allowed_actions = tuple(allowed_actions)
        super().__init__(self._token)


class RunNotFoundError(WorkflowError):
    """The requested run is absent, deleted, or expired."""

    _token = "run_not_found"

    def __init__(self) -> None:
        super().__init__(
            PublicError(
                code="RUN_NOT_FOUND",
                message="The run was not found or has expired.",
                retryable=False,
            )
        )


class ConcurrentRunMutationError(WorkflowError):
    """The caller's expected run version is no longer current."""

    _token = "concurrent_run_mutation"

    def __init__(
        self,
        *,
        current_stage: RunStage | None = None,
        allowed_actions: tuple[RunAction, ...] = (),
    ) -> None:
        super().__init__(
            PublicError(
                code="INVALID_STATE",
                message="The run changed before the request completed.",
                retryable=True,
            ),
            current_stage=current_stage,
            allowed_actions=allowed_actions,
        )


class InvalidRunStateError(WorkflowError):
    """A command or transition is not legal in the current stage."""

    _token = "invalid_run_state"

    def __init__(
        self,
        *,
        current_stage: RunStage,
        allowed_actions: tuple[RunAction, ...],
    ) -> None:
        super().__init__(
            PublicError(
                code="INVALID_STATE",
                message="The run cannot perform that action in its current state.",
                retryable=False,
            ),
            current_stage=current_stage,
            allowed_actions=allowed_actions,
        )


class StaleArtifactError(WorkflowError):
    """A command references an artifact that is no longer current."""

    _token = "stale_artifact"

    def __init__(
        self,
        *,
        current_stage: RunStage | None = None,
        allowed_actions: tuple[RunAction, ...] = (),
    ) -> None:
        super().__init__(
            PublicError(
                code="HASH_MISMATCH",
                message="The referenced artifact is no longer current.",
                retryable=False,
            ),
            current_stage=current_stage,
            allowed_actions=allowed_actions,
        )


class InvalidRunCommandError(WorkflowError):
    """A workflow command violates a server-side command invariant."""

    _token = "invalid_run_command"

    def __init__(
        self,
        *,
        current_stage: RunStage | None = None,
        allowed_actions: tuple[RunAction, ...] = (),
    ) -> None:
        super().__init__(
            PublicError(
                code="INVALID_INPUT",
                message="The run command is invalid.",
                retryable=False,
            ),
            current_stage=current_stage,
            allowed_actions=allowed_actions,
        )
