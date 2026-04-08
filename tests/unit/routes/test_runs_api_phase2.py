"""Tests for Phase 2 run-detail API endpoints.

Covers:
- GET /runs/{id} — enhanced response with worktree_path, event_count, artifact_count
- GET /runs/{id}/events — complete event timeline
- GET /runs/{id}/artifacts — artifact metadata list
- GET /runs/{id}/artifacts/{artifact_id} — artifact content download
- GET /runs/{id}/verification — convenience endpoint for verification results
- GET /runs/{id}/review — convenience endpoint for review verdict
- 404 cases for missing runs, missing artifacts, and not-yet-reached phases
"""

import json
import sys
import types
import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

# Stub heavy third-party modules that are not available in the test environment.
for _mod_name in (
    "claude_agent_sdk",
    "asyncpg",
    "boto3",
    "anthropic",
):
    if _mod_name not in sys.modules:
        sys.modules[_mod_name] = types.ModuleType(_mod_name)

# claude_agent_sdk needs specific names.
_cas = sys.modules["claude_agent_sdk"]
for _attr in ("ClaudeAgentOptions", "ResultMessage", "query"):
    if not hasattr(_cas, _attr):
        setattr(_cas, _attr, MagicMock())

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import JSON, event
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.deps import get_artifact_store, get_db_session
from app.main import create_app
from foundry.db import models as db_models
from foundry.db.models import Base, Run, RunArtifact, RunEvent
from foundry.storage.artifact_store import ArtifactStore


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
async def engine():
    """Create an async in-memory SQLite engine with JSONB→JSON adaptation."""
    eng = create_async_engine("sqlite+aiosqlite://", echo=False)

    @event.listens_for(eng.sync_engine, "connect")
    def _enable_fk(dbapi_conn, _record):
        cursor = dbapi_conn.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    # Patch JSONB → JSON for SQLite compatibility.
    for table in Base.metadata.tables.values():
        for column in table.columns:
            if isinstance(column.type, JSONB):
                column.type = JSON()

    async with eng.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    yield eng
    await eng.dispose()


@pytest.fixture
async def session_factory(engine):
    """Return an async session factory bound to the in-memory engine."""
    return async_sessionmaker(engine, expire_on_commit=False)


@pytest.fixture
async def db_session(session_factory):
    """Yield a single async session for direct DB manipulation in tests."""
    async with session_factory() as session:
        yield session


@pytest.fixture
def mock_artifact_store():
    """Return a mock ArtifactStore with configurable retrieve behaviour."""
    store = AsyncMock(spec=ArtifactStore)
    store.retrieve = AsyncMock()
    return store


@pytest.fixture
async def app(session_factory, mock_artifact_store):
    """Create a FastAPI test app with overridden DB and artifact-store deps."""
    application = create_app()

    async def _override_db():
        async with session_factory() as session:
            yield session
            await session.commit()

    def _override_store():
        return mock_artifact_store

    application.dependency_overrides[get_db_session] = _override_db
    application.dependency_overrides[get_artifact_store] = _override_store
    return application


@pytest.fixture
async def client(app):
    """Yield an httpx AsyncClient wired to the test app."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _now() -> datetime:
    return datetime.now(timezone.utc)


async def _create_run(session: AsyncSession, **overrides) -> Run:
    """Insert a Run row and return it."""
    defaults = {
        "task_type": "bug_fix",
        "repo": "unicorn-app",
        "base_branch": "main",
        "title": "Test run",
        "prompt": "Fix the bug",
        "state": "queued",
        "mcp_profile": "none",
        "metadata_": {},
        "created_at": _now(),
        "updated_at": _now(),
    }
    defaults.update(overrides)
    run = Run(**defaults)
    session.add(run)
    await session.flush()
    return run


async def _create_event(session: AsyncSession, run_id: uuid.UUID, **overrides) -> RunEvent:
    """Insert a RunEvent row and return it."""
    defaults = {
        "run_id": run_id,
        "state": "queued",
        "message": "Run queued",
        "metadata_": {},
        "created_at": _now(),
    }
    defaults.update(overrides)
    evt = RunEvent(**defaults)
    session.add(evt)
    await session.flush()
    return evt


async def _create_artifact(
    session: AsyncSession, run_id: uuid.UUID, **overrides
) -> RunArtifact:
    """Insert a RunArtifact row and return it."""
    defaults = {
        "run_id": run_id,
        "artifact_type": "plan",
        "storage_path": f"runs/{run_id}/plan.json",
        "size_bytes": 128,
        "checksum": "abc123",
        "created_at": _now(),
    }
    defaults.update(overrides)
    art = RunArtifact(**defaults)
    session.add(art)
    await session.flush()
    return art


# ---------------------------------------------------------------------------
# GET /runs/{id} — Enhanced RunResponse
# ---------------------------------------------------------------------------


class TestGetRunEnhanced:
    """GET /v1/runs/{id} returns worktree_path, event_count, artifact_count."""

    async def test_run_response_includes_worktree_path(self, client, db_session):
        run = await _create_run(
            db_session,
            worktree_path="/tmp/foundry-worktrees/abc",
            branch_name="foundry/bug-fix-test",
        )
        await db_session.commit()

        resp = await client.get(f"/v1/runs/{run.id}")
        assert resp.status_code == 200
        body = resp.json()
        assert body["worktree_path"] == "/tmp/foundry-worktrees/abc"
        assert body["branch_name"] == "foundry/bug-fix-test"

    async def test_run_response_includes_summary_counts(self, client, db_session):
        run = await _create_run(db_session)
        await _create_event(db_session, run.id, state="queued", message="Queued")
        await _create_event(db_session, run.id, state="planning", message="Planning")
        await _create_artifact(db_session, run.id)
        await _create_artifact(
            db_session, run.id,
            artifact_type="diff",
            storage_path=f"runs/{run.id}/diff.patch",
        )
        await db_session.commit()

        resp = await client.get(f"/v1/runs/{run.id}")
        assert resp.status_code == 200
        body = resp.json()
        assert body["event_count"] == 2
        assert body["artifact_count"] == 2

    async def test_run_response_zero_counts_when_empty(self, client, db_session):
        run = await _create_run(db_session)
        await db_session.commit()

        resp = await client.get(f"/v1/runs/{run.id}")
        assert resp.status_code == 200
        body = resp.json()
        assert body["event_count"] == 0
        assert body["artifact_count"] == 0

    async def test_run_response_includes_error_message(self, client, db_session):
        run = await _create_run(
            db_session,
            state="errored",
            error_message="Build failed",
            completed_at=_now(),
        )
        await db_session.commit()

        resp = await client.get(f"/v1/runs/{run.id}")
        assert resp.status_code == 200
        body = resp.json()
        assert body["state"] == "errored"
        assert body["error_message"] == "Build failed"
        assert body["completed_at"] is not None

    async def test_run_response_includes_pr_url(self, client, db_session):
        run = await _create_run(
            db_session,
            state="completed",
            pr_url="https://github.com/org/repo/pull/42",
            completed_at=_now(),
        )
        await db_session.commit()

        resp = await client.get(f"/v1/runs/{run.id}")
        assert resp.status_code == 200
        body = resp.json()
        assert body["pr_url"] == "https://github.com/org/repo/pull/42"

    async def test_run_not_found_returns_404(self, client):
        fake_id = uuid.uuid4()
        resp = await client.get(f"/v1/runs/{fake_id}")
        assert resp.status_code == 404


# ---------------------------------------------------------------------------
# GET /runs/{id}/events
# ---------------------------------------------------------------------------


class TestGetRunEvents:
    """GET /v1/runs/{id}/events returns all events in chronological order."""

    async def test_returns_events_ordered(self, client, db_session):
        run = await _create_run(db_session)
        e1 = await _create_event(db_session, run.id, state="queued", message="Queued")
        e2 = await _create_event(
            db_session, run.id,
            state="planning",
            message="Planning started",
            model_used="claude-opus-4-6",
            tokens_in=100,
            tokens_out=500,
            duration_ms=1200,
        )
        await db_session.commit()

        resp = await client.get(f"/v1/runs/{run.id}/events")
        assert resp.status_code == 200
        events = resp.json()
        assert len(events) == 2
        assert events[0]["state"] == "queued"
        assert events[1]["state"] == "planning"
        assert events[1]["model_used"] == "claude-opus-4-6"
        assert events[1]["tokens_in"] == 100
        assert events[1]["tokens_out"] == 500
        assert events[1]["duration_ms"] == 1200

    async def test_events_run_not_found(self, client):
        resp = await client.get(f"/v1/runs/{uuid.uuid4()}/events")
        assert resp.status_code == 404


# ---------------------------------------------------------------------------
# GET /runs/{id}/artifacts
# ---------------------------------------------------------------------------


class TestGetRunArtifacts:
    """GET /v1/runs/{id}/artifacts returns artifact metadata list."""

    async def test_returns_artifact_metadata(self, client, db_session):
        run = await _create_run(db_session)
        art = await _create_artifact(
            db_session, run.id,
            artifact_type="plan",
            storage_path=f"runs/{run.id}/plan.json",
            size_bytes=256,
            checksum="deadbeef",
        )
        await db_session.commit()

        resp = await client.get(f"/v1/runs/{run.id}/artifacts")
        assert resp.status_code == 200
        artifacts = resp.json()
        assert len(artifacts) == 1
        assert artifacts[0]["artifact_type"] == "plan"
        assert artifacts[0]["size_bytes"] == 256
        assert artifacts[0]["checksum"] == "deadbeef"
        assert artifacts[0]["id"] == str(art.id)

    async def test_artifacts_run_not_found(self, client):
        resp = await client.get(f"/v1/runs/{uuid.uuid4()}/artifacts")
        assert resp.status_code == 404


# ---------------------------------------------------------------------------
# GET /runs/{id}/artifacts/{artifact_id} — Content download
# ---------------------------------------------------------------------------


class TestGetArtifactContent:
    """GET /v1/runs/{id}/artifacts/{artifact_id} downloads artifact content."""

    async def test_returns_json_content_type(self, client, db_session, mock_artifact_store):
        run = await _create_run(db_session)
        art = await _create_artifact(
            db_session, run.id,
            artifact_type="plan",
            storage_path=f"runs/{run.id}/plan.json",
        )
        await db_session.commit()

        plan_data = {"steps": [{"file_path": "main.go", "action": "modify"}]}
        mock_artifact_store.retrieve.return_value = json.dumps(plan_data).encode()

        resp = await client.get(f"/v1/runs/{run.id}/artifacts/{art.id}")
        assert resp.status_code == 200
        assert resp.headers["content-type"] == "application/json"
        assert resp.json() == plan_data

    async def test_returns_text_for_patch(self, client, db_session, mock_artifact_store):
        run = await _create_run(db_session)
        art = await _create_artifact(
            db_session, run.id,
            artifact_type="diff",
            storage_path=f"runs/{run.id}/diff.patch",
        )
        await db_session.commit()

        patch_content = b"--- a/file.go\n+++ b/file.go\n@@ -1 +1 @@\n-old\n+new"
        mock_artifact_store.retrieve.return_value = patch_content

        resp = await client.get(f"/v1/runs/{run.id}/artifacts/{art.id}")
        assert resp.status_code == 200
        assert resp.headers["content-type"] == "text/plain; charset=utf-8"
        assert resp.text == patch_content.decode()

    async def test_returns_ndjson_for_jsonl(self, client, db_session, mock_artifact_store):
        run = await _create_run(db_session)
        art = await _create_artifact(
            db_session, run.id,
            artifact_type="extraction",
            storage_path=f"runs/{run.id}/extraction.jsonl",
        )
        await db_session.commit()

        mock_artifact_store.retrieve.return_value = b'{"a":1}\n{"b":2}\n'

        resp = await client.get(f"/v1/runs/{run.id}/artifacts/{art.id}")
        assert resp.status_code == 200
        assert "application/x-ndjson" in resp.headers["content-type"]

    async def test_artifact_not_found_returns_404(self, client, db_session):
        run = await _create_run(db_session)
        await db_session.commit()

        resp = await client.get(f"/v1/runs/{run.id}/artifacts/{uuid.uuid4()}")
        assert resp.status_code == 404
        assert "Artifact not found" in resp.json()["detail"]

    async def test_artifact_wrong_run_returns_404(self, client, db_session):
        """Artifact exists but belongs to a different run."""
        run1 = await _create_run(db_session)
        run2 = await _create_run(db_session)
        art = await _create_artifact(db_session, run2.id)
        await db_session.commit()

        resp = await client.get(f"/v1/runs/{run1.id}/artifacts/{art.id}")
        assert resp.status_code == 404

    async def test_artifact_file_missing_returns_404(self, client, db_session, mock_artifact_store):
        run = await _create_run(db_session)
        art = await _create_artifact(db_session, run.id)
        await db_session.commit()

        mock_artifact_store.retrieve.side_effect = FileNotFoundError("gone")

        resp = await client.get(f"/v1/runs/{run.id}/artifacts/{art.id}")
        assert resp.status_code == 404
        assert "not found in storage" in resp.json()["detail"]

    async def test_run_not_found_returns_404(self, client):
        resp = await client.get(f"/v1/runs/{uuid.uuid4()}/artifacts/{uuid.uuid4()}")
        assert resp.status_code == 404
        assert "Run not found" in resp.json()["detail"]


# ---------------------------------------------------------------------------
# GET /runs/{id}/verification — Convenience endpoint
# ---------------------------------------------------------------------------


class TestGetRunVerification:
    """GET /v1/runs/{id}/verification returns structured verification results."""

    async def test_returns_verification_results(self, client, db_session, mock_artifact_store):
        run = await _create_run(db_session, state="verification_passed")
        await _create_artifact(
            db_session, run.id,
            artifact_type="verification",
            storage_path=f"runs/{run.id}/verification.json",
        )
        await db_session.commit()

        verification_data = {
            "checks": [
                {"check_type": "go_build", "passed": True, "output": "ok", "duration_ms": 3200},
                {"check_type": "go_test", "passed": True, "output": "PASS", "duration_ms": 5100},
                {"check_type": "go_vet", "passed": True, "output": "", "duration_ms": 800},
            ]
        }
        mock_artifact_store.retrieve.return_value = json.dumps(verification_data).encode()

        resp = await client.get(f"/v1/runs/{run.id}/verification")
        assert resp.status_code == 200
        body = resp.json()
        assert body["run_id"] == str(run.id)
        assert body["passed"] is True
        assert len(body["checks"]) == 3
        assert body["checks"][0]["check_type"] == "go_build"
        assert body["checks"][0]["passed"] is True
        assert body["checks"][0]["duration_ms"] == 3200

    async def test_returns_failed_when_any_check_fails(self, client, db_session, mock_artifact_store):
        run = await _create_run(db_session, state="verification_failed")
        await _create_artifact(
            db_session, run.id,
            artifact_type="verification",
            storage_path=f"runs/{run.id}/verification.json",
        )
        await db_session.commit()

        verification_data = {
            "checks": [
                {"check_type": "go_build", "passed": True, "output": "ok", "duration_ms": 1000},
                {"check_type": "go_test", "passed": False, "output": "FAIL: TestFoo", "duration_ms": 4000},
            ]
        }
        mock_artifact_store.retrieve.return_value = json.dumps(verification_data).encode()

        resp = await client.get(f"/v1/runs/{run.id}/verification")
        assert resp.status_code == 200
        body = resp.json()
        assert body["passed"] is False
        assert body["checks"][1]["passed"] is False
        assert "FAIL" in body["checks"][1]["output"]

    async def test_supports_flat_list_format(self, client, db_session, mock_artifact_store):
        """Verification data stored as a flat list (no wrapping object)."""
        run = await _create_run(db_session, state="verification_passed")
        await _create_artifact(
            db_session, run.id,
            artifact_type="verification",
            storage_path=f"runs/{run.id}/verification.json",
        )
        await db_session.commit()

        verification_data = [
            {"check_type": "go_build", "passed": True, "output": "ok"},
        ]
        mock_artifact_store.retrieve.return_value = json.dumps(verification_data).encode()

        resp = await client.get(f"/v1/runs/{run.id}/verification")
        assert resp.status_code == 200
        body = resp.json()
        assert body["passed"] is True
        assert len(body["checks"]) == 1

    async def test_verification_not_reached_returns_404(self, client, db_session):
        """Run exists but has no verification artifact yet."""
        run = await _create_run(db_session, state="planning")
        await db_session.commit()

        resp = await client.get(f"/v1/runs/{run.id}/verification")
        assert resp.status_code == 404
        assert "not reached the verification phase" in resp.json()["detail"]

    async def test_verification_file_missing_returns_404(self, client, db_session, mock_artifact_store):
        run = await _create_run(db_session, state="verification_passed")
        await _create_artifact(
            db_session, run.id,
            artifact_type="verification",
            storage_path=f"runs/{run.id}/verification.json",
        )
        await db_session.commit()

        mock_artifact_store.retrieve.side_effect = FileNotFoundError("gone")

        resp = await client.get(f"/v1/runs/{run.id}/verification")
        assert resp.status_code == 404
        assert "not found in storage" in resp.json()["detail"]

    async def test_verification_run_not_found(self, client):
        resp = await client.get(f"/v1/runs/{uuid.uuid4()}/verification")
        assert resp.status_code == 404
        assert "Run not found" in resp.json()["detail"]


# ---------------------------------------------------------------------------
# GET /runs/{id}/review — Convenience endpoint
# ---------------------------------------------------------------------------


class TestGetRunReview:
    """GET /v1/runs/{id}/review returns structured review verdict(s)."""

    async def test_returns_review_verdict(self, client, db_session, mock_artifact_store):
        run = await _create_run(db_session, state="completed")
        await _create_artifact(
            db_session, run.id,
            artifact_type="review",
            storage_path=f"runs/{run.id}/review.json",
        )
        await db_session.commit()

        review_data = {
            "verdict": "approve",
            "issues": [],
            "summary": "LGTM",
            "confidence": 0.95,
        }
        mock_artifact_store.retrieve.return_value = json.dumps(review_data).encode()

        resp = await client.get(f"/v1/runs/{run.id}/review")
        assert resp.status_code == 200
        body = resp.json()
        assert body["review"]["verdict"] == "approve"
        assert body["review"]["summary"] == "LGTM"
        assert body["review"]["confidence"] == 0.95
        assert body["review"]["issues"] == []
        assert body["migration_guard_review"] is None

    async def test_returns_review_with_issues(self, client, db_session, mock_artifact_store):
        run = await _create_run(db_session, state="review_failed")
        await _create_artifact(
            db_session, run.id,
            artifact_type="review",
            storage_path=f"runs/{run.id}/review.json",
        )
        await db_session.commit()

        review_data = {
            "verdict": "request_changes",
            "issues": [
                {
                    "severity": "major",
                    "file_path": "services/api/handler.go",
                    "line_range": "42-50",
                    "description": "Missing error check on DB call",
                    "suggestion": "Add `if err != nil` check",
                }
            ],
            "summary": "One major issue needs fixing",
            "confidence": 0.88,
        }
        mock_artifact_store.retrieve.return_value = json.dumps(review_data).encode()

        resp = await client.get(f"/v1/runs/{run.id}/review")
        assert resp.status_code == 200
        body = resp.json()
        assert body["review"]["verdict"] == "request_changes"
        assert len(body["review"]["issues"]) == 1
        assert body["review"]["issues"][0]["severity"] == "major"

    async def test_includes_migration_guard_review(self, client, db_session, mock_artifact_store):
        run = await _create_run(db_session, state="completed")
        await _create_artifact(
            db_session, run.id,
            artifact_type="review",
            storage_path=f"runs/{run.id}/review.json",
        )
        await _create_artifact(
            db_session, run.id,
            artifact_type="review",
            storage_path=f"runs/{run.id}/migration_guard_review.json",
        )
        await db_session.commit()

        review_data = {
            "verdict": "approve",
            "issues": [],
            "summary": "LGTM",
            "confidence": 0.95,
        }
        mg_data = {
            "verdict": "approve",
            "issues": [],
            "summary": "Migration is safe",
            "confidence": 0.90,
        }

        async def _retrieve(path: str) -> bytes:
            if "migration_guard" in path:
                return json.dumps(mg_data).encode()
            return json.dumps(review_data).encode()

        mock_artifact_store.retrieve.side_effect = _retrieve

        resp = await client.get(f"/v1/runs/{run.id}/review")
        assert resp.status_code == 200
        body = resp.json()
        assert body["review"]["verdict"] == "approve"
        assert body["migration_guard_review"] is not None
        assert body["migration_guard_review"]["verdict"] == "approve"
        assert body["migration_guard_review"]["summary"] == "Migration is safe"

    async def test_review_not_reached_returns_404(self, client, db_session):
        run = await _create_run(db_session, state="implementing")
        await db_session.commit()

        resp = await client.get(f"/v1/runs/{run.id}/review")
        assert resp.status_code == 404
        assert "not reached the review phase" in resp.json()["detail"]

    async def test_review_file_missing_returns_404(self, client, db_session, mock_artifact_store):
        run = await _create_run(db_session, state="completed")
        await _create_artifact(
            db_session, run.id,
            artifact_type="review",
            storage_path=f"runs/{run.id}/review.json",
        )
        await db_session.commit()

        mock_artifact_store.retrieve.side_effect = FileNotFoundError("gone")

        resp = await client.get(f"/v1/runs/{run.id}/review")
        assert resp.status_code == 404
        assert "not found in storage" in resp.json()["detail"]

    async def test_review_run_not_found(self, client):
        resp = await client.get(f"/v1/runs/{uuid.uuid4()}/review")
        assert resp.status_code == 404
        assert "Run not found" in resp.json()["detail"]

    async def test_migration_guard_file_missing_returns_null(
        self, client, db_session, mock_artifact_store,
    ):
        """Migration guard artifact record exists but file is missing."""
        run = await _create_run(db_session, state="completed")
        await _create_artifact(
            db_session, run.id,
            artifact_type="review",
            storage_path=f"runs/{run.id}/review.json",
        )
        await _create_artifact(
            db_session, run.id,
            artifact_type="review",
            storage_path=f"runs/{run.id}/migration_guard_review.json",
        )
        await db_session.commit()

        review_data = {
            "verdict": "approve",
            "issues": [],
            "summary": "LGTM",
            "confidence": 0.95,
        }

        async def _retrieve(path: str) -> bytes:
            if "migration_guard" in path:
                raise FileNotFoundError("gone")
            return json.dumps(review_data).encode()

        mock_artifact_store.retrieve.side_effect = _retrieve

        resp = await client.get(f"/v1/runs/{run.id}/review")
        assert resp.status_code == 200
        body = resp.json()
        assert body["review"]["verdict"] == "approve"
        assert body["migration_guard_review"] is None
