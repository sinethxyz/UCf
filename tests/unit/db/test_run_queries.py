"""Tests for foundry.db.queries.runs."""

import uuid

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from foundry.contracts.shared import MCPProfile, RunState, TaskType
from foundry.contracts.task_types import TaskRequest
from foundry.db.models import Run, RunEvent
from foundry.db.queries.runs import (
    add_run_event,
    create_run,
    get_run,
    get_run_events,
    list_runs,
    update_run_state,
)


# -- create_run ---------------------------------------------------------------


async def test_create_run_returns_run_with_queued_state(
    async_session: AsyncSession, sample_task_request: TaskRequest
):
    run = await create_run(async_session, sample_task_request)

    assert isinstance(run, Run)
    assert run.id is not None
    assert run.state == "queued"
    assert run.task_type == sample_task_request.task_type.value
    assert run.repo == sample_task_request.repo
    assert run.base_branch == sample_task_request.base_branch
    assert run.title == sample_task_request.title
    assert run.prompt == sample_task_request.prompt
    assert run.mcp_profile == sample_task_request.mcp_profile.value
    assert run.metadata_ == sample_task_request.metadata


async def test_create_run_generates_unique_uuid(
    async_session: AsyncSession, sample_task_request: TaskRequest
):
    run1 = await create_run(async_session, sample_task_request)
    run2 = await create_run(async_session, sample_task_request)
    assert run1.id != run2.id


async def test_create_run_empty_metadata(async_session: AsyncSession):
    req = TaskRequest(
        task_type=TaskType.REFACTOR,
        repo="unicorn-foundry",
        title="Clean up imports",
        prompt="Remove unused imports",
    )
    run = await create_run(async_session, req)
    assert run.metadata_ == {}


# -- get_run ------------------------------------------------------------------


async def test_get_run_returns_run_with_relationships(
    async_session: AsyncSession, sample_task_request: TaskRequest
):
    run = await create_run(async_session, sample_task_request)
    await async_session.commit()

    fetched = await get_run(async_session, run.id)
    assert fetched is not None
    assert fetched.id == run.id
    assert isinstance(fetched.events, list)
    assert isinstance(fetched.artifacts, list)


async def test_get_run_returns_none_for_missing_id(async_session: AsyncSession):
    result = await get_run(async_session, uuid.uuid4())
    assert result is None


# -- update_run_state ---------------------------------------------------------


async def test_update_run_state_changes_state(
    async_session: AsyncSession, sample_task_request: TaskRequest
):
    run = await create_run(async_session, sample_task_request)

    updated = await update_run_state(async_session, run.id, "planning")
    assert updated.state == "planning"
    assert updated.updated_at is not None


async def test_update_run_state_sets_error_message(
    async_session: AsyncSession, sample_task_request: TaskRequest
):
    run = await create_run(async_session, sample_task_request)

    updated = await update_run_state(
        async_session, run.id, "errored", error_message="Something broke"
    )
    assert updated.state == "errored"
    assert updated.error_message == "Something broke"
    assert updated.completed_at is not None


async def test_update_run_state_sets_completed_at_for_terminal_states(
    async_session: AsyncSession, sample_task_request: TaskRequest
):
    for terminal in ("completed", "cancelled", "errored"):
        run = await create_run(async_session, sample_task_request)
        updated = await update_run_state(async_session, run.id, terminal)
        assert updated.completed_at is not None, f"completed_at not set for {terminal}"


async def test_update_run_state_no_completed_at_for_non_terminal(
    async_session: AsyncSession, sample_task_request: TaskRequest
):
    run = await create_run(async_session, sample_task_request)
    updated = await update_run_state(async_session, run.id, "planning")
    assert updated.completed_at is None


async def test_update_run_state_raises_for_missing_run(async_session: AsyncSession):
    with pytest.raises(ValueError, match="not found"):
        await update_run_state(async_session, uuid.uuid4(), "planning")


# -- list_runs ----------------------------------------------------------------


async def test_list_runs_returns_ordered_by_created_desc(
    async_session: AsyncSession, sample_task_request: TaskRequest
):
    for _ in range(3):
        await create_run(async_session, sample_task_request)

    runs = await list_runs(async_session, limit=10, offset=0)
    assert len(runs) == 3
    # Most recent first
    for i in range(len(runs) - 1):
        assert runs[i].created_at >= runs[i + 1].created_at


async def test_list_runs_respects_limit_and_offset(
    async_session: AsyncSession, sample_task_request: TaskRequest
):
    for _ in range(5):
        await create_run(async_session, sample_task_request)

    page1 = await list_runs(async_session, limit=2, offset=0)
    page2 = await list_runs(async_session, limit=2, offset=2)
    assert len(page1) == 2
    assert len(page2) == 2
    assert page1[0].id != page2[0].id


async def test_list_runs_filters_by_state(
    async_session: AsyncSession, sample_task_request: TaskRequest
):
    run1 = await create_run(async_session, sample_task_request)
    run2 = await create_run(async_session, sample_task_request)
    await update_run_state(async_session, run2.id, "planning")

    queued = await list_runs(async_session, limit=10, offset=0, state_filter="queued")
    planning = await list_runs(async_session, limit=10, offset=0, state_filter="planning")
    assert len(queued) == 1
    assert len(planning) == 1
    assert queued[0].id == run1.id
    assert planning[0].id == run2.id


async def test_list_runs_empty_result(async_session: AsyncSession):
    runs = await list_runs(async_session, limit=10, offset=0)
    assert runs == []


# -- add_run_event / get_run_events ------------------------------------------


async def test_add_and_get_run_events(
    async_session: AsyncSession, sample_task_request: TaskRequest
):
    run = await create_run(async_session, sample_task_request)

    evt1 = RunEvent(run_id=run.id, state="queued", message="Run created")
    evt2 = RunEvent(run_id=run.id, state="planning", message="Planning started")
    await add_run_event(async_session, evt1)
    await add_run_event(async_session, evt2)

    events = await get_run_events(async_session, run.id)
    assert len(events) == 2
    assert events[0].state == "queued"
    assert events[1].state == "planning"


async def test_add_run_event_returns_event_with_id(
    async_session: AsyncSession, sample_task_request: TaskRequest
):
    run = await create_run(async_session, sample_task_request)
    evt = RunEvent(run_id=run.id, state="queued", message="Created")
    result = await add_run_event(async_session, evt)
    assert result.id is not None


async def test_get_run_events_returns_chronological_order(
    async_session: AsyncSession, sample_task_request: TaskRequest
):
    run = await create_run(async_session, sample_task_request)

    for state in ["queued", "creating_worktree", "planning"]:
        evt = RunEvent(run_id=run.id, state=state, message=f"State: {state}")
        await add_run_event(async_session, evt)

    events = await get_run_events(async_session, run.id)
    assert len(events) == 3
    for i in range(len(events) - 1):
        assert events[i].created_at <= events[i + 1].created_at


async def test_get_run_events_empty_for_unknown_run(async_session: AsyncSession):
    events = await get_run_events(async_session, uuid.uuid4())
    assert events == []
