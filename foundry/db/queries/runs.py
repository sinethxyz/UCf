"""Database queries for runs and run events."""

from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from foundry.contracts.task_types import TaskRequest
from foundry.db.models import Run, RunEvent


async def create_run(session: AsyncSession, task_request: TaskRequest) -> Run:
    """Create a new run from a task request.

    Args:
        session: Active database session.
        task_request: The validated task request to persist.

    Returns:
        The newly created Run record.
    """
    run = Run(
        task_type=task_request.task_type.value,
        repo=task_request.repo,
        base_branch=task_request.base_branch,
        title=task_request.title,
        prompt=task_request.prompt,
        state="queued",
        mcp_profile=task_request.mcp_profile.value,
        metadata_=task_request.metadata or {},
    )
    session.add(run)
    await session.flush()
    return run


async def get_run(session: AsyncSession, run_id: UUID) -> Run | None:
    """Fetch a single run by its primary key.

    Args:
        session: Active database session.
        run_id: UUID of the run to retrieve.

    Returns:
        The Run if found, otherwise None.
    """
    stmt = (
        select(Run)
        .where(Run.id == run_id)
        .options(selectinload(Run.events), selectinload(Run.artifacts))
    )
    result = await session.execute(stmt)
    return result.scalar_one_or_none()


async def update_run_state(
    session: AsyncSession,
    run_id: UUID,
    new_state: str,
    error_message: str | None = None,
) -> Run:
    """Transition a run to a new lifecycle state.

    Args:
        session: Active database session.
        run_id: UUID of the run to update.
        new_state: Target state value.
        error_message: Optional error details when transitioning to an error state.

    Returns:
        The updated Run record.
    """
    run = await session.get(Run, run_id)
    if run is None:
        raise ValueError(f"Run {run_id} not found")

    now = datetime.now(timezone.utc)
    run.state = new_state
    run.updated_at = now
    if error_message is not None:
        run.error_message = error_message

    terminal_states = {"completed", "cancelled", "errored"}
    if new_state in terminal_states:
        run.completed_at = now

    await session.flush()
    return run


async def list_runs(
    session: AsyncSession,
    limit: int,
    offset: int,
    state_filter: str | None = None,
) -> list[Run]:
    """List runs with pagination and optional state filtering.

    Args:
        session: Active database session.
        limit: Maximum number of runs to return.
        offset: Number of runs to skip.
        state_filter: If provided, only return runs matching this state.

    Returns:
        List of Run records ordered by creation time descending.
    """
    stmt = select(Run).order_by(Run.created_at.desc()).limit(limit).offset(offset)
    if state_filter is not None:
        stmt = stmt.where(Run.state == state_filter)
    result = await session.execute(stmt)
    return list(result.scalars().all())


async def add_run_event(session: AsyncSession, run_event: RunEvent) -> RunEvent:
    """Persist a run event.

    Args:
        session: Active database session.
        run_event: The RunEvent ORM instance to insert.

    Returns:
        The persisted RunEvent with generated fields populated.
    """
    session.add(run_event)
    await session.flush()
    return run_event


async def get_run_events(session: AsyncSession, run_id: UUID) -> list[RunEvent]:
    """Retrieve all events for a run, ordered by creation time.

    Args:
        session: Active database session.
        run_id: UUID of the parent run.

    Returns:
        List of RunEvent records in chronological order.
    """
    stmt = (
        select(RunEvent)
        .where(RunEvent.run_id == run_id)
        .order_by(RunEvent.created_at.asc())
    )
    result = await session.execute(stmt)
    return list(result.scalars().all())
