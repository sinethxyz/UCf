"""Database queries for run artifacts."""

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from foundry.db.models import RunArtifact


async def create_artifact(session: AsyncSession, **kwargs) -> RunArtifact:
    """Insert a new artifact record."""
    artifact = RunArtifact(**kwargs)
    session.add(artifact)
    await session.flush()
    return artifact


async def get_artifact(session: AsyncSession, artifact_id: UUID) -> RunArtifact | None:
    """Fetch an artifact by ID."""
    return await session.get(RunArtifact, artifact_id)


async def list_artifacts_for_run(session: AsyncSession, run_id: UUID) -> list[RunArtifact]:
    """List all artifacts for a run."""
    stmt = select(RunArtifact).where(RunArtifact.run_id == run_id).order_by(RunArtifact.created_at)
    result = await session.execute(stmt)
    return list(result.scalars().all())
