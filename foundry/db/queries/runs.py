"""Database queries for runs and run events."""

from uuid import UUID

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from foundry.db.models import Run, RunEvent


async def create_run(session: AsyncSession, **kwargs) -> Run:
    """Insert a new run record."""
    run = Run(**kwargs)
    session.add(run)
    await session.flush()
    return run


async def get_run(session: AsyncSession, run_id: UUID) -> Run | None:
    """Fetch a run by ID."""
    return await session.get(Run, run_id)


async def update_run_state(session: AsyncSession, run_id: UUID, state: str, **kwargs) -> None:
    """Transition a run to a new state."""
    stmt = update(Run).where(Run.id == run_id).values(state=state, **kwargs)
    await session.execute(stmt)


async def list_run_events(session: AsyncSession, run_id: UUID) -> list[RunEvent]:
    """List all events for a run, ordered by creation time."""
    stmt = select(RunEvent).where(RunEvent.run_id == run_id).order_by(RunEvent.created_at)
    result = await session.execute(stmt)
    return list(result.scalars().all())


async def create_run_event(session: AsyncSession, **kwargs) -> RunEvent:
    """Insert a new run event."""
    event = RunEvent(**kwargs)
    session.add(event)
    await session.flush()
    return event
