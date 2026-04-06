"""Batch extraction endpoints."""

from fastapi import APIRouter

router = APIRouter()


@router.post("/batches/extract")
async def create_batch() -> dict:
    """Submit sources for batch extraction."""
    raise NotImplementedError


@router.get("/batches/{batch_id}")
async def get_batch(batch_id: str) -> dict:
    """Get batch job status."""
    raise NotImplementedError


@router.get("/batches/{batch_id}/results")
async def get_batch_results(batch_id: str) -> dict:
    """Get batch extraction results."""
    raise NotImplementedError
