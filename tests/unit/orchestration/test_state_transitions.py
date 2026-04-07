"""Tests for the RunEngine state machine (_transition and VALID_TRANSITIONS)."""

import uuid
from unittest.mock import AsyncMock, MagicMock

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from foundry.contracts.shared import RunState
from foundry.contracts.task_types import TaskRequest
from foundry.db.models import RunEvent
from foundry.db.queries.runs import create_run, get_run, get_run_events
from foundry.orchestration.run_engine import VALID_TRANSITIONS, RunEngine


@pytest.fixture
def run_engine(async_session: AsyncSession) -> RunEngine:
    """Return a RunEngine with mock dependencies (only session is real)."""
    return RunEngine(
        session=async_session,
        artifact_store=MagicMock(),
        worktree_manager=MagicMock(),
        agent_runner=MagicMock(),
        pr_creator=MagicMock(),
        verification_runner=MagicMock(),
    )


# -- VALID_TRANSITIONS structure ----------------------------------------------


def test_all_run_states_are_in_transition_map():
    """Every RunState enum member must appear as a key in VALID_TRANSITIONS."""
    for state in RunState:
        assert state in VALID_TRANSITIONS, f"{state} missing from VALID_TRANSITIONS"


def test_terminal_states_have_no_outgoing_transitions():
    terminal = {RunState.COMPLETED, RunState.CANCELLED, RunState.ERRORED}
    for state in terminal:
        assert VALID_TRANSITIONS[state] == set(), (
            f"Terminal state {state} should have no outgoing transitions"
        )


def test_happy_path_is_fully_connected():
    """The happy path from QUEUED to COMPLETED must be traversable."""
    happy_path = [
        RunState.QUEUED,
        RunState.CREATING_WORKTREE,
        RunState.PLANNING,
        RunState.IMPLEMENTING,
        RunState.VERIFYING,
        RunState.VERIFICATION_PASSED,
        RunState.REVIEWING,
        RunState.PR_OPENED,
        RunState.COMPLETED,
    ]
    for i in range(len(happy_path) - 1):
        from_s, to_s = happy_path[i], happy_path[i + 1]
        assert to_s in VALID_TRANSITIONS[from_s], (
            f"Happy path broken: {from_s.value} -> {to_s.value}"
        )


def test_failure_states_can_retry_to_queued():
    retryable = [RunState.PLAN_FAILED, RunState.VERIFICATION_FAILED, RunState.REVIEW_FAILED]
    for state in retryable:
        assert RunState.QUEUED in VALID_TRANSITIONS[state], (
            f"{state} should be able to transition to QUEUED for retry"
        )


def test_all_active_states_can_reach_errored():
    """Every non-terminal, non-failure state should allow transitioning to ERRORED."""
    exempt = {
        RunState.COMPLETED, RunState.CANCELLED, RunState.ERRORED,
        RunState.QUEUED,  # QUEUED -> CANCELLED, not ERRORED
        RunState.PLAN_FAILED, RunState.VERIFICATION_FAILED, RunState.REVIEW_FAILED,
    }
    for state in RunState:
        if state in exempt:
            continue
        assert RunState.ERRORED in VALID_TRANSITIONS[state], (
            f"Active state {state} should be able to transition to ERRORED"
        )


# -- _transition valid transitions -------------------------------------------


async def test_transition_valid_updates_state(
    async_session: AsyncSession,
    sample_task_request: TaskRequest,
    run_engine: RunEngine,
):
    run = await create_run(async_session, sample_task_request)

    await run_engine._transition(
        run.id, RunState.QUEUED, RunState.CREATING_WORKTREE, "Starting"
    )

    updated = await get_run(async_session, run.id)
    assert updated is not None
    assert updated.state == RunState.CREATING_WORKTREE.value


async def test_transition_creates_event(
    async_session: AsyncSession,
    sample_task_request: TaskRequest,
    run_engine: RunEngine,
):
    run = await create_run(async_session, sample_task_request)

    await run_engine._transition(
        run.id, RunState.QUEUED, RunState.CREATING_WORKTREE, "Creating worktree"
    )

    events = await get_run_events(async_session, run.id)
    assert len(events) == 1
    assert events[0].state == RunState.CREATING_WORKTREE.value
    assert events[0].message == "Creating worktree"


async def test_transition_multiple_steps(
    async_session: AsyncSession,
    sample_task_request: TaskRequest,
    run_engine: RunEngine,
):
    """Walk multiple valid transitions sequentially."""
    run = await create_run(async_session, sample_task_request)

    transitions = [
        (RunState.QUEUED, RunState.CREATING_WORKTREE),
        (RunState.CREATING_WORKTREE, RunState.PLANNING),
        (RunState.PLANNING, RunState.IMPLEMENTING),
    ]
    for from_s, to_s in transitions:
        await run_engine._transition(run.id, from_s, to_s, f"{from_s.value} -> {to_s.value}")

    updated = await get_run(async_session, run.id)
    assert updated is not None
    assert updated.state == RunState.IMPLEMENTING.value

    events = await get_run_events(async_session, run.id)
    assert len(events) == 3


# -- _transition invalid transitions ----------------------------------------


async def test_transition_invalid_raises_value_error(
    async_session: AsyncSession,
    sample_task_request: TaskRequest,
    run_engine: RunEngine,
):
    run = await create_run(async_session, sample_task_request)

    with pytest.raises(ValueError, match="Invalid transition"):
        await run_engine._transition(
            run.id, RunState.QUEUED, RunState.COMPLETED, "Skip everything"
        )


async def test_transition_from_terminal_raises(
    async_session: AsyncSession,
    sample_task_request: TaskRequest,
    run_engine: RunEngine,
):
    """Terminal states have no outgoing transitions."""
    run = await create_run(async_session, sample_task_request)

    # Move to completed via the happy path shortcut
    await run_engine._transition(run.id, RunState.QUEUED, RunState.CREATING_WORKTREE, "")
    await run_engine._transition(run.id, RunState.CREATING_WORKTREE, RunState.PLANNING, "")
    await run_engine._transition(run.id, RunState.PLANNING, RunState.IMPLEMENTING, "")
    await run_engine._transition(run.id, RunState.IMPLEMENTING, RunState.VERIFYING, "")
    await run_engine._transition(run.id, RunState.VERIFYING, RunState.VERIFICATION_PASSED, "")
    await run_engine._transition(run.id, RunState.VERIFICATION_PASSED, RunState.REVIEWING, "")
    await run_engine._transition(run.id, RunState.REVIEWING, RunState.PR_OPENED, "")
    await run_engine._transition(run.id, RunState.PR_OPENED, RunState.COMPLETED, "Done")

    with pytest.raises(ValueError, match="Invalid transition"):
        await run_engine._transition(
            run.id, RunState.COMPLETED, RunState.QUEUED, "Try again"
        )


async def test_transition_backward_not_allowed(
    async_session: AsyncSession,
    sample_task_request: TaskRequest,
    run_engine: RunEngine,
):
    """Cannot go backward in the pipeline (e.g., PLANNING -> QUEUED)."""
    run = await create_run(async_session, sample_task_request)

    await run_engine._transition(run.id, RunState.QUEUED, RunState.CREATING_WORKTREE, "")
    await run_engine._transition(run.id, RunState.CREATING_WORKTREE, RunState.PLANNING, "")

    with pytest.raises(ValueError, match="Invalid transition"):
        await run_engine._transition(
            run.id, RunState.PLANNING, RunState.QUEUED, "Backtrack"
        )


async def test_transition_to_errored_from_active_state(
    async_session: AsyncSession,
    sample_task_request: TaskRequest,
    run_engine: RunEngine,
):
    run = await create_run(async_session, sample_task_request)
    await run_engine._transition(run.id, RunState.QUEUED, RunState.CREATING_WORKTREE, "")

    await run_engine._transition(
        run.id, RunState.CREATING_WORKTREE, RunState.ERRORED, "Worktree failed"
    )

    updated = await get_run(async_session, run.id)
    assert updated is not None
    assert updated.state == RunState.ERRORED.value


async def test_transition_default_message(
    async_session: AsyncSession,
    sample_task_request: TaskRequest,
    run_engine: RunEngine,
):
    """When message is empty, _transition fills in a default."""
    run = await create_run(async_session, sample_task_request)
    await run_engine._transition(run.id, RunState.QUEUED, RunState.CREATING_WORKTREE, "")

    events = await get_run_events(async_session, run.id)
    assert len(events) == 1
    assert "creating_worktree" in events[0].message.lower()


async def test_transition_retry_from_plan_failed(
    async_session: AsyncSession,
    sample_task_request: TaskRequest,
    run_engine: RunEngine,
):
    run = await create_run(async_session, sample_task_request)
    await run_engine._transition(run.id, RunState.QUEUED, RunState.CREATING_WORKTREE, "")
    await run_engine._transition(run.id, RunState.CREATING_WORKTREE, RunState.PLANNING, "")
    await run_engine._transition(run.id, RunState.PLANNING, RunState.PLAN_FAILED, "Bad plan")

    # Retry: PLAN_FAILED -> QUEUED
    await run_engine._transition(run.id, RunState.PLAN_FAILED, RunState.QUEUED, "Retrying")

    updated = await get_run(async_session, run.id)
    assert updated is not None
    assert updated.state == RunState.QUEUED.value
