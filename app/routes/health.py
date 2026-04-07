"""Health check endpoint."""

from fastapi import APIRouter

router = APIRouter()


@router.get("/health")
async def health_check() -> dict:
    """Return service health status and version."""
    return {"status": "ok", "version": "0.1.0"}
