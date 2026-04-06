"""Verification dispatch: routes verification to the correct runner based on file types."""

from pathlib import Path


async def run_verification(worktree_path: str, changed_files: list[str]) -> dict:
    """Run appropriate verification based on changed file types.

    Dispatches to Go, TypeScript, or schema verification based on
    the extensions of changed files.

    Args:
        worktree_path: Path to the worktree.
        changed_files: List of changed file paths.

    Returns:
        Aggregated verification results.
    """
    raise NotImplementedError
