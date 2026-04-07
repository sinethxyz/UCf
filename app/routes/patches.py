"""Patch application endpoints."""

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.deps import get_db_session

router = APIRouter()


class PatchApplyRequest(BaseModel):
    """Request body for applying a stored patch to a worktree."""

    patch_artifact_path: str
    worktree_path: str
    metadata: dict = {}


class PatchApplyResponse(BaseModel):
    """Response after applying a patch."""

    success: bool
    files_modified: list[str] = []
    message: str = ""


@router.post("/patches/apply", response_model=PatchApplyResponse)
async def apply_patch(
    request: PatchApplyRequest,
    db: AsyncSession = Depends(get_db_session),
) -> PatchApplyResponse:
    """Apply a stored patch to a worktree.

    Retrieves the patch artifact from storage and applies it to the
    specified worktree directory using git apply.
    """
    raise HTTPException(status_code=501, detail="Not implemented")
