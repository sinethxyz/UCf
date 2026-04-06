"""Review endpoints."""

from fastapi import APIRouter

router = APIRouter()


@router.post("/reviews")
async def create_review() -> dict:
    """Submit a diff for independent review."""
    raise NotImplementedError
