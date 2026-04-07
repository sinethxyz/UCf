"""Run management endpoints."""

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.deps import get_db_session, get_run_engine
from foundry.contracts.run_models import RunArtifact, RunEvent, RunResponse
from foundry.contracts.task_types import TaskRequest
from foundry.orchestration.run_engine import RunEngine

router = APIRouter()


@router.post("/runs", status_code=201, response_model=RunResponse)
async def create_run(
    task_request: TaskRequest,
    db: AsyncSession = Depends(get_db_session),
    engine: RunEngine = Depends(get_run_engine),
) -> RunResponse:
    """Submit a new task for execution.

    Validates the task request, creates a run record in QUEUED state,
    and enqueues it for processing by the run worker.
    """
    raise HTTPException(status_code=501, detail="Not implemented")


@router.get("/runs/{run_id}", response_model=RunResponse)
async def get_run(
    run_id: UUID,
    db: AsyncSession = Depends(get_db_session),
) -> RunResponse:
    """Get run status and metadata."""
    raise HTTPException(status_code=501, detail="Not implemented")


@router.get("/runs/{run_id}/events", response_model=list[RunEvent])
async def get_run_events(
    run_id: UUID,
    db: AsyncSession = Depends(get_db_session),
) -> list[RunEvent]:
    """Get all events for a run, ordered by timestamp."""
    raise HTTPException(status_code=501, detail="Not implemented")


@router.get("/runs/{run_id}/artifacts", response_model=list[RunArtifact])
async def get_run_artifacts(
    run_id: UUID,
    db: AsyncSession = Depends(get_db_session),
) -> list[RunArtifact]:
    """Get all artifacts produced by a run."""
    raise HTTPException(status_code=501, detail="Not implemented")


@router.post("/runs/{run_id}/cancel", response_model=RunResponse)
async def cancel_run(
    run_id: UUID,
    db: AsyncSession = Depends(get_db_session),
    engine: RunEngine = Depends(get_run_engine),
) -> RunResponse:
    """Cancel an in-progress run.

    Only runs in non-terminal states can be cancelled.
    """
    raise HTTPException(status_code=501, detail="Not implemented")


@router.post("/runs/{run_id}/retry", response_model=RunResponse)
async def retry_run(
    run_id: UUID,
    db: AsyncSession = Depends(get_db_session),
    engine: RunEngine = Depends(get_run_engine),
) -> RunResponse:
    """Retry a failed run.

    Only runs in plan_failed, verification_failed, or review_failed
    states can be retried.
    """
    raise HTTPException(status_code=501, detail="Not implemented")
