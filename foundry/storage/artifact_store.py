"""Artifact storage: write and read artifacts to object storage.

Storage path convention: foundry/runs/{run_id}/{artifact_type}.json
"""

from pathlib import Path
from uuid import UUID


class ArtifactStore:
    """Manages artifact persistence."""

    def __init__(self, base_path: str = "artifacts") -> None:
        self.base_path = Path(base_path)

    async def store(self, run_id: UUID, artifact_type: str, data: bytes) -> str:
        """Store an artifact.

        Args:
            run_id: The run that produced this artifact.
            artifact_type: Type of artifact (plan, diff, review, etc.).
            data: Raw artifact data.

        Returns:
            Storage path for the artifact.
        """
        raise NotImplementedError

    async def retrieve(self, storage_path: str) -> bytes:
        """Retrieve an artifact by its storage path.

        Args:
            storage_path: The path returned by store().

        Returns:
            Raw artifact data.
        """
        raise NotImplementedError
