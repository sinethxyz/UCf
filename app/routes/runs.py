"""Run management endpoints."""

from fastapi import APIRouter

router = APIRouter()


@router.post("/runs")
async def create_run() -> dict:
    """Submit a new task for execution."""
    raise NotImplementedError


@router.get("/runs/{run_id}")
async def get_run(run_id: str) -> dict:
    """Get run status and metadata."""
    raise NotImplementedError


@router.post("/runs/{run_id}/cancel")
async def cancel_run(run_id: str) -> dict:
    """Cancel a running task."""
    raise NotImplementedError


@router.post("/runs/{run_id}/retry")
async def retry_run(run_id: str) -> dict:
    """Retry a failed run."""
    raise NotImplementedError


@router.get("/runs/{run_id}/events")
async def get_run_events(run_id: str) -> dict:
    """Get all events for a run."""
    raise NotImplementedError


@router.get("/runs/{run_id}/artifacts")
async def get_run_artifacts(run_id: str) -> dict:
    """Get all artifacts for a run."""
    raise NotImplementedError
