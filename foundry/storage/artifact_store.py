"""Artifact storage: write and read run artifacts to local filesystem.

Storage path convention: runs/{run_id}/{artifact_type}.json

Phase 1: local filesystem. Can be upgraded to object storage later.
"""

import hashlib
import logging
import os
import tempfile
from datetime import UTC, datetime
from enum import StrEnum
from pathlib import Path
from typing import TypedDict
from uuid import UUID

logger = logging.getLogger(__name__)


class ArtifactType(StrEnum):
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
    TRANSITION = "transition"


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
        """Store an artifact using same-filesystem atomic replacement.

        The temporary file is flushed and synced before replacement, then its
        directory is synced. This is local file persistence, not a distributed
        transaction or a guarantee of exactly-once action execution.
        """
        if filename is None:
            ext = ".patch" if artifact_type == ArtifactType.DIFF else ".json"
            filename = f"{artifact_type.value}{ext}"

        rel_path = Path("runs") / str(run_id) / filename
        full_path = self.base_path / rel_path
        full_path.parent.mkdir(parents=True, exist_ok=True)

        content = data if isinstance(data, bytes) else data.encode("utf-8")
        with tempfile.TemporaryDirectory(prefix=".ucf-write-", dir=full_path.parent) as staging:
            temporary = Path(staging) / "artifact"
            with temporary.open("wb") as handle:
                handle.write(content)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temporary, full_path)
            directory_fd = os.open(full_path.parent, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
            try:
                os.fsync(directory_fd)
            finally:
                os.close(directory_fd)

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
        """Retrieve an artifact by its storage path."""
        full_path = self.base_path / storage_path
        if not full_path.exists():
            raise FileNotFoundError(f"Artifact not found: {storage_path}")
        return full_path.read_bytes()

    async def delete(self, storage_path: str) -> None:
        """Delete an artifact from storage."""
        full_path = self.base_path / storage_path
        if full_path.exists():
            full_path.unlink()
            logger.info("Deleted artifact: %s", storage_path)

    async def list_artifacts(self, run_id: UUID) -> list[ArtifactInfo]:
        """List all artifacts for a given run with metadata."""
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
                    stat.st_mtime, tz=UTC,
                ).isoformat(),
            ))
        return result

    def get_checksum(self, data: bytes | str) -> str:
        """Compute SHA-256 checksum for artifact data."""
        content = data if isinstance(data, bytes) else data.encode("utf-8")
        return hashlib.sha256(content).hexdigest()
