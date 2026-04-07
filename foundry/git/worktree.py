"""Git worktree management: create, list, and cleanup worktrees.

All Foundry code edits happen in isolated worktrees, never on main.
One worktree per run ensures full isolation.
"""

from pathlib import Path
from uuid import UUID


class WorktreeManager:
    """Manages git worktrees for isolated run execution.

    Each run gets its own worktree so concurrent runs never interfere.
    Worktrees are created under a configurable base directory and cleaned
    up after runs complete or when stale entries are detected.
    """

    def __init__(self, repo_path: str, worktree_base: str = "/tmp/foundry-worktrees") -> None:
        self.repo_path = Path(repo_path)
        self.worktree_base = Path(worktree_base)

    async def create(self, repo: str, branch_name: str, run_id: UUID) -> str:
        """Create a new worktree for the given branch and run.

        Args:
            repo: Repository identifier (e.g. 'unicorn-app').
            branch_name: The branch to create the worktree for.
            run_id: The run ID that owns this worktree.

        Returns:
            Absolute path to the created worktree directory.
        """
        raise NotImplementedError("Phase 1")

    async def cleanup(self, worktree_path: str) -> None:
        """Remove a worktree and its associated branch.

        Args:
            worktree_path: Absolute path to the worktree to clean up.
        """
        raise NotImplementedError("Phase 1")

    async def cleanup_stale(self, max_age_hours: int = 24) -> int:
        """Remove worktrees older than the given threshold.

        Args:
            max_age_hours: Maximum age in hours before a worktree is
                considered stale. Defaults to 24.

        Returns:
            Number of stale worktrees cleaned up.
        """
        raise NotImplementedError("Phase 1")

    async def list_active(self) -> list[dict]:
        """List all active worktrees managed by Foundry.

        Returns:
            List of dicts with worktree info including path, branch,
            run_id, and creation time.
        """
        raise NotImplementedError("Phase 1")
