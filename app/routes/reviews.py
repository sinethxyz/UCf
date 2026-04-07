"""Review endpoints."""

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.deps import get_db_session
from foundry.contracts.review_models import ReviewVerdict

router = APIRouter()


class ReviewRequest(BaseModel):
    """Request body for standalone code review."""

    diff: str
    title: str = ""
    context: str = ""
    metadata: dict = {}


@router.post("/reviews", response_model=ReviewVerdict)
async def create_review(
    request: ReviewRequest,
    db: AsyncSession = Depends(get_db_session),
) -> ReviewVerdict:
    """Submit a diff for independent review.

    Runs the reviewer subagent against the provided diff without
    requiring a full run lifecycle.
    """
    raise HTTPException(status_code=501, detail="Not implemented")
