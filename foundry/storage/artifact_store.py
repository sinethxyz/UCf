"""Artifact storage: write and read run artifacts to object storage.

Storage path convention: foundry/runs/{run_id}/{artifact_type}.json
"""

from enum import Enum
from uuid import UUID


class ArtifactType(str, Enum):
    """Types of artifacts produced by Foundry runs."""

    PLAN = "plan"
    DIFF = "diff"
    REVIEW = "review"
    VERIFICATION = "verification"
    PATCH = "patch"
    EXTRACTION = "extraction"
    EVAL = "eval"
    ERROR_LOG = "error_log"


class ArtifactStore:
    """Stores and retrieves run artifacts in object storage.

    Artifacts are keyed by run ID and type, following the path
    convention: foundry/runs/{run_id}/{artifact_type}.json
    """

    def __init__(self, base_path: str = "artifacts") -> None:
        self.base_path = base_path

    async def store(
        self,
        run_id: UUID,
        artifact_type: ArtifactType,
        data: bytes | str,
        filename: str | None = None,
    ) -> str:
        """Store an artifact for a run.

        Args:
            run_id: The run that produced this artifact.
            artifact_type: Type of artifact (plan, diff, review, etc.).
            data: Raw artifact data as bytes or string.
            filename: Optional custom filename. Defaults to
                '{artifact_type}.json'.

        Returns:
            Storage path for retrieval.
        """
        raise NotImplementedError("Phase 1")

    async def retrieve(self, storage_path: str) -> bytes:
        """Retrieve an artifact by its storage path.

        Args:
            storage_path: The path returned by store().

        Returns:
            Raw artifact data as bytes.
        """
        raise NotImplementedError("Phase 1")

    async def delete(self, storage_path: str) -> None:
        """Delete an artifact from storage.

        Args:
            storage_path: The path of the artifact to delete.
        """
        raise NotImplementedError("Phase 1")

    async def list_artifacts(self, run_id: UUID) -> list[str]:
        """List all artifact paths for a given run.

        Args:
            run_id: The run to list artifacts for.

        Returns:
            List of storage paths.
        """
        raise NotImplementedError("Phase 1")
