"""Tests that all 6 artifact types are registered during a successful run.

Verifies that execute_run stores and registers in the DB:
1. plan.json (PlanArtifact serialized)
2. diff.patch (raw git diff output)
3. verification.json (list of VerificationResult serialized)
4. review.json (ReviewVerdict serialized)
5. pr_metadata.json (url, number, branch, labels)
6. error_log.json (on any error: traceback, state at failure, last event)
"""

import json
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from foundry.contracts.review_models import ReviewVerdict
from foundry.contracts.shared import (
    Complexity,
    MCPProfile,
    ReviewVerdictType,
    RunState,
    TaskType,
)
from foundry.contracts.task_types import PlanArtifact, PlanStep, TaskRequest
from foundry.db.queries.artifacts import get_artifacts
from foundry.orchestration.run_engine import RunEngine
from foundry.storage.artifact_store import ArtifactStore, ArtifactType
from foundry.verification.go_verify import VerificationResult


# ---------------------------------------------------------------------------
# Shared test data
# ---------------------------------------------------------------------------

SAMPLE_DIFF = """\
diff --git a/services/api/search/handler.go b/services/api/search/handler.go
-    offset := (page - 1) * pageSize + 1
+    offset := (page - 1) * pageSize
"""


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def sample_task_request() -> TaskRequest:
    return TaskRequest(
        task_type=TaskType.BUG_FIX,
        repo="unicorn-app",
        base_branch="main",
        title="Fix pagination bug",
        prompt="Fix the off-by-one error in search pagination",
        target_paths=["services/api/search/handler.go"],
        mcp_profile=MCPProfile.NONE,
    )


@pytest.fixture
def sample_plan() -> PlanArtifact:
    return PlanArtifact(
        task_id=uuid4(),
        steps=[
            PlanStep(
                file_path="services/api/search/handler.go",
                action="modify",
                rationale="Fix off-by-one in offset calculation",
            ),
        ],
        risks=[],
        open_questions=[],
        estimated_complexity=Complexity.SMALL,
    )


@pytest.fixture
def sample_review() -> ReviewVerdict:
    return ReviewVerdict(
        verdict=ReviewVerdictType.APPROVE,
        issues=[],
        summary="Clean fix, approved.",
        confidence=0.95,
    )


@pytest.fixture
def artifact_store(tmp_path: Path) -> ArtifactStore:
    return ArtifactStore(base_path=str(tmp_path / "artifacts"))


@pytest.fixture
def mock_worktree_manager() -> MagicMock:
    manager = MagicMock()
    manager.create = AsyncMock(return_value="/tmp/foundry-worktrees/test-run")
    manager.cleanup = AsyncMock()
    return manager


@pytest.fixture
def mock_agent_runner(sample_plan, sample_review) -> MagicMock:
    runner = MagicMock()
    runner.run_planner = AsyncMock(return_value=sample_plan)
    runner.run_implementer = AsyncMock(return_value=SAMPLE_DIFF)
    runner.run_reviewer = AsyncMock(return_value=sample_review)
    runner.run_migration_guard = AsyncMock(return_value=None)
    return runner


@pytest.fixture
def mock_pr_creator() -> MagicMock:
    creator = MagicMock()
    creator.create_pr = AsyncMock(return_value={
        "url": "https://github.com/sinethxyz/unicorn-app/pull/42",
        "number": 42,
    })
    return creator


@pytest.fixture
def mock_verification_runner() -> MagicMock:
    runner = MagicMock()
    runner.run_all = AsyncMock(return_value=([
        VerificationResult(check_type="go_build", passed=True, output="ok", duration_ms=500),
        VerificationResult(check_type="go_test", passed=True, output="PASS", duration_ms=1000),
    ], True))
    return runner


def _make_git_mock():
    mock_proc = AsyncMock()
    mock_proc.returncode = 0
    mock_proc.communicate = AsyncMock(return_value=(b"", b""))
    return mock_proc


@pytest.fixture
def run_engine(
    async_session: AsyncSession,
    artifact_store: ArtifactStore,
    mock_worktree_manager: MagicMock,
    mock_agent_runner: MagicMock,
    mock_pr_creator: MagicMock,
    mock_verification_runner: MagicMock,
) -> RunEngine:
    return RunEngine(
        session=async_session,
        artifact_store=artifact_store,
        worktree_manager=mock_worktree_manager,
        agent_runner=mock_agent_runner,
        pr_creator=mock_pr_creator,
        verification_runner=mock_verification_runner,
    )


# ---------------------------------------------------------------------------
# Happy path: all 5 artifact types registered
# ---------------------------------------------------------------------------


class TestAllArtifactsRegisteredOnSuccess:
    """A successful run must register plan, diff, verification, review, and pr_metadata."""

    async def test_all_five_artifact_types_registered_in_db(
        self,
        run_engine: RunEngine,
        sample_task_request: TaskRequest,
        async_session: AsyncSession,
    ):
        with patch("asyncio.create_subprocess_exec", return_value=_make_git_mock()):
            response = await run_engine.execute_run(sample_task_request)

        assert response.state == RunState.COMPLETED

        db_artifacts = await get_artifacts(async_session, response.id)
        artifact_types = {a.artifact_type for a in db_artifacts}

        assert "plan" in artifact_types
        assert "diff" in artifact_types
        assert "verification" in artifact_types
        assert "review" in artifact_types
        assert "pr_metadata" in artifact_types

    async def test_exactly_five_artifacts_on_success(
        self,
        run_engine: RunEngine,
        sample_task_request: TaskRequest,
        async_session: AsyncSession,
    ):
        with patch("asyncio.create_subprocess_exec", return_value=_make_git_mock()):
            response = await run_engine.execute_run(sample_task_request)

        db_artifacts = await get_artifacts(async_session, response.id)
        assert len(db_artifacts) == 5

    async def test_all_artifacts_have_storage_path(
        self,
        run_engine: RunEngine,
        sample_task_request: TaskRequest,
        async_session: AsyncSession,
    ):
        with patch("asyncio.create_subprocess_exec", return_value=_make_git_mock()):
            response = await run_engine.execute_run(sample_task_request)

        db_artifacts = await get_artifacts(async_session, response.id)
        for artifact in db_artifacts:
            assert artifact.storage_path is not None
            assert artifact.storage_path.startswith("runs/")

    async def test_all_artifacts_have_size_bytes(
        self,
        run_engine: RunEngine,
        sample_task_request: TaskRequest,
        async_session: AsyncSession,
    ):
        with patch("asyncio.create_subprocess_exec", return_value=_make_git_mock()):
            response = await run_engine.execute_run(sample_task_request)

        db_artifacts = await get_artifacts(async_session, response.id)
        for artifact in db_artifacts:
            assert artifact.size_bytes is not None
            assert artifact.size_bytes > 0

    async def test_all_artifacts_have_checksum(
        self,
        run_engine: RunEngine,
        sample_task_request: TaskRequest,
        async_session: AsyncSession,
    ):
        with patch("asyncio.create_subprocess_exec", return_value=_make_git_mock()):
            response = await run_engine.execute_run(sample_task_request)

        db_artifacts = await get_artifacts(async_session, response.id)
        for artifact in db_artifacts:
            assert artifact.checksum is not None
            assert len(artifact.checksum) == 64  # SHA-256 hex

    async def test_plan_artifact_is_valid_json(
        self,
        run_engine: RunEngine,
        sample_task_request: TaskRequest,
        async_session: AsyncSession,
        artifact_store: ArtifactStore,
    ):
        with patch("asyncio.create_subprocess_exec", return_value=_make_git_mock()):
            response = await run_engine.execute_run(sample_task_request)

        db_artifacts = await get_artifacts(async_session, response.id)
        plan_artifact = [a for a in db_artifacts if a.artifact_type == "plan"][0]

        raw = await artifact_store.retrieve(plan_artifact.storage_path)
        data = json.loads(raw)
        assert "steps" in data

    async def test_diff_artifact_contains_patch(
        self,
        run_engine: RunEngine,
        sample_task_request: TaskRequest,
        async_session: AsyncSession,
        artifact_store: ArtifactStore,
    ):
        with patch("asyncio.create_subprocess_exec", return_value=_make_git_mock()):
            response = await run_engine.execute_run(sample_task_request)

        db_artifacts = await get_artifacts(async_session, response.id)
        diff_artifact = [a for a in db_artifacts if a.artifact_type == "diff"][0]

        raw = await artifact_store.retrieve(diff_artifact.storage_path)
        assert b"diff --git" in raw

    async def test_verification_artifact_is_valid_json(
        self,
        run_engine: RunEngine,
        sample_task_request: TaskRequest,
        async_session: AsyncSession,
        artifact_store: ArtifactStore,
    ):
        with patch("asyncio.create_subprocess_exec", return_value=_make_git_mock()):
            response = await run_engine.execute_run(sample_task_request)

        db_artifacts = await get_artifacts(async_session, response.id)
        verif_artifact = [a for a in db_artifacts if a.artifact_type == "verification"][0]

        raw = await artifact_store.retrieve(verif_artifact.storage_path)
        data = json.loads(raw)
        assert isinstance(data, list)
        assert all("check_type" in item for item in data)
        assert all("passed" in item for item in data)

    async def test_review_artifact_contains_verdict(
        self,
        run_engine: RunEngine,
        sample_task_request: TaskRequest,
        async_session: AsyncSession,
        artifact_store: ArtifactStore,
    ):
        with patch("asyncio.create_subprocess_exec", return_value=_make_git_mock()):
            response = await run_engine.execute_run(sample_task_request)

        db_artifacts = await get_artifacts(async_session, response.id)
        review_artifact = [a for a in db_artifacts if a.artifact_type == "review"][0]

        raw = await artifact_store.retrieve(review_artifact.storage_path)
        data = json.loads(raw)
        assert "verdict" in data
        assert data["verdict"] == "approve"

    async def test_pr_metadata_artifact_has_url_and_number(
        self,
        run_engine: RunEngine,
        sample_task_request: TaskRequest,
        async_session: AsyncSession,
        artifact_store: ArtifactStore,
    ):
        with patch("asyncio.create_subprocess_exec", return_value=_make_git_mock()):
            response = await run_engine.execute_run(sample_task_request)

        db_artifacts = await get_artifacts(async_session, response.id)
        pr_artifact = [a for a in db_artifacts if a.artifact_type == "pr_metadata"][0]

        raw = await artifact_store.retrieve(pr_artifact.storage_path)
        data = json.loads(raw)
        assert "url" in data
        assert "number" in data
        assert "branch" in data
        assert "labels" in data

    async def test_artifact_files_exist_on_disk(
        self,
        run_engine: RunEngine,
        sample_task_request: TaskRequest,
        async_session: AsyncSession,
        artifact_store: ArtifactStore,
    ):
        with patch("asyncio.create_subprocess_exec", return_value=_make_git_mock()):
            response = await run_engine.execute_run(sample_task_request)

        entries = await artifact_store.list_artifacts(response.id)
        filenames = {e["filename"] for e in entries}

        assert "plan.json" in filenames
        assert "diff.patch" in filenames
        assert "verification.json" in filenames
        assert "review.json" in filenames
        assert "pr_metadata.json" in filenames


# ---------------------------------------------------------------------------
# Error path: error_log.json registered
# ---------------------------------------------------------------------------


class TestErrorLogArtifactRegistered:
    """On unexpected error, error_log.json must be stored and registered in DB."""

    async def test_error_log_registered_in_db_on_unexpected_error(
        self,
        run_engine: RunEngine,
        sample_task_request: TaskRequest,
        async_session: AsyncSession,
        mock_worktree_manager: MagicMock,
    ):
        mock_worktree_manager.create = AsyncMock(
            side_effect=RuntimeError("Disk full"),
        )

        response = await run_engine.execute_run(sample_task_request)

        assert response.state == RunState.ERRORED
        db_artifacts = await get_artifacts(async_session, response.id)
        error_artifacts = [a for a in db_artifacts if a.artifact_type == "error_log"]
        assert len(error_artifacts) >= 1

    async def test_error_log_has_size_and_checksum_in_db(
        self,
        run_engine: RunEngine,
        sample_task_request: TaskRequest,
        async_session: AsyncSession,
        mock_worktree_manager: MagicMock,
    ):
        mock_worktree_manager.create = AsyncMock(
            side_effect=RuntimeError("Disk full"),
        )

        response = await run_engine.execute_run(sample_task_request)

        db_artifacts = await get_artifacts(async_session, response.id)
        error_artifact = [a for a in db_artifacts if a.artifact_type == "error_log"][0]
        assert error_artifact.size_bytes is not None
        assert error_artifact.size_bytes > 0
        assert error_artifact.checksum is not None
        assert len(error_artifact.checksum) == 64

    async def test_error_log_contains_traceback(
        self,
        run_engine: RunEngine,
        sample_task_request: TaskRequest,
        async_session: AsyncSession,
        artifact_store: ArtifactStore,
        mock_worktree_manager: MagicMock,
    ):
        mock_worktree_manager.create = AsyncMock(
            side_effect=RuntimeError("Disk full"),
        )

        response = await run_engine.execute_run(sample_task_request)

        db_artifacts = await get_artifacts(async_session, response.id)
        error_artifact = [a for a in db_artifacts if a.artifact_type == "error_log"][0]

        raw = await artifact_store.retrieve(error_artifact.storage_path)
        data = json.loads(raw)
        assert "traceback" in data
        assert "Disk full" in data["traceback"]

    async def test_error_log_contains_state_at_failure(
        self,
        run_engine: RunEngine,
        sample_task_request: TaskRequest,
        async_session: AsyncSession,
        artifact_store: ArtifactStore,
        mock_worktree_manager: MagicMock,
    ):
        mock_worktree_manager.create = AsyncMock(
            side_effect=RuntimeError("Disk full"),
        )

        response = await run_engine.execute_run(sample_task_request)

        db_artifacts = await get_artifacts(async_session, response.id)
        error_artifact = [a for a in db_artifacts if a.artifact_type == "error_log"][0]

        raw = await artifact_store.retrieve(error_artifact.storage_path)
        data = json.loads(raw)
        assert "state_at_failure" in data

    async def test_error_log_contains_last_event(
        self,
        run_engine: RunEngine,
        sample_task_request: TaskRequest,
        async_session: AsyncSession,
        artifact_store: ArtifactStore,
        mock_worktree_manager: MagicMock,
    ):
        mock_worktree_manager.create = AsyncMock(
            side_effect=RuntimeError("Disk full"),
        )

        response = await run_engine.execute_run(sample_task_request)

        db_artifacts = await get_artifacts(async_session, response.id)
        error_artifact = [a for a in db_artifacts if a.artifact_type == "error_log"][0]

        raw = await artifact_store.retrieve(error_artifact.storage_path)
        data = json.loads(raw)
        assert "last_event" in data

    async def test_error_log_registered_on_planning_failure(
        self,
        run_engine: RunEngine,
        sample_task_request: TaskRequest,
        async_session: AsyncSession,
        mock_agent_runner: MagicMock,
    ):
        mock_agent_runner.run_planner = AsyncMock(
            side_effect=RuntimeError("Planner crashed"),
        )

        response = await run_engine.execute_run(sample_task_request)

        assert response.state == RunState.PLAN_FAILED
        db_artifacts = await get_artifacts(async_session, response.id)
        error_artifacts = [a for a in db_artifacts if a.artifact_type == "error_log"]
        assert len(error_artifacts) >= 1

        # Error artifact should have checksum
        assert error_artifacts[0].checksum is not None

    async def test_error_log_registered_on_implementation_failure(
        self,
        run_engine: RunEngine,
        sample_task_request: TaskRequest,
        async_session: AsyncSession,
        mock_agent_runner: MagicMock,
    ):
        mock_agent_runner.run_implementer = AsyncMock(
            side_effect=RuntimeError("Implementer crashed"),
        )

        response = await run_engine.execute_run(sample_task_request)

        assert response.state == RunState.ERRORED
        db_artifacts = await get_artifacts(async_session, response.id)
        error_artifacts = [a for a in db_artifacts if a.artifact_type == "error_log"]
        assert len(error_artifacts) >= 1
        assert error_artifacts[0].checksum is not None
