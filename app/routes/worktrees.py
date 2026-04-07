"""Worktree management endpoints."""

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.deps import get_db_session

router = APIRouter()


class WorktreeCleanupResponse(BaseModel):
    """Response from worktree cleanup."""

    cleaned: int
    message: str


@router.post("/worktrees/cleanup", response_model=WorktreeCleanupResponse)
async def cleanup_worktrees(
    db: AsyncSession = Depends(get_db_session),
) -> WorktreeCleanupResponse:
    """Trigger cleanup of stale worktrees.

    Removes worktrees older than the configured max age and updates
    their database records.
    """
    raise HTTPException(status_code=501, detail="Not implemented")
