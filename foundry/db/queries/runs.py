"""Database queries for runs and run events."""

from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from foundry.contracts import TaskRequest
from foundry.db.models import Run, RunEvent


async def create_run(session: AsyncSession, task_request: TaskRequest) -> Run:
    """Create a new run from a task request.

    Args:
        session: Active database session.
        task_request: The validated task request to persist.

    Returns:
        The newly created Run record.
    """
    raise NotImplementedError("Phase 1")


async def get_run(session: AsyncSession, run_id: UUID) -> Run | None:
    """Fetch a single run by its primary key.

    Args:
        session: Active database session.
        run_id: UUID of the run to retrieve.

    Returns:
        The Run if found, otherwise None.
    """
    raise NotImplementedError("Phase 1")


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
    raise NotImplementedError("Phase 1")


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
    raise NotImplementedError("Phase 1")


async def add_run_event(session: AsyncSession, run_event: RunEvent) -> RunEvent:
    """Persist a run event.

    Args:
        session: Active database session.
        run_event: The RunEvent ORM instance to insert.

    Returns:
        The persisted RunEvent with generated fields populated.
    """
    raise NotImplementedError("Phase 1")


async def get_run_events(session: AsyncSession, run_id: UUID) -> list[RunEvent]:
    """Retrieve all events for a run, ordered by creation time.

    Args:
        session: Active database session.
        run_id: UUID of the parent run.

    Returns:
        List of RunEvent records in chronological order.
    """
    raise NotImplementedError("Phase 1")
