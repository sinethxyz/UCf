"""Cleanup worker: periodic cleanup of stale worktrees and old artifacts."""

from __future__ import annotations

import logging

logger = logging.getLogger(__name__)


class CleanupWorker:
    """Periodic cleanup of stale worktrees and old artifacts.

    Runs on a configurable interval to remove worktrees that have exceeded
    their maximum age and purge artifacts older than the retention period.
    """

    def __init__(self, worktree_base_path: str, artifact_base_path: str) -> None:
        self.worktree_base_path = worktree_base_path
        self.artifact_base_path = artifact_base_path
        self._running = False

    async def start(self) -> None:
        """Begin the periodic cleanup loop.

        Blocks until :meth:`shutdown` is called.
        """
        raise NotImplementedError("Cleanup worker not yet implemented")

    async def cleanup_worktrees(self, max_age_hours: int = 24) -> int:
        """Remove worktrees older than max_age_hours.

        Args:
            max_age_hours: Maximum age in hours before a worktree is removed.

        Returns:
            Number of worktrees cleaned up.
        """
        raise NotImplementedError("Worktree cleanup not yet implemented")

    async def cleanup_artifacts(self, max_age_days: int = 30) -> int:
        """Remove artifacts older than max_age_days.

        Args:
            max_age_days: Maximum age in days before an artifact is removed.

        Returns:
            Number of artifacts cleaned up.
        """
        raise NotImplementedError("Artifact cleanup not yet implemented")

    async def shutdown(self) -> None:
        """Signal the worker to stop and exit gracefully."""
        logger.info("CleanupWorker shutting down")
        self._running = False
