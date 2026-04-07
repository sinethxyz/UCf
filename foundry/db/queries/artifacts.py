"""Database queries for run artifacts."""

from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from foundry.db.models import RunArtifact


async def store_artifact(
    session: AsyncSession,
    run_id: UUID,
    artifact_type: str,
    storage_path: str,
    size_bytes: int | None = None,
    checksum: str | None = None,
) -> RunArtifact:
    """Store metadata for a new run artifact.

    Args:
        session: Active database session.
        run_id: UUID of the parent run.
        artifact_type: Kind of artifact (e.g. ``plan``, ``diff``, ``review``).
        storage_path: Path or URI where the artifact content is stored.
        size_bytes: Optional file size in bytes.
        checksum: Optional integrity checksum (e.g. SHA-256 hex digest).

    Returns:
        The newly created RunArtifact record.
    """
    raise NotImplementedError("Phase 1")


async def get_artifacts(session: AsyncSession, run_id: UUID) -> list[RunArtifact]:
    """List all artifacts for a run.

    Args:
        session: Active database session.
        run_id: UUID of the parent run.

    Returns:
        List of RunArtifact records ordered by creation time.
    """
    raise NotImplementedError("Phase 1")


async def get_artifact(session: AsyncSession, artifact_id: UUID) -> RunArtifact | None:
    """Fetch a single artifact by its primary key.

    Args:
        session: Active database session.
        artifact_id: UUID of the artifact to retrieve.

    Returns:
        The RunArtifact if found, otherwise None.
    """
    raise NotImplementedError("Phase 1")
