"""Artifact storage: write and read run artifacts to local filesystem.

Storage path convention: runs/{run_id}/{artifact_type}.json

Phase 1: local filesystem. Can be upgraded to object storage later.
"""

import hashlib
import logging
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import TypedDict
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


class StoreResult(TypedDict):
    """Return value of ArtifactStore.store()."""

    storage_path: str
    size_bytes: int
    checksum: str


class ArtifactInfo(TypedDict):
    """Metadata for a stored artifact file."""

    filename: str
    size_bytes: int
    modified: str


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
    ) -> StoreResult:
        """Store an artifact for a run.

        Args:
            run_id: The run that produced this artifact.
            artifact_type: Type of artifact (plan, diff, review, etc.).
            data: Raw artifact data as bytes or string.
            filename: Optional custom filename. Defaults to
                '{artifact_type}.json' (or '.patch' for diffs).

        Returns:
            Dict with storage_path (relative), size_bytes, and SHA-256 checksum.
        """
        if filename is None:
            ext = ".patch" if artifact_type == ArtifactType.DIFF else ".json"
            filename = f"{artifact_type.value}{ext}"

        rel_path = Path("runs") / str(run_id) / filename
        full_path = self.base_path / rel_path
        full_path.parent.mkdir(parents=True, exist_ok=True)

        content = data if isinstance(data, bytes) else data.encode("utf-8")
        full_path.write_bytes(content)

        size_bytes = len(content)
        checksum = hashlib.sha256(content).hexdigest()

        logger.info(
            "Stored artifact %s for run %s (%d bytes, sha256=%s)",
            artifact_type.value, run_id, size_bytes, checksum[:12],
        )
        return StoreResult(
            storage_path=str(rel_path),
            size_bytes=size_bytes,
            checksum=checksum,
        )

    async def retrieve(self, storage_path: str) -> bytes:
        """Retrieve an artifact by its storage path.

        Args:
            storage_path: The path returned by store().

        Returns:
            Raw artifact data as bytes.

        Raises:
            FileNotFoundError: If the artifact does not exist at the given path.
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

    async def list_artifacts(self, run_id: UUID) -> list[ArtifactInfo]:
        """List all artifacts for a given run with metadata.

        Args:
            run_id: The run to list artifacts for.

        Returns:
            List of dicts with filename, size_bytes, and modified (ISO timestamp).
        """
        run_dir = self.base_path / "runs" / str(run_id)
        if not run_dir.exists():
            return []
        result: list[ArtifactInfo] = []
        for f in sorted(run_dir.iterdir()):
            if not f.is_file():
                continue
            stat = f.stat()
            result.append(ArtifactInfo(
                filename=f.name,
                size_bytes=stat.st_size,
                modified=datetime.fromtimestamp(
                    stat.st_mtime, tz=timezone.utc,
                ).isoformat(),
            ))
        return result

    def get_checksum(self, data: bytes | str) -> str:
        """Compute SHA-256 checksum for artifact data."""
        content = data if isinstance(data, bytes) else data.encode("utf-8")
        return hashlib.sha256(content).hexdigest()
