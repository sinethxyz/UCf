"""Worktree management endpoints."""

from fastapi import APIRouter

router = APIRouter()


@router.post("/worktrees/cleanup")
async def cleanup_worktrees() -> dict:
    """Trigger cleanup of stale worktrees."""
    raise NotImplementedError
