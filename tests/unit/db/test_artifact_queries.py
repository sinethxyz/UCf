"""Tests for foundry.db.queries.artifacts."""

import uuid

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from foundry.contracts.task_types import TaskRequest
from foundry.db.models import RunArtifact
from foundry.db.queries.artifacts import get_artifact, get_artifacts, store_artifact
from foundry.db.queries.runs import create_run


# -- store_artifact -----------------------------------------------------------


async def test_store_artifact_creates_record(
    async_session: AsyncSession, sample_task_request: TaskRequest
):
    run = await create_run(async_session, sample_task_request)

    artifact = await store_artifact(
        async_session,
        run_id=run.id,
        artifact_type="plan",
        storage_path="runs/abc/plan.json",
        size_bytes=1024,
        checksum="sha256:abc123",
    )

    assert isinstance(artifact, RunArtifact)
    assert artifact.id is not None
    assert artifact.run_id == run.id
    assert artifact.artifact_type == "plan"
    assert artifact.storage_path == "runs/abc/plan.json"
    assert artifact.size_bytes == 1024
    assert artifact.checksum == "sha256:abc123"
    assert artifact.created_at is not None


async def test_store_artifact_optional_fields(
    async_session: AsyncSession, sample_task_request: TaskRequest
):
    run = await create_run(async_session, sample_task_request)

    artifact = await store_artifact(
        async_session,
        run_id=run.id,
        artifact_type="diff",
        storage_path="runs/abc/diff.patch",
    )

    assert artifact.size_bytes is None
    assert artifact.checksum is None


# -- get_artifacts ------------------------------------------------------------


async def test_get_artifacts_returns_all_for_run(
    async_session: AsyncSession, sample_task_request: TaskRequest
):
    run = await create_run(async_session, sample_task_request)

    await store_artifact(
        async_session, run.id, "plan", "runs/abc/plan.json", 100, "c1"
    )
    await store_artifact(
        async_session, run.id, "diff", "runs/abc/diff.patch", 200, "c2"
    )
    await store_artifact(
        async_session, run.id, "review", "runs/abc/review.json", 300, "c3"
    )

    artifacts = await get_artifacts(async_session, run.id)
    assert len(artifacts) == 3
    types = [a.artifact_type for a in artifacts]
    assert "plan" in types
    assert "diff" in types
    assert "review" in types


async def test_get_artifacts_ordered_by_created_at(
    async_session: AsyncSession, sample_task_request: TaskRequest
):
    run = await create_run(async_session, sample_task_request)

    for t in ["plan", "diff", "review"]:
        await store_artifact(async_session, run.id, t, f"runs/x/{t}.json")

    artifacts = await get_artifacts(async_session, run.id)
    for i in range(len(artifacts) - 1):
        assert artifacts[i].created_at <= artifacts[i + 1].created_at


async def test_get_artifacts_empty_for_unknown_run(async_session: AsyncSession):
    artifacts = await get_artifacts(async_session, uuid.uuid4())
    assert artifacts == []


async def test_get_artifacts_isolates_runs(
    async_session: AsyncSession, sample_task_request: TaskRequest
):
    run1 = await create_run(async_session, sample_task_request)
    run2 = await create_run(async_session, sample_task_request)

    await store_artifact(async_session, run1.id, "plan", "r1/plan.json")
    await store_artifact(async_session, run2.id, "diff", "r2/diff.patch")

    arts1 = await get_artifacts(async_session, run1.id)
    arts2 = await get_artifacts(async_session, run2.id)
    assert len(arts1) == 1
    assert len(arts2) == 1
    assert arts1[0].artifact_type == "plan"
    assert arts2[0].artifact_type == "diff"


# -- get_artifact -------------------------------------------------------------


async def test_get_artifact_by_id(
    async_session: AsyncSession, sample_task_request: TaskRequest
):
    run = await create_run(async_session, sample_task_request)
    stored = await store_artifact(
        async_session, run.id, "plan", "runs/abc/plan.json", 512, "checksum"
    )

    fetched = await get_artifact(async_session, stored.id)
    assert fetched is not None
    assert fetched.id == stored.id
    assert fetched.artifact_type == "plan"
    assert fetched.storage_path == "runs/abc/plan.json"


async def test_get_artifact_returns_none_for_missing(async_session: AsyncSession):
    result = await get_artifact(async_session, uuid.uuid4())
    assert result is None
