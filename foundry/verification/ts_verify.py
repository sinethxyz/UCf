"""TypeScript verification: tsc, eslint, next build."""


async def verify_typescript(worktree_path: str) -> dict:
    """Run TypeScript verification suite on a worktree.

    Executes: tsc --noEmit, eslint.

    Args:
        worktree_path: Path to the worktree to verify.

    Returns:
        Dict with check results.
    """
    raise NotImplementedError
