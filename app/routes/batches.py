"""Batch extraction endpoints."""

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.deps import get_db_session
from foundry.contracts.extraction_models import ExtractionResult

router = APIRouter()


class BatchExtractRequest(BaseModel):
    """Request body for submitting an extraction batch."""

    source_ids: list[UUID]
    source_type: str
    model: str = "claude-sonnet-4-6"
    metadata: dict = {}


class BatchStatusResponse(BaseModel):
    """Status of a batch extraction job."""

    batch_id: UUID
    status: str
    total_items: int
    completed_items: int
    failed_items: int


@router.post("/batches/extract", status_code=201, response_model=BatchStatusResponse)
async def create_batch(
    request: BatchExtractRequest,
    db: AsyncSession = Depends(get_db_session),
) -> BatchStatusResponse:
    """Submit sources for batch extraction via the Anthropic Batch API.

    Creates a batch job record and enqueues items for processing.
    """
    raise HTTPException(status_code=501, detail="Not implemented")


@router.get("/batches/{batch_id}", response_model=BatchStatusResponse)
async def get_batch(
    batch_id: UUID,
    db: AsyncSession = Depends(get_db_session),
) -> BatchStatusResponse:
    """Get batch job status including item-level progress."""
    raise HTTPException(status_code=501, detail="Not implemented")


@router.get("/batches/{batch_id}/results", response_model=list[ExtractionResult])
async def get_batch_results(
    batch_id: UUID,
    db: AsyncSession = Depends(get_db_session),
) -> list[ExtractionResult]:
    """Get completed extraction results for a batch."""
    raise HTTPException(status_code=501, detail="Not implemented")
