"""Review endpoints.

Debug-only endpoint for standalone blind diff review outside the run
lifecycle. Accepts a raw diff, runs the reviewer subagent, and returns
a structured ReviewVerdict.
"""

import logging
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.deps import get_artifact_store, get_db_session
from foundry.contracts.review_models import ReviewVerdict
from foundry.db.queries import artifacts as artifact_queries
from foundry.storage.artifact_store import ArtifactStore, ArtifactType
from foundry.tasks.review_diff import execute_standalone_review

logger = logging.getLogger(__name__)

router = APIRouter()


class ReviewRequest(BaseModel):
    """Request body for standalone code review."""

    diff: str
    title: str = ""
    description: str = ""
    run_id: UUID | None = Field(
        default=None,
        description="Optional run ID to associate the review artifact with.",
    )


@router.post("/reviews", response_model=ReviewVerdict)
async def create_review(
    request: ReviewRequest,
    db: AsyncSession = Depends(get_db_session),
) -> ReviewVerdict:
    """Submit a diff for independent blind review.

    Runs the reviewer subagent against the provided diff without
    requiring a full run lifecycle. The reviewer sees ONLY the diff,
    title, and description — never the plan.

    If run_id is provided, the review artifact is persisted and
    registered in the database for that run.
    """
    if not request.diff.strip():
        raise HTTPException(status_code=422, detail="diff must not be empty")

    artifact_store: ArtifactStore | None = None
    if request.run_id is not None:
        artifact_store = get_artifact_store()

    verdict = await execute_standalone_review(
        diff=request.diff,
        title=request.title,
        description=request.description,
        run_id=request.run_id,
        artifact_store=artifact_store,
    )

    # Register artifact metadata in DB if run_id was provided
    if request.run_id is not None and artifact_store is not None:
        review_json = verdict.model_dump_json(indent=2)
        storage_path = f"runs/{request.run_id}/review.json"
        await artifact_queries.store_artifact(
            db,
            request.run_id,
            ArtifactType.REVIEW.value,
            storage_path,
            len(review_json.encode()),
            artifact_store.get_checksum(review_json),
        )

    return verdict
