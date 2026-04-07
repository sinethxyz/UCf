"""Database queries for batch jobs and batch items."""

from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from foundry.db.models import BatchItem, BatchJob


async def create_batch(
    session: AsyncSession,
    batch_type: str,
    model: str,
    total_items: int,
) -> BatchJob:
    """Create a new batch job record.

    Args:
        session: Active database session.
        batch_type: Kind of batch (e.g. ``extraction``, ``classification``).
        model: Claude model identifier to use for batch processing.
        total_items: Expected number of items in the batch.

    Returns:
        The newly created BatchJob record.
    """
    raise NotImplementedError("Phase 1")


async def update_batch_state(
    session: AsyncSession,
    batch_id: UUID,
    state: str,
    completed: int = 0,
    failed: int = 0,
) -> BatchJob:
    """Update a batch job's state and progress counters.

    Args:
        session: Active database session.
        batch_id: UUID of the batch job to update.
        state: New state value.
        completed: Number of successfully completed items.
        failed: Number of failed items.

    Returns:
        The updated BatchJob record.
    """
    raise NotImplementedError("Phase 1")


async def add_batch_item(
    session: AsyncSession,
    batch_id: UUID,
    input_hash: str,
) -> BatchItem:
    """Add an item to a batch job.

    Args:
        session: Active database session.
        batch_id: UUID of the parent batch job.
        input_hash: Content hash of the input payload for deduplication.

    Returns:
        The newly created BatchItem record.
    """
    raise NotImplementedError("Phase 1")


async def update_batch_item(
    session: AsyncSession,
    item_id: UUID,
    state: str,
    result_path: str | None = None,
    is_valid: bool | None = None,
    error: str | None = None,
) -> BatchItem:
    """Update the state and results of a batch item.

    Args:
        session: Active database session.
        item_id: UUID of the batch item to update.
        state: New state value.
        result_path: Path to the result artifact, if available.
        is_valid: Whether the result passed schema validation.
        error: Error message if the item failed.

    Returns:
        The updated BatchItem record.
    """
    raise NotImplementedError("Phase 1")


async def get_batch_items(session: AsyncSession, batch_id: UUID) -> list[BatchItem]:
    """List all items for a batch job.

    Args:
        session: Active database session.
        batch_id: UUID of the parent batch job.

    Returns:
        List of BatchItem records ordered by creation time.
    """
    raise NotImplementedError("Phase 1")
