"""Artifact storage: write and read run artifacts to local filesystem.

Storage path convention: runs/{run_id}/{artifact_type}.json

Phase 1: local filesystem. Can be upgraded to object storage later.
"""

import hashlib
import logging
from enum import Enum
from pathlib import Path
from uuid import UUID

logger = logging.getLogger(__name__)


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
    PR_METADATA = "pr_metadata"


class ArtifactStore:
    """Stores and retrieves run artifacts on the local filesystem.

    Artifacts are keyed by run ID and type, following the path
    convention: runs/{run_id}/{artifact_type}.json
    """

    def __init__(self, base_path: str = "artifacts") -> None:
        self.base_path = Path(base_path)

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
            Storage path relative to base_path for retrieval.
        """
        if filename is None:
            ext = ".patch" if artifact_type == ArtifactType.DIFF else ".json"
            filename = f"{artifact_type.value}{ext}"

        rel_path = Path("runs") / str(run_id) / filename
        full_path = self.base_path / rel_path
        full_path.parent.mkdir(parents=True, exist_ok=True)

        content = data if isinstance(data, bytes) else data.encode("utf-8")
        full_path.write_bytes(content)

        logger.info("Stored artifact %s for run %s (%d bytes)", artifact_type.value, run_id, len(content))
        return str(rel_path)

    async def retrieve(self, storage_path: str) -> bytes:
        """Retrieve an artifact by its storage path.

        Args:
            storage_path: The path returned by store().

        Returns:
            Raw artifact data as bytes.
        """
        full_path = self.base_path / storage_path
        if not full_path.exists():
            raise FileNotFoundError(f"Artifact not found: {storage_path}")
        return full_path.read_bytes()

    async def delete(self, storage_path: str) -> None:
        """Delete an artifact from storage.

        Args:
            storage_path: The path of the artifact to delete.
        """
        full_path = self.base_path / storage_path
        if full_path.exists():
            full_path.unlink()
            logger.info("Deleted artifact: %s", storage_path)

    async def list_artifacts(self, run_id: UUID) -> list[str]:
        """List all artifact paths for a given run.

        Args:
            run_id: The run to list artifacts for.

        Returns:
            List of storage paths.
        """
        run_dir = self.base_path / "runs" / str(run_id)
        if not run_dir.exists():
            return []
        return [
            str(Path("runs") / str(run_id) / f.name)
            for f in sorted(run_dir.iterdir())
            if f.is_file()
        ]

    def get_checksum(self, data: bytes | str) -> str:
        """Compute SHA-256 checksum for artifact data."""
        content = data if isinstance(data, bytes) else data.encode("utf-8")
        return hashlib.sha256(content).hexdigest()
