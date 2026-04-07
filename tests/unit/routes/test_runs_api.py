"""Tests for the /runs API endpoints using FastAPI TestClient with mocked deps."""

import json
import uuid
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.deps import get_db_session, get_redis
from app.routes import runs as runs_module
from foundry.contracts.run_models import RunResponse
from foundry.contracts.shared import RunState


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_run_orm(
    run_id: uuid.UUID | None = None,
    state: str = "queued",
    task_type: str = "bug_fix",
    title: str = "Fix pagination bug",
    error_message: str | None = None,
    pr_url: str | None = None,
):
    """Create a fake Run ORM-like object for dependency overrides."""
    now = datetime.now(timezone.utc)
    run = MagicMock()
    run.id = run_id or uuid.uuid4()
    run.task_type = task_type
    run.repo = "unicorn-app"
    run.base_branch = "main"
    run.title = title
    run.state = state
    run.branch_name = None
    run.pr_url = pr_url
    run.error_message = error_message
    run.created_at = now
    run.updated_at = now
    run.completed_at = None
    # ORM uses metadata_ but Pydantic from_attributes looks for field name "metadata"
    run.metadata = {}
    run.metadata_ = {}
    run.prompt = "Fix the off-by-one error"
    run.mcp_profile = "none"
    run.worktree_path = None
    run.events = []
    run.artifacts = []
    return run


def _make_event_orm(run_id: uuid.UUID, state: str = "queued", message: str = "Created"):
    """Create a fake RunEvent ORM-like object."""
    evt = MagicMock()
    evt.run_id = run_id
    evt.created_at = datetime.now(timezone.utc)
    evt.state = state
    evt.message = message
    evt.metadata_ = {}
    evt.duration_ms = None
    evt.model_used = None
    evt.tokens_in = None
    evt.tokens_out = None
    return evt


def _make_artifact_orm(run_id: uuid.UUID):
    """Create a fake RunArtifact ORM-like object."""
    art = MagicMock()
    art.id = uuid.uuid4()
    art.run_id = run_id
    art.artifact_type = "plan"
    art.storage_path = f"runs/{run_id}/plan.json"
    art.size_bytes = 1024
    art.checksum = "abc123"
    art.created_at = datetime.now(timezone.utc)
    return art


def _make_run_response(run_id: uuid.UUID, state: RunState = RunState.QUEUED) -> RunResponse:
    """Create a RunResponse contract instance."""
    now = datetime.now(timezone.utc)
    return RunResponse(
        id=run_id,
        task_type="bug_fix",
        repo="unicorn-app",
        base_branch="main",
        title="Fix pagination bug",
        state=state,
        created_at=now,
        updated_at=now,
    )


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def run_id():
    return uuid.uuid4()


@pytest.fixture
def mock_db():
    return AsyncMock()


@pytest.fixture
def mock_redis():
    redis = AsyncMock()
    redis.lpush = AsyncMock(return_value=1)
    return redis


@pytest.fixture
def client(mock_db, mock_redis):
    @asynccontextmanager
    async def noop_lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
        yield

    app = FastAPI(lifespan=noop_lifespan)
    app.include_router(runs_module.router, prefix="/v1")

    async def override_db():
        yield mock_db

    async def override_redis():
        return mock_redis

    app.dependency_overrides[get_db_session] = override_db
    app.dependency_overrides[get_redis] = override_redis

    with TestClient(app, raise_server_exceptions=False) as c:
        yield c

    app.dependency_overrides.clear()


# ---------------------------------------------------------------------------
# POST /v1/runs
# ---------------------------------------------------------------------------

class TestCreateRun:
    def test_create_run_success(self, client, mock_db, mock_redis, run_id):
        run = _make_run_orm(run_id=run_id)
        with patch.object(runs_module, "run_queries") as mock_rq:
            mock_rq.create_run = AsyncMock(return_value=run)
            resp = client.post("/v1/runs", json={
                "task_type": "bug_fix",
                "repo": "unicorn-app",
                "title": "Fix pagination bug",
                "prompt": "Fix the off-by-one error",
                "mcp_profile": "none",
            })

        assert resp.status_code == 201
        body = resp.json()
        assert body["id"] == str(run_id)
        assert body["state"] == "queued"
        assert body["task_type"] == "bug_fix"

    def test_create_run_enqueues_to_redis(self, client, mock_redis, run_id):
        run = _make_run_orm(run_id=run_id)
        with patch.object(runs_module, "run_queries") as mock_rq:
            mock_rq.create_run = AsyncMock(return_value=run)
            client.post("/v1/runs", json={
                "task_type": "bug_fix",
                "repo": "unicorn-app",
                "title": "Fix pagination bug",
                "prompt": "Fix the off-by-one error",
                "mcp_profile": "none",
            })

        mock_redis.lpush.assert_called_once()
        call_args = mock_redis.lpush.call_args
        assert call_args[0][0] == "foundry:runs"
        payload = json.loads(call_args[0][1])
        assert payload["_run_id"] == str(run_id)
        assert payload["task_type"] == "bug_fix"

    def test_create_run_invalid_task_type(self, client):
        resp = client.post("/v1/runs", json={
            "task_type": "nonexistent",
            "repo": "unicorn-app",
            "title": "Bad task",
            "prompt": "This should fail",
        })
        assert resp.status_code == 422


# ---------------------------------------------------------------------------
# GET /v1/runs/{id}
# ---------------------------------------------------------------------------

class TestGetRun:
    def test_get_run_success(self, client, run_id):
        run = _make_run_orm(run_id=run_id)
        with patch.object(runs_module, "run_queries") as mock_rq:
            mock_rq.get_run = AsyncMock(return_value=run)
            resp = client.get(f"/v1/runs/{run_id}")

        assert resp.status_code == 200
        assert resp.json()["id"] == str(run_id)

    def test_get_run_not_found(self, client):
        fake_id = uuid.uuid4()
        with patch.object(runs_module, "run_queries") as mock_rq:
            mock_rq.get_run = AsyncMock(return_value=None)
            resp = client.get(f"/v1/runs/{fake_id}")

        assert resp.status_code == 404
        assert "not found" in resp.json()["detail"].lower()


# ---------------------------------------------------------------------------
# GET /v1/runs/{id}/events
# ---------------------------------------------------------------------------

class TestGetRunEvents:
    def test_get_events_success(self, client, run_id):
        run = _make_run_orm(run_id=run_id)
        events = [
            _make_event_orm(run_id, "queued", "Run created"),
            _make_event_orm(run_id, "creating_worktree", "Creating worktree"),
        ]
        with patch.object(runs_module, "run_queries") as mock_rq:
            mock_rq.get_run = AsyncMock(return_value=run)
            mock_rq.get_run_events = AsyncMock(return_value=events)
            resp = client.get(f"/v1/runs/{run_id}/events")

        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 2
        assert data[0]["state"] == "queued"
        assert data[1]["state"] == "creating_worktree"

    def test_get_events_run_not_found(self, client):
        fake_id = uuid.uuid4()
        with patch.object(runs_module, "run_queries") as mock_rq:
            mock_rq.get_run = AsyncMock(return_value=None)
            resp = client.get(f"/v1/runs/{fake_id}/events")

        assert resp.status_code == 404


# ---------------------------------------------------------------------------
# GET /v1/runs/{id}/artifacts
# ---------------------------------------------------------------------------

class TestGetRunArtifacts:
    def test_get_artifacts_success(self, client, run_id):
        run = _make_run_orm(run_id=run_id)
        artifacts = [_make_artifact_orm(run_id)]
        with (
            patch.object(runs_module, "run_queries") as mock_rq,
            patch.object(runs_module, "artifact_queries") as mock_aq,
        ):
            mock_rq.get_run = AsyncMock(return_value=run)
            mock_aq.get_artifacts = AsyncMock(return_value=artifacts)
            resp = client.get(f"/v1/runs/{run_id}/artifacts")

        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 1
        assert data[0]["artifact_type"] == "plan"

    def test_get_artifacts_run_not_found(self, client):
        fake_id = uuid.uuid4()
        with patch.object(runs_module, "run_queries") as mock_rq:
            mock_rq.get_run = AsyncMock(return_value=None)
            resp = client.get(f"/v1/runs/{fake_id}/artifacts")

        assert resp.status_code == 404


# ---------------------------------------------------------------------------
# POST /v1/runs/{id}/cancel
# ---------------------------------------------------------------------------

class TestCancelRun:
    def test_cancel_run_success(self, client, run_id):
        response = _make_run_response(run_id, RunState.CANCELLED)
        mock_engine = AsyncMock()
        mock_engine.cancel_run = AsyncMock(return_value=response)

        with patch.object(runs_module, "get_run_engine", new_callable=AsyncMock, return_value=mock_engine):
            resp = client.post(f"/v1/runs/{run_id}/cancel")

        assert resp.status_code == 200
        assert resp.json()["state"] == "cancelled"

    def test_cancel_run_conflict(self, client, run_id):
        mock_engine = AsyncMock()
        mock_engine.cancel_run = AsyncMock(side_effect=ValueError("Run already completed"))

        with patch.object(runs_module, "get_run_engine", new_callable=AsyncMock, return_value=mock_engine):
            resp = client.post(f"/v1/runs/{run_id}/cancel")

        assert resp.status_code == 409
        assert "already completed" in resp.json()["detail"]


# ---------------------------------------------------------------------------
# POST /v1/runs/{id}/retry
# ---------------------------------------------------------------------------

class TestRetryRun:
    def test_retry_run_success(self, client, mock_redis, run_id):
        response = _make_run_response(run_id, RunState.QUEUED)
        mock_engine = AsyncMock()
        mock_engine.retry_run = AsyncMock(return_value=response)
        run = _make_run_orm(run_id=run_id, state="queued")

        with (
            patch.object(runs_module, "get_run_engine", new_callable=AsyncMock, return_value=mock_engine),
            patch.object(runs_module, "run_queries") as mock_rq,
        ):
            mock_rq.get_run = AsyncMock(return_value=run)
            resp = client.post(f"/v1/runs/{run_id}/retry")

        assert resp.status_code == 200
        assert resp.json()["state"] == "queued"
        mock_redis.lpush.assert_called_once()

    def test_retry_run_conflict(self, client, run_id):
        mock_engine = AsyncMock()
        mock_engine.retry_run = AsyncMock(side_effect=ValueError("Run is not retryable"))

        with patch.object(runs_module, "get_run_engine", new_callable=AsyncMock, return_value=mock_engine):
            resp = client.post(f"/v1/runs/{run_id}/retry")

        assert resp.status_code == 409

    def test_retry_run_re_enqueues_to_redis(self, client, mock_redis, run_id):
        response = _make_run_response(run_id, RunState.QUEUED)
        mock_engine = AsyncMock()
        mock_engine.retry_run = AsyncMock(return_value=response)
        run = _make_run_orm(run_id=run_id, state="queued")

        with (
            patch.object(runs_module, "get_run_engine", new_callable=AsyncMock, return_value=mock_engine),
            patch.object(runs_module, "run_queries") as mock_rq,
        ):
            mock_rq.get_run = AsyncMock(return_value=run)
            client.post(f"/v1/runs/{run_id}/retry")

        call_args = mock_redis.lpush.call_args
        payload = json.loads(call_args[0][1])
        assert payload["_run_id"] == str(run_id)
        assert payload["task_type"] == "bug_fix"
