"""Database queries for batch jobs and batch items."""

from uuid import UUID

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from foundry.db.models import BatchItem, BatchJob


async def create_batch_job(session: AsyncSession, **kwargs) -> BatchJob:
    """Insert a new batch job record."""
    job = BatchJob(**kwargs)
    session.add(job)
    await session.flush()
    return job


async def get_batch_job(session: AsyncSession, batch_id: UUID) -> BatchJob | None:
    """Fetch a batch job by ID."""
    return await session.get(BatchJob, batch_id)


async def update_batch_progress(
    session: AsyncSession,
    batch_id: UUID,
    completed_items: int,
    failed_items: int,
) -> None:
    """Update batch job progress counters."""
    stmt = (
        update(BatchJob)
        .where(BatchJob.id == batch_id)
        .values(completed_items=completed_items, failed_items=failed_items)
    )
    await session.execute(stmt)


async def create_batch_item(session: AsyncSession, **kwargs) -> BatchItem:
    """Insert a new batch item."""
    item = BatchItem(**kwargs)
    session.add(item)
    await session.flush()
    return item


async def list_batch_items(session: AsyncSession, batch_id: UUID) -> list[BatchItem]:
    """List all items for a batch job."""
    stmt = select(BatchItem).where(BatchItem.batch_id == batch_id).order_by(BatchItem.created_at)
    result = await session.execute(stmt)
    return list(result.scalars().all())
