"""Database queries for eval runs."""

from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from foundry.contracts import EvalDefinition
from foundry.db.models import EvalRun


async def create_eval_run(session: AsyncSession, definition: EvalDefinition) -> EvalRun:
    """Create a new eval run from a definition.

    Args:
        session: Active database session.
        definition: The validated eval definition specifying dataset, scorer, and model.

    Returns:
        The newly created EvalRun record.
    """
    raise NotImplementedError("Phase 1")


async def update_eval_run(
    session: AsyncSession,
    eval_id: UUID,
    state: str,
    metrics: dict | None = None,
    result_path: str | None = None,
) -> EvalRun:
    """Update an eval run's state and optional results.

    Args:
        session: Active database session.
        eval_id: UUID of the eval run to update.
        state: New state value.
        metrics: Aggregated scoring metrics, if available.
        result_path: Path to the full results artifact, if available.

    Returns:
        The updated EvalRun record.
    """
    raise NotImplementedError("Phase 1")


async def get_eval_run(session: AsyncSession, eval_id: UUID) -> EvalRun | None:
    """Fetch an eval run by its primary key.

    Args:
        session: Active database session.
        eval_id: UUID of the eval run to retrieve.

    Returns:
        The EvalRun if found, otherwise None.
    """
    raise NotImplementedError("Phase 1")


async def list_eval_runs(
    session: AsyncSession,
    dataset: str | None = None,
    limit: int = 20,
) -> list[EvalRun]:
    """List eval runs with optional dataset filtering.

    Args:
        session: Active database session.
        dataset: If provided, only return runs for this dataset.
        limit: Maximum number of results to return (default 20).

    Returns:
        List of EvalRun records ordered by creation time descending.
    """
    raise NotImplementedError("Phase 1")
