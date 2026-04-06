"""Database queries for eval runs."""

from uuid import UUID

from sqlalchemy import update
from sqlalchemy.ext.asyncio import AsyncSession

from foundry.db.models import EvalRun


async def create_eval_run(session: AsyncSession, **kwargs) -> EvalRun:
    """Insert a new eval run record."""
    eval_run = EvalRun(**kwargs)
    session.add(eval_run)
    await session.flush()
    return eval_run


async def get_eval_run(session: AsyncSession, eval_id: UUID) -> EvalRun | None:
    """Fetch an eval run by ID."""
    return await session.get(EvalRun, eval_id)


async def complete_eval_run(
    session: AsyncSession,
    eval_id: UUID,
    metrics: dict,
    result_path: str,
) -> None:
    """Mark an eval run as completed with results."""
    stmt = (
        update(EvalRun)
        .where(EvalRun.id == eval_id)
        .values(state="completed", metrics=metrics, result_path=result_path)
    )
    await session.execute(stmt)
