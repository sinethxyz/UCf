"""Patch application endpoints."""

from fastapi import APIRouter

router = APIRouter()


@router.post("/patches/apply")
async def apply_patch() -> dict:
    """Apply a patch to a worktree."""
    raise NotImplementedError
