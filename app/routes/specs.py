"""Spec planning endpoints."""

from fastapi import APIRouter

router = APIRouter()


@router.post("/specs/plan")
async def create_plan() -> dict:
    """Convert a feature spec into an implementation plan."""
    raise NotImplementedError
