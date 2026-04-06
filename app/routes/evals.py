"""Eval run endpoints."""

from fastapi import APIRouter

router = APIRouter()


@router.post("/evals/run")
async def create_eval() -> dict:
    """Submit an eval run."""
    raise NotImplementedError


@router.get("/evals/{eval_id}")
async def get_eval(eval_id: str) -> dict:
    """Get eval run status and results."""
    raise NotImplementedError
