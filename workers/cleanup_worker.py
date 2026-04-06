"""Cleanup worker: periodic cleanup of stale worktrees and artifacts."""


async def cleanup_stale_worktrees(max_age_hours: int = 24) -> int:
    """Remove worktrees older than max_age_hours.

    Args:
        max_age_hours: Maximum age before cleanup.

    Returns:
        Number of worktrees cleaned up.
    """
    raise NotImplementedError
