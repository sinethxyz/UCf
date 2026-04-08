"""Run management endpoints."""

import json
from uuid import UUID

import redis.asyncio as aioredis
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.deps import get_artifact_store, get_db_session, get_redis, get_run_engine
from foundry.contracts.review_models import ReviewVerdict
from foundry.contracts.run_models import (
    RunArtifact,
    RunEvent,
    RunResponse,
    VerificationCheckResult,
    VerificationResponse,
)
from foundry.contracts.shared import RunState
from foundry.contracts.task_types import TaskRequest
from foundry.db.queries import artifacts as artifact_queries
from foundry.db.queries import runs as run_queries
from foundry.orchestration.run_engine import RunEngine
from foundry.storage.artifact_store import ArtifactStore

router = APIRouter()

QUEUE_KEY = "foundry:runs"

# Content-type mapping for artifact file extensions.
_CONTENT_TYPES: dict[str, str] = {
    ".json": "application/json",
    ".jsonl": "application/x-ndjson",
    ".patch": "text/plain",
    ".diff": "text/plain",
    ".txt": "text/plain",
    ".md": "text/markdown",
    ".log": "text/plain",
}


def _run_to_response(run) -> RunResponse:
    """Map a Run ORM instance to a RunResponse contract."""
    event_count = len(run.events) if run.events else 0
    artifact_count = len(run.artifacts) if run.artifacts else 0
    return RunResponse(
        id=run.id,
        task_type=run.task_type,
        repo=run.repo,
        base_branch=run.base_branch,
        title=run.title,
        state=RunState(run.state),
        worktree_path=run.worktree_path,
        branch_name=run.branch_name,
        pr_url=run.pr_url,
        error_message=run.error_message,
        created_at=run.created_at,
        updated_at=run.updated_at,
        completed_at=run.completed_at,
        event_count=event_count,
        artifact_count=artifact_count,
        metadata=run.metadata_ if run.metadata_ else {},
    )


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
    """Get run status and metadata including summary counts."""
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
            state=RunState(e.state),
            message=e.message,
            metadata=e.metadata_ if e.metadata_ else {},
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
    """Get all artifact metadata for a run.

    Returns metadata only — artifact contents are not inlined.
    Use GET /runs/{run_id}/artifacts/{artifact_id} to download contents.
    """
    run = await run_queries.get_run(db, run_id)
    if run is None:
        raise HTTPException(status_code=404, detail="Run not found")

    artifacts = await artifact_queries.get_artifacts(db, run_id)
    return [RunArtifact.model_validate(a) for a in artifacts]


@router.get("/runs/{run_id}/artifacts/{artifact_id}")
async def get_artifact_content(
    run_id: UUID,
    artifact_id: UUID,
    db: AsyncSession = Depends(get_db_session),
    store: ArtifactStore = Depends(get_artifact_store),
) -> Response:
    """Download artifact contents with appropriate Content-Type.

    Looks up the artifact metadata from the DB, verifies it belongs to
    the specified run, then reads the raw content from the artifact store.
    """
    run = await run_queries.get_run(db, run_id)
    if run is None:
        raise HTTPException(status_code=404, detail="Run not found")

    artifact = await artifact_queries.get_artifact(db, artifact_id)
    if artifact is None or artifact.run_id != run_id:
        raise HTTPException(status_code=404, detail="Artifact not found")

    try:
        content = await store.retrieve(artifact.storage_path)
    except FileNotFoundError:
        raise HTTPException(
            status_code=404,
            detail="Artifact file not found in storage",
        )

    # Determine content type from file extension.
    suffix = "." + artifact.storage_path.rsplit(".", 1)[-1] if "." in artifact.storage_path else ""
    content_type = _CONTENT_TYPES.get(suffix, "application/octet-stream")

    return Response(content=content, media_type=content_type)


@router.get("/runs/{run_id}/verification", response_model=VerificationResponse)
async def get_run_verification(
    run_id: UUID,
    db: AsyncSession = Depends(get_db_session),
    store: ArtifactStore = Depends(get_artifact_store),
) -> VerificationResponse:
    """Get structured verification results for a run.

    Looks for the verification.json artifact, parses it, and returns
    structured check results. Returns 404 if the run has not yet
    reached the verification phase.
    """
    run = await run_queries.get_run(db, run_id)
    if run is None:
        raise HTTPException(status_code=404, detail="Run not found")

    # Find the verification artifact by type.
    artifacts = await artifact_queries.get_artifacts(db, run_id)
    verification_artifact = None
    for a in artifacts:
        if a.artifact_type == "verification":
            verification_artifact = a
            break

    if verification_artifact is None:
        raise HTTPException(
            status_code=404,
            detail="Run has not reached the verification phase",
        )

    try:
        raw = await store.retrieve(verification_artifact.storage_path)
    except FileNotFoundError:
        raise HTTPException(
            status_code=404,
            detail="Verification artifact file not found in storage",
        )

    data = json.loads(raw)

    # Support both wrapped {"checks": [...]} and flat list formats.
    if isinstance(data, list):
        checks_raw = data
    else:
        checks_raw = data.get("checks", [])

    all_passed = all(c.get("passed", False) for c in checks_raw)
    checks = [
        VerificationCheckResult(
            check_type=c.get("check_type", "unknown"),
            passed=c.get("passed", False),
            output=c.get("output"),
            duration_ms=c.get("duration_ms"),
        )
        for c in checks_raw
    ]

    return VerificationResponse(run_id=run_id, passed=all_passed, checks=checks)


@router.get("/runs/{run_id}/review")
async def get_run_review(
    run_id: UUID,
    db: AsyncSession = Depends(get_db_session),
    store: ArtifactStore = Depends(get_artifact_store),
) -> dict:
    """Get structured review verdict(s) for a run.

    Fetches the review.json artifact and parses it into a ReviewVerdict.
    Also includes migration_guard_review.json if present. Returns 404
    if the run has not reached the review phase.
    """
    run = await run_queries.get_run(db, run_id)
    if run is None:
        raise HTTPException(status_code=404, detail="Run not found")

    artifacts = await artifact_queries.get_artifacts(db, run_id)

    review_artifact = None
    migration_guard_artifact = None
    for a in artifacts:
        if a.artifact_type == "review":
            # Prefer the main review; migration guard has a different path.
            if "migration_guard" in a.storage_path:
                migration_guard_artifact = a
            else:
                review_artifact = a

    if review_artifact is None:
        raise HTTPException(
            status_code=404,
            detail="Run has not reached the review phase",
        )

    try:
        raw = await store.retrieve(review_artifact.storage_path)
    except FileNotFoundError:
        raise HTTPException(
            status_code=404,
            detail="Review artifact file not found in storage",
        )

    review_data = json.loads(raw)
    review_verdict = ReviewVerdict.model_validate(review_data, strict=False)

    result: dict = {"review": review_verdict.model_dump(mode="json")}

    # Include migration guard review if it exists.
    if migration_guard_artifact is not None:
        try:
            mg_raw = await store.retrieve(migration_guard_artifact.storage_path)
            mg_data = json.loads(mg_raw)
            mg_verdict = ReviewVerdict.model_validate(mg_data, strict=False)
            result["migration_guard_review"] = mg_verdict.model_dump(mode="json")
        except (FileNotFoundError, json.JSONDecodeError, Exception):
            # Migration guard file missing or corrupt — include as null.
            result["migration_guard_review"] = None
    else:
        result["migration_guard_review"] = None

    return result


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
