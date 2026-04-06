"""Git worktree management: create, list, and cleanup worktrees.

All Foundry code edits happen in isolated worktrees, never on main.
"""

from pathlib import Path


class WorktreeManager:
    """Manages git worktrees for isolated run execution."""

    def __init__(self, repo_path: str, worktree_base: str = "/tmp/foundry-worktrees") -> None:
        self.repo_path = Path(repo_path)
        self.worktree_base = Path(worktree_base)

    async def create(self, branch_name: str) -> Path:
        """Create a new worktree for the given branch.

        Args:
            branch_name: The branch to create the worktree for.

        Returns:
            Path to the created worktree directory.
        """
        raise NotImplementedError

    async def cleanup(self, worktree_path: Path) -> None:
        """Remove a worktree and its associated branch.

        Args:
            worktree_path: Path to the worktree to clean up.
        """
        raise NotImplementedError

    async def list_active(self) -> list[dict]:
        """List all active worktrees.

        Returns:
            List of worktree metadata dicts.
        """
        raise NotImplementedError
