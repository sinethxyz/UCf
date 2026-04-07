"""Run management endpoints."""

import json
from uuid import UUID

import redis.asyncio as aioredis
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.deps import get_db_session, get_redis, get_run_engine
from foundry.contracts.run_models import RunArtifact, RunEvent, RunResponse
from foundry.contracts.task_types import TaskRequest
from foundry.db.queries import artifacts as artifact_queries
from foundry.db.queries import runs as run_queries
from foundry.orchestration.run_engine import RunEngine

router = APIRouter()

QUEUE_KEY = "foundry:runs"


def _run_to_response(run) -> RunResponse:
    """Map a Run ORM instance to a RunResponse contract."""
    return RunResponse.model_validate(run)


@router.post("/runs", status_code=201, response_model=RunResponse)
async def create_run(
    task_request: TaskRequest,
    db: AsyncSession = Depends(get_db_session),
    redis: aioredis.Redis = Depends(get_redis),
) -> RunResponse:
    """Submit a new task for execution.

    Validates the task request, creates a run record in QUEUED state,
    and enqueues it for processing by the run worker.
    """
    run = await run_queries.create_run(db, task_request)
    await db.flush()

    # Enqueue for worker processing
    payload = task_request.model_dump(mode="json")
    payload["_run_id"] = str(run.id)
    await redis.lpush(QUEUE_KEY, json.dumps(payload))

    return _run_to_response(run)


@router.get("/runs/{run_id}", response_model=RunResponse)
async def get_run(
    run_id: UUID,
    db: AsyncSession = Depends(get_db_session),
) -> RunResponse:
    """Get run status and metadata."""
    run = await run_queries.get_run(db, run_id)
    if run is None:
        raise HTTPException(status_code=404, detail="Run not found")
    return _run_to_response(run)


@router.get("/runs/{run_id}/events", response_model=list[RunEvent])
async def get_run_events(
    run_id: UUID,
    db: AsyncSession = Depends(get_db_session),
) -> list[RunEvent]:
    """Get all events for a run, ordered by timestamp."""
    run = await run_queries.get_run(db, run_id)
    if run is None:
        raise HTTPException(status_code=404, detail="Run not found")

    events = await run_queries.get_run_events(db, run_id)
    return [
        RunEvent(
            run_id=e.run_id,
            timestamp=e.created_at,
            state=e.state,
            message=e.message,
            metadata=e.metadata_,
            duration_ms=e.duration_ms,
            model_used=e.model_used,
            tokens_in=e.tokens_in,
            tokens_out=e.tokens_out,
        )
        for e in events
    ]


@router.get("/runs/{run_id}/artifacts", response_model=list[RunArtifact])
async def get_run_artifacts(
    run_id: UUID,
    db: AsyncSession = Depends(get_db_session),
) -> list[RunArtifact]:
    """Get all artifacts produced by a run."""
    run = await run_queries.get_run(db, run_id)
    if run is None:
        raise HTTPException(status_code=404, detail="Run not found")

    artifacts = await artifact_queries.get_artifacts(db, run_id)
    return [RunArtifact.model_validate(a) for a in artifacts]


@router.post("/runs/{run_id}/cancel", response_model=RunResponse)
async def cancel_run(
    run_id: UUID,
    db: AsyncSession = Depends(get_db_session),
) -> RunResponse:
    """Cancel an in-progress run.

    Only runs in non-terminal states can be cancelled.
    """
    engine = await get_run_engine(db)
    try:
        return await engine.cancel_run(run_id)
    except ValueError as e:
        raise HTTPException(status_code=409, detail=str(e))


@router.post("/runs/{run_id}/retry", response_model=RunResponse)
async def retry_run(
    run_id: UUID,
    db: AsyncSession = Depends(get_db_session),
    redis: aioredis.Redis = Depends(get_redis),
) -> RunResponse:
    """Retry a failed run.

    Only runs in plan_failed, verification_failed, or review_failed
    states can be retried.
    """
    engine = await get_run_engine(db)
    try:
        response = await engine.retry_run(run_id)
    except ValueError as e:
        raise HTTPException(status_code=409, detail=str(e))

    # Re-enqueue for worker
    run = await run_queries.get_run(db, run_id)
    if run is not None:
        payload = {
            "task_type": run.task_type,
            "repo": run.repo,
            "base_branch": run.base_branch,
            "title": run.title,
            "prompt": run.prompt,
            "mcp_profile": run.mcp_profile,
            "_run_id": str(run.id),
        }
        await redis.lpush(QUEUE_KEY, json.dumps(payload))

    return response
