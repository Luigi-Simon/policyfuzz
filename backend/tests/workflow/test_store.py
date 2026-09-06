"""Behavioral tests for private in-memory workflow storage."""

import asyncio
import sys
from datetime import UTC, datetime, timedelta
from math import inf, nan

import pytest

from app.domain.models import (
    CreateRunRequest,
    GenerationConfig,
    PublicError,
    RunManifest,
    RunRecord,
)
from app.workflow.errors import (
    ConcurrentRunMutationError,
    InvalidRunCommandError,
    RunNotFoundError,
    WorkflowError,
)
from app.workflow.store import RunStore
from app.workflow.types import StoredRun

HASH = "a" * 64


class FakeClock:
    def __init__(self) -> None:
        self.wall = datetime(2026, 9, 6, tzinfo=UTC)
        self.tick = 100.0

    def wall_now(self) -> datetime:
        return self.wall

    def monotonic(self) -> float:
        return self.tick


def make_record(clock: FakeClock, **changes: object) -> RunRecord:
    run_id = str(changes.get("run_id", "run-1"))
    values = {
        "run_id": run_id,
        "stage": "queued",
        "manifest": RunManifest(
            manifest_id="manifest-1",
            run_id=run_id,
            engine_version="1.0",
            engine_sha256=HASH,
            prompt_hashes=(),
            provider="fake",
            model_identifier="offline",
            generation_config=GenerationConfig(),
            random_seed=42,
            started_at=clock.wall,
            mode="cached",
        ),
        "created_at": clock.wall,
        "expires_at": clock.wall + timedelta(seconds=1),
    }
    return RunRecord(**(values | changes))


def test_workflow_error_keeps_public_context_but_never_places_it_in_exception_repr() -> (
    None
):
    public_error = PublicError(
        code="INTERNAL_ERROR",
        message="Safe message with secret-marker-for-test",
        error_id="safe-error-id",
    )

    error = WorkflowError(
        public_error,
        current_stage="awaiting_contract",
        allowed_actions=("confirm_contract", "delete_run"),
    )

    assert error.public_error == public_error
    assert error.current_stage == "awaiting_contract"
    assert error.allowed_actions == ("confirm_contract", "delete_run")
    assert str(error) == "workflow_error"
    assert "secret-marker-for-test" not in repr(error)


@pytest.mark.asyncio
async def test_create_assigns_exact_wall_expiry_but_expiration_is_monotonic() -> None:
    clock = FakeClock()
    store = RunStore(clock)

    created = await store.create(make_record(clock))
    assert created.created_at == datetime(2026, 9, 6, tzinfo=UTC)
    assert created.expires_at == datetime(2026, 9, 6, 1, tzinfo=UTC)

    clock.wall += timedelta(days=30)
    clock.tick = 3699.999
    assert (await store.get(created.run_id)).run_id == created.run_id

    clock.wall -= timedelta(days=60)
    clock.tick = 3700.0
    with pytest.raises(RunNotFoundError):
        await store.get(created.run_id)

    # Expiry removes the private entry, so a fresh run may claim the ID.
    replacement = await store.create(make_record(clock))
    assert replacement.run_id == created.run_id


@pytest.mark.asyncio
async def test_create_rejects_duplicate_live_id() -> None:
    clock = FakeClock()
    store = RunStore(clock)
    await store.create(make_record(clock))

    with pytest.raises(InvalidRunCommandError):
        await store.create(make_record(clock))


@pytest.mark.asyncio
async def test_create_and_get_return_independent_revalidated_deep_snapshots() -> None:
    clock = FakeClock()
    request = CreateRunRequest(
        source_type="pasted_text",
        title="Synthetic policy",
        text="Non-confidential synthetic policy",
        non_confidential_confirmed=True,
    )
    incoming = StoredRun(**make_record(clock).model_dump(), source_request=request)
    store = RunStore(clock)

    created = await store.create(incoming)
    created.manifest.generation_config.__dict__["temperature_milli"] = 999
    created.__dict__["source_request"] = None
    incoming.manifest.__dict__["provider"] = "changed-after-create"

    first = await store.get(created.run_id)
    assert first.manifest.provider == "fake"
    assert first.manifest.generation_config.temperature_milli == 0
    assert first.source_request == request
    first.manifest.__dict__["provider"] = "changed-after-get"
    assert (await store.get(created.run_id)).manifest.provider == "fake"


@pytest.mark.asyncio
async def test_successful_mutation_increments_version_and_stale_cas_rolls_back() -> (
    None
):
    clock = FakeClock()
    store = RunStore(clock)
    created = await store.create(make_record(clock))

    updated = await store.mutate(
        created.run_id,
        created.version,
        lambda current: current.model_copy(update={"stage": "ingesting"}),
    )
    assert updated.version == 1
    assert updated.stage == "ingesting"

    called = False

    def stale_change(current: StoredRun) -> StoredRun:
        nonlocal called
        called = True
        return current.model_copy(update={"stage": "extracting"})

    with pytest.raises(ConcurrentRunMutationError):
        await store.mutate(created.run_id, created.version, stale_change)
    assert called is False
    persisted = await store.get(created.run_id)
    assert persisted.version == 1
    assert persisted.stage == "ingesting"


@pytest.mark.asyncio
async def test_two_concurrent_writers_with_one_version_have_exactly_one_winner() -> (
    None
):
    clock = FakeClock()
    store = RunStore(clock)
    created = await store.create(make_record(clock))

    outcomes = await asyncio.gather(
        store.mutate(
            created.run_id,
            0,
            lambda current: current.model_copy(update={"stage": "ingesting"}),
        ),
        store.mutate(
            created.run_id,
            0,
            lambda current: current.model_copy(update={"stage": "failed"}),
        ),
        return_exceptions=True,
    )

    assert sum(isinstance(value, StoredRun) for value in outcomes) == 1
    assert sum(isinstance(value, ConcurrentRunMutationError) for value in outcomes) == 1
    assert (await store.get(created.run_id)).version == 1


@pytest.mark.asyncio
async def test_callback_exception_and_invalid_identity_change_roll_back() -> None:
    clock = FakeClock()
    store = RunStore(clock)
    created = await store.create(make_record(clock))

    def explode(_: StoredRun) -> StoredRun:
        raise LookupError("private callback detail")

    with pytest.raises(LookupError, match="private callback detail"):
        await store.mutate(created.run_id, 0, explode)
    assert (await store.get(created.run_id)).version == 0

    with pytest.raises(InvalidRunCommandError):
        await store.mutate(
            created.run_id,
            0,
            lambda current: current.model_copy(update={"run_id": "different-run"}),
        )
    persisted = await store.get(created.run_id)
    assert persisted.run_id == created.run_id
    assert persisted.version == 0


@pytest.mark.asyncio
@pytest.mark.parametrize("field", ["manifest", "created_at", "expires_at"])
async def test_mutation_rejects_other_immutable_identity_fields(field: str) -> None:
    clock = FakeClock()
    store = RunStore(clock)
    created = await store.create(make_record(clock))
    changes: dict[str, object] = {
        "manifest": created.manifest.model_copy(update={"provider": "other"}),
        "created_at": created.created_at + timedelta(seconds=1),
        "expires_at": created.expires_at - timedelta(seconds=1),
    }

    with pytest.raises(InvalidRunCommandError):
        await store.mutate(
            created.run_id,
            created.version,
            lambda current: current.model_copy(update={field: changes[field]}),
        )
    assert (await store.get(created.run_id)).version == 0


@pytest.mark.asyncio
async def test_mutation_callback_must_be_synchronous() -> None:
    clock = FakeClock()
    store = RunStore(clock)
    created = await store.create(make_record(clock))

    async def async_change(current: StoredRun) -> StoredRun:
        return current.model_copy(update={"stage": "ingesting"})

    with pytest.raises(InvalidRunCommandError):
        await store.mutate(created.run_id, 0, async_change)
    assert (await store.get(created.run_id)).version == 0


@pytest.mark.asyncio
async def test_delete_prevents_a_writer_that_already_captured_old_entry_from_resurrecting() -> (
    None
):
    clock = FakeClock()
    store = RunStore(clock)
    created = await store.create(make_record(clock))
    old_entry = store._entries[created.run_id]
    await old_entry.lock.acquire()
    writer = asyncio.create_task(
        store.mutate(
            created.run_id,
            0,
            lambda current: current.model_copy(update={"stage": "ingesting"}),
        )
    )
    await asyncio.sleep(0)

    await store.delete(created.run_id)
    replacement = await store.create(make_record(clock))
    old_entry.lock.release()

    with pytest.raises(RunNotFoundError):
        await writer
    assert (await store.get(created.run_id)).version == replacement.version == 0
    assert (await store.get(created.run_id)).stage == "queued"


@pytest.mark.asyncio
async def test_delete_is_immediate_and_missing_delete_is_safe_not_found() -> None:
    clock = FakeClock()
    store = RunStore(clock)
    created = await store.create(make_record(clock))

    await store.delete(created.run_id)
    with pytest.raises(RunNotFoundError):
        await store.get(created.run_id)
    with pytest.raises(RunNotFoundError):
        await store.delete(created.run_id)


@pytest.mark.asyncio
async def test_close_releases_all_runs_and_is_terminal_and_idempotent() -> None:
    clock = FakeClock()
    store = RunStore(clock)
    await store.create(make_record(clock))

    await store.aclose()
    await store.aclose()
    with pytest.raises(RunNotFoundError):
        await store.get("run-1")
    with pytest.raises(InvalidRunCommandError):
        await store.create(make_record(clock, run_id="run-2"))


@pytest.mark.asyncio
async def test_purge_removes_only_expired_entries_and_rejects_nonfinite_time() -> None:
    clock = FakeClock()
    store = RunStore(clock, ttl_seconds=10)
    await store.create(make_record(clock, run_id="run-1"))
    clock.tick = 105.0
    await store.create(make_record(clock, run_id="run-2"))

    assert await store.purge_expired(110.0) == 1
    with pytest.raises(RunNotFoundError):
        await store.get("run-1")
    assert (await store.get("run-2")).run_id == "run-2"
    for value in (nan, inf, -inf):
        with pytest.raises(InvalidRunCommandError):
            await store.purge_expired(value)


@pytest.mark.parametrize("ttl", [0, -1, 3601, True, 1.5])
def test_ttl_must_be_an_integer_between_one_and_3600(ttl: object) -> None:
    with pytest.raises(InvalidRunCommandError):
        RunStore(FakeClock(), ttl_seconds=ttl)  # type: ignore[arg-type]


@pytest.mark.asyncio
async def test_finite_monotonic_reading_must_still_form_a_future_deadline() -> None:
    clock = FakeClock()
    clock.tick = sys.float_info.max
    store = RunStore(clock)

    with pytest.raises(InvalidRunCommandError):
        await store.create(make_record(clock))
