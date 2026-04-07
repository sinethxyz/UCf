"""Integration-style tests for RunEngine.execute_run() and _open_pr().

All external dependencies (agent_runner, worktree_manager, pr_creator,
verification_runner, artifact_store) are mocked. The database session
is real (SQLite in-memory) so state transitions are validated end-to-end.
"""

import json
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import UUID, uuid4

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from foundry.contracts.review_models import ReviewIssue, ReviewVerdict
from foundry.contracts.shared import (
    Complexity,
    MCPProfile,
    ReviewSeverity,
    ReviewVerdictType,
    RunState,
    TaskType,
)
from foundry.contracts.task_types import PlanArtifact, PlanStep, TaskRequest
from foundry.db.queries.runs import create_run, get_run, get_run_events
from foundry.orchestration.run_engine import RunEngine
from foundry.storage.artifact_store import ArtifactStore, ArtifactType
from foundry.verification.go_verify import VerificationResult


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
            PlanStep(
                file_path="services/api/search/handler_test.go",
                action="modify",
                rationale="Add regression test",
            ),
        ],
        risks=["Might affect other pagination endpoints"],
        open_questions=[],
        estimated_complexity=Complexity.SMALL,
    )


@pytest.fixture
def sample_review() -> ReviewVerdict:
    return ReviewVerdict(
        verdict=ReviewVerdictType.APPROVE,
        issues=[],
        summary="Clean fix, approved.",
    )


@pytest.fixture
def rejected_review() -> ReviewVerdict:
    return ReviewVerdict(
        verdict=ReviewVerdictType.REJECT,
        issues=[
            ReviewIssue(
                severity=ReviewSeverity.CRITICAL,
                file_path="handler.go",
                description="Missing error handling",
            ),
        ],
        summary="Critical issues found.",
    )


SAMPLE_DIFF = """\
diff --git a/services/api/search/handler.go b/services/api/search/handler.go
-    offset := (page - 1) * pageSize + 1
+    offset := (page - 1) * pageSize
"""


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
        "url": "https://github.com/sinethxyz/unicorn-app/pull/99",
        "number": 99,
    })
    return creator


@pytest.fixture
def mock_verification_runner() -> MagicMock:
    runner = MagicMock()
    runner.run_all = AsyncMock(return_value=[
        VerificationResult(check_type="go_build", passed=True, output="ok", duration_ms=1000),
        VerificationResult(check_type="go_test", passed=True, output="PASS", duration_ms=2000),
    ])
    return runner


def _make_git_mock():
    """Create a mock for asyncio.create_subprocess_exec that simulates git commands."""
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
# execute_run — happy path
# ---------------------------------------------------------------------------


class TestExecuteRunHappyPath:
    async def test_happy_path_reaches_completed(
        self,
        run_engine: RunEngine,
        sample_task_request: TaskRequest,
        async_session: AsyncSession,
    ):
        """Full happy path: QUEUED → ... → COMPLETED."""
        with patch("asyncio.create_subprocess_exec", return_value=_make_git_mock()):
            response = await run_engine.execute_run(sample_task_request)

        assert response.state == RunState.COMPLETED

    async def test_happy_path_sets_pr_url(
        self,
        run_engine: RunEngine,
        sample_task_request: TaskRequest,
    ):
        with patch("asyncio.create_subprocess_exec", return_value=_make_git_mock()):
            response = await run_engine.execute_run(sample_task_request)

        assert response.pr_url == "https://github.com/sinethxyz/unicorn-app/pull/99"

    async def test_happy_path_stores_pr_metadata_artifact(
        self,
        run_engine: RunEngine,
        sample_task_request: TaskRequest,
        artifact_store: ArtifactStore,
    ):
        with patch("asyncio.create_subprocess_exec", return_value=_make_git_mock()):
            response = await run_engine.execute_run(sample_task_request)

        artifacts = await artifact_store.list_artifacts(response.id)
        pr_artifacts = [a for a in artifacts if "pr_metadata" in a]
        assert len(pr_artifacts) == 1

        content = json.loads(await artifact_store.retrieve(pr_artifacts[0]))
        assert content["url"] == "https://github.com/sinethxyz/unicorn-app/pull/99"
        assert content["number"] == 99

    async def test_happy_path_calls_all_phases(
        self,
        run_engine: RunEngine,
        sample_task_request: TaskRequest,
        mock_worktree_manager,
        mock_agent_runner,
        mock_pr_creator,
        mock_verification_runner,
    ):
        with patch("asyncio.create_subprocess_exec", return_value=_make_git_mock()):
            await run_engine.execute_run(sample_task_request)

        mock_worktree_manager.create.assert_called_once()
        mock_agent_runner.run_planner.assert_called_once()
        mock_agent_runner.run_implementer.assert_called_once()
        mock_verification_runner.run_all.assert_called_once()
        mock_agent_runner.run_reviewer.assert_called_once()
        mock_pr_creator.create_pr.assert_called_once()

    async def test_happy_path_cleans_up_worktree(
        self,
        run_engine: RunEngine,
        sample_task_request: TaskRequest,
        mock_worktree_manager,
    ):
        with patch("asyncio.create_subprocess_exec", return_value=_make_git_mock()):
            await run_engine.execute_run(sample_task_request)

        mock_worktree_manager.cleanup.assert_called_once_with(
            "/tmp/foundry-worktrees/test-run",
        )

    async def test_happy_path_creates_events_for_all_states(
        self,
        run_engine: RunEngine,
        sample_task_request: TaskRequest,
        async_session: AsyncSession,
    ):
        with patch("asyncio.create_subprocess_exec", return_value=_make_git_mock()):
            response = await run_engine.execute_run(sample_task_request)

        events = await get_run_events(async_session, response.id)
        event_states = [e.state for e in events]

        # Should traverse all happy path states
        assert "queued" in event_states
        assert "creating_worktree" in event_states
        assert "planning" in event_states
        assert "implementing" in event_states
        assert "verifying" in event_states
        assert "verification_passed" in event_states
        assert "reviewing" in event_states
        assert "pr_opened" in event_states
        assert "completed" in event_states

    async def test_happy_path_pr_creator_receives_correct_args(
        self,
        run_engine: RunEngine,
        sample_task_request: TaskRequest,
        mock_pr_creator,
    ):
        with patch("asyncio.create_subprocess_exec", return_value=_make_git_mock()):
            await run_engine.execute_run(sample_task_request)

        call_kwargs = mock_pr_creator.create_pr.call_args.kwargs
        assert call_kwargs["task_request"] == sample_task_request
        assert call_kwargs["base_branch"] == "main"
        assert call_kwargs["diff"] == SAMPLE_DIFF
        assert isinstance(call_kwargs["run_id"], UUID)
        assert call_kwargs["review_verdict"].verdict == ReviewVerdictType.APPROVE

    async def test_happy_path_sets_branch_name_on_run(
        self,
        run_engine: RunEngine,
        sample_task_request: TaskRequest,
        async_session: AsyncSession,
    ):
        with patch("asyncio.create_subprocess_exec", return_value=_make_git_mock()):
            response = await run_engine.execute_run(sample_task_request)

        assert response.branch_name is not None
        assert response.branch_name.startswith("foundry/")


# ---------------------------------------------------------------------------
# execute_run — planning failure
# ---------------------------------------------------------------------------


class TestExecuteRunPlanningFailure:
    async def test_plan_failure_returns_plan_failed_state(
        self,
        run_engine: RunEngine,
        sample_task_request: TaskRequest,
        mock_agent_runner,
    ):
        mock_agent_runner.run_planner = AsyncMock(
            side_effect=RuntimeError("Planner crashed"),
        )

        response = await run_engine.execute_run(sample_task_request)

        assert response.state == RunState.PLAN_FAILED

    async def test_plan_failure_does_not_call_implementer(
        self,
        run_engine: RunEngine,
        sample_task_request: TaskRequest,
        mock_agent_runner,
    ):
        mock_agent_runner.run_planner = AsyncMock(
            side_effect=RuntimeError("Planner crashed"),
        )

        await run_engine.execute_run(sample_task_request)

        mock_agent_runner.run_implementer.assert_not_called()

    async def test_plan_failure_cleans_up_worktree(
        self,
        run_engine: RunEngine,
        sample_task_request: TaskRequest,
        mock_agent_runner,
        mock_worktree_manager,
    ):
        mock_agent_runner.run_planner = AsyncMock(
            side_effect=RuntimeError("Planner crashed"),
        )

        await run_engine.execute_run(sample_task_request)

        mock_worktree_manager.cleanup.assert_called_once()


# ---------------------------------------------------------------------------
# execute_run — implementation failure
# ---------------------------------------------------------------------------


class TestExecuteRunImplementationFailure:
    async def test_implementation_failure_returns_errored_state(
        self,
        run_engine: RunEngine,
        sample_task_request: TaskRequest,
        mock_agent_runner,
    ):
        mock_agent_runner.run_implementer = AsyncMock(
            side_effect=RuntimeError("Implementer crashed"),
        )

        response = await run_engine.execute_run(sample_task_request)

        assert response.state == RunState.ERRORED

    async def test_implementation_failure_does_not_open_pr(
        self,
        run_engine: RunEngine,
        sample_task_request: TaskRequest,
        mock_agent_runner,
        mock_pr_creator,
    ):
        mock_agent_runner.run_implementer = AsyncMock(
            side_effect=RuntimeError("Implementer crashed"),
        )

        await run_engine.execute_run(sample_task_request)

        mock_pr_creator.create_pr.assert_not_called()

    async def test_implementation_failure_cleans_up_worktree(
        self,
        run_engine: RunEngine,
        sample_task_request: TaskRequest,
        mock_agent_runner,
        mock_worktree_manager,
    ):
        mock_agent_runner.run_implementer = AsyncMock(
            side_effect=RuntimeError("Implementer crashed"),
        )

        await run_engine.execute_run(sample_task_request)

        mock_worktree_manager.cleanup.assert_called_once()


# ---------------------------------------------------------------------------
# execute_run — verification failure
# ---------------------------------------------------------------------------


class TestExecuteRunVerificationFailure:
    async def test_verification_failure_returns_verification_failed(
        self,
        run_engine: RunEngine,
        sample_task_request: TaskRequest,
        mock_verification_runner,
    ):
        mock_verification_runner.run_all = AsyncMock(return_value=[
            VerificationResult(
                check_type="go_test", passed=False,
                output="FAIL", duration_ms=1000,
            ),
        ])

        with patch("asyncio.create_subprocess_exec", return_value=_make_git_mock()):
            response = await run_engine.execute_run(sample_task_request)

        assert response.state == RunState.VERIFICATION_FAILED

    async def test_verification_failure_does_not_open_pr(
        self,
        run_engine: RunEngine,
        sample_task_request: TaskRequest,
        mock_verification_runner,
        mock_pr_creator,
    ):
        mock_verification_runner.run_all = AsyncMock(return_value=[
            VerificationResult(
                check_type="go_test", passed=False,
                output="FAIL", duration_ms=1000,
            ),
        ])

        with patch("asyncio.create_subprocess_exec", return_value=_make_git_mock()):
            await run_engine.execute_run(sample_task_request)

        mock_pr_creator.create_pr.assert_not_called()


# ---------------------------------------------------------------------------
# execute_run — review rejection
# ---------------------------------------------------------------------------


class TestExecuteRunReviewRejection:
    async def test_review_rejection_returns_review_failed(
        self,
        run_engine: RunEngine,
        sample_task_request: TaskRequest,
        mock_agent_runner,
        rejected_review: ReviewVerdict,
    ):
        mock_agent_runner.run_reviewer = AsyncMock(return_value=rejected_review)

        with patch("asyncio.create_subprocess_exec", return_value=_make_git_mock()):
            response = await run_engine.execute_run(sample_task_request)

        assert response.state == RunState.REVIEW_FAILED

    async def test_review_rejection_does_not_open_pr(
        self,
        run_engine: RunEngine,
        sample_task_request: TaskRequest,
        mock_agent_runner,
        rejected_review: ReviewVerdict,
        mock_pr_creator,
    ):
        mock_agent_runner.run_reviewer = AsyncMock(return_value=rejected_review)

        with patch("asyncio.create_subprocess_exec", return_value=_make_git_mock()):
            await run_engine.execute_run(sample_task_request)

        mock_pr_creator.create_pr.assert_not_called()

    async def test_review_rejection_cleans_up_worktree(
        self,
        run_engine: RunEngine,
        sample_task_request: TaskRequest,
        mock_agent_runner,
        rejected_review: ReviewVerdict,
        mock_worktree_manager,
    ):
        mock_agent_runner.run_reviewer = AsyncMock(return_value=rejected_review)

        with patch("asyncio.create_subprocess_exec", return_value=_make_git_mock()):
            await run_engine.execute_run(sample_task_request)

        mock_worktree_manager.cleanup.assert_called_once()


# ---------------------------------------------------------------------------
# execute_run — unexpected error handling
# ---------------------------------------------------------------------------


class TestExecuteRunErrorHandling:
    async def test_unexpected_error_transitions_to_errored(
        self,
        run_engine: RunEngine,
        sample_task_request: TaskRequest,
        mock_worktree_manager,
    ):
        mock_worktree_manager.create = AsyncMock(
            side_effect=RuntimeError("Disk full"),
        )

        response = await run_engine.execute_run(sample_task_request)

        assert response.state == RunState.ERRORED

    async def test_unexpected_error_stores_error_artifact(
        self,
        run_engine: RunEngine,
        sample_task_request: TaskRequest,
        mock_worktree_manager,
        artifact_store: ArtifactStore,
    ):
        mock_worktree_manager.create = AsyncMock(
            side_effect=RuntimeError("Disk full"),
        )

        response = await run_engine.execute_run(sample_task_request)

        artifacts = await artifact_store.list_artifacts(response.id)
        error_artifacts = [a for a in artifacts if "error_log" in a]
        assert len(error_artifacts) >= 1

        content = json.loads(await artifact_store.retrieve(error_artifacts[0]))
        assert "Disk full" in content["error"]
        assert content["phase"] == "execute_run"

    async def test_unexpected_error_includes_traceback(
        self,
        run_engine: RunEngine,
        sample_task_request: TaskRequest,
        mock_worktree_manager,
        artifact_store: ArtifactStore,
    ):
        mock_worktree_manager.create = AsyncMock(
            side_effect=RuntimeError("Disk full"),
        )

        response = await run_engine.execute_run(sample_task_request)

        artifacts = await artifact_store.list_artifacts(response.id)
        error_artifacts = [a for a in artifacts if "error_log" in a]
        content = json.loads(await artifact_store.retrieve(error_artifacts[0]))
        assert "traceback" in content
        assert "Disk full" in content["traceback"]

    async def test_error_during_pr_opening_transitions_to_errored(
        self,
        run_engine: RunEngine,
        sample_task_request: TaskRequest,
        mock_pr_creator,
    ):
        mock_pr_creator.create_pr = AsyncMock(
            side_effect=RuntimeError("GitHub API error"),
        )

        with patch("asyncio.create_subprocess_exec", return_value=_make_git_mock()):
            response = await run_engine.execute_run(sample_task_request)

        assert response.state == RunState.ERRORED

    async def test_worktree_cleanup_on_error(
        self,
        run_engine: RunEngine,
        sample_task_request: TaskRequest,
        mock_pr_creator,
        mock_worktree_manager,
    ):
        """Worktree is cleaned up even when PR creation fails."""
        mock_pr_creator.create_pr = AsyncMock(
            side_effect=RuntimeError("GitHub API error"),
        )

        with patch("asyncio.create_subprocess_exec", return_value=_make_git_mock()):
            await run_engine.execute_run(sample_task_request)

        mock_worktree_manager.cleanup.assert_called_once()

    async def test_worktree_cleanup_failure_does_not_mask_result(
        self,
        run_engine: RunEngine,
        sample_task_request: TaskRequest,
        mock_worktree_manager,
    ):
        """A failed worktree cleanup should not raise or mask the run result."""
        mock_worktree_manager.cleanup = AsyncMock(
            side_effect=RuntimeError("Cleanup failed"),
        )

        with patch("asyncio.create_subprocess_exec", return_value=_make_git_mock()):
            response = await run_engine.execute_run(sample_task_request)

        # The run should still complete successfully
        assert response.state == RunState.COMPLETED


# ---------------------------------------------------------------------------
# _open_pr tests
# ---------------------------------------------------------------------------


class TestOpenPr:
    async def _setup_run_in_reviewing_state(
        self,
        session: AsyncSession,
        run_engine: RunEngine,
        task_request: TaskRequest,
    ) -> UUID:
        """Create a run and advance it to REVIEWING state."""
        run = await create_run(session, task_request)
        run_id = run.id
        # Set branch_name on the run record
        run.branch_name = "foundry/bug-fix-pagination"
        await session.flush()

        transitions = [
            (RunState.QUEUED, RunState.CREATING_WORKTREE),
            (RunState.CREATING_WORKTREE, RunState.PLANNING),
            (RunState.PLANNING, RunState.IMPLEMENTING),
            (RunState.IMPLEMENTING, RunState.VERIFYING),
            (RunState.VERIFYING, RunState.VERIFICATION_PASSED),
            (RunState.VERIFICATION_PASSED, RunState.REVIEWING),
        ]
        for from_s, to_s in transitions:
            await run_engine._transition(run_id, from_s, to_s, f"{from_s.value} -> {to_s.value}")
        return run_id

    async def test_open_pr_transitions_to_completed(
        self,
        run_engine: RunEngine,
        async_session: AsyncSession,
        sample_task_request: TaskRequest,
        sample_plan: PlanArtifact,
        sample_review: ReviewVerdict,
    ):
        run_id = await self._setup_run_in_reviewing_state(
            async_session, run_engine, sample_task_request,
        )

        with patch("asyncio.create_subprocess_exec", return_value=_make_git_mock()):
            pr_url = await run_engine._open_pr(
                run_id, sample_task_request, "/tmp/worktree",
                sample_plan, sample_review, SAMPLE_DIFF,
            )

        run = await get_run(async_session, run_id)
        assert run is not None
        assert run.state == RunState.COMPLETED.value

    async def test_open_pr_returns_pr_url(
        self,
        run_engine: RunEngine,
        async_session: AsyncSession,
        sample_task_request: TaskRequest,
        sample_plan: PlanArtifact,
        sample_review: ReviewVerdict,
    ):
        run_id = await self._setup_run_in_reviewing_state(
            async_session, run_engine, sample_task_request,
        )

        with patch("asyncio.create_subprocess_exec", return_value=_make_git_mock()):
            pr_url = await run_engine._open_pr(
                run_id, sample_task_request, "/tmp/worktree",
                sample_plan, sample_review, SAMPLE_DIFF,
            )

        assert pr_url == "https://github.com/sinethxyz/unicorn-app/pull/99"

    async def test_open_pr_stores_pr_metadata_artifact(
        self,
        run_engine: RunEngine,
        async_session: AsyncSession,
        sample_task_request: TaskRequest,
        sample_plan: PlanArtifact,
        sample_review: ReviewVerdict,
        artifact_store: ArtifactStore,
    ):
        run_id = await self._setup_run_in_reviewing_state(
            async_session, run_engine, sample_task_request,
        )

        with patch("asyncio.create_subprocess_exec", return_value=_make_git_mock()):
            await run_engine._open_pr(
                run_id, sample_task_request, "/tmp/worktree",
                sample_plan, sample_review, SAMPLE_DIFF,
            )

        artifacts = await artifact_store.list_artifacts(run_id)
        pr_artifacts = [a for a in artifacts if "pr_metadata" in a]
        assert len(pr_artifacts) == 1

        content = json.loads(await artifact_store.retrieve(pr_artifacts[0]))
        assert content["number"] == 99
        assert "foundry/bug-fix-pagination" in content["branch"]

    async def test_open_pr_updates_run_pr_url(
        self,
        run_engine: RunEngine,
        async_session: AsyncSession,
        sample_task_request: TaskRequest,
        sample_plan: PlanArtifact,
        sample_review: ReviewVerdict,
    ):
        run_id = await self._setup_run_in_reviewing_state(
            async_session, run_engine, sample_task_request,
        )

        with patch("asyncio.create_subprocess_exec", return_value=_make_git_mock()):
            await run_engine._open_pr(
                run_id, sample_task_request, "/tmp/worktree",
                sample_plan, sample_review, SAMPLE_DIFF,
            )

        run = await get_run(async_session, run_id)
        assert run is not None
        assert run.pr_url == "https://github.com/sinethxyz/unicorn-app/pull/99"

    async def test_open_pr_creates_pr_opened_and_completed_events(
        self,
        run_engine: RunEngine,
        async_session: AsyncSession,
        sample_task_request: TaskRequest,
        sample_plan: PlanArtifact,
        sample_review: ReviewVerdict,
    ):
        run_id = await self._setup_run_in_reviewing_state(
            async_session, run_engine, sample_task_request,
        )

        with patch("asyncio.create_subprocess_exec", return_value=_make_git_mock()):
            await run_engine._open_pr(
                run_id, sample_task_request, "/tmp/worktree",
                sample_plan, sample_review, SAMPLE_DIFF,
            )

        events = await get_run_events(async_session, run_id)
        event_states = [e.state for e in events]
        assert "pr_opened" in event_states
        assert "completed" in event_states

    async def test_open_pr_passes_diff_to_pr_creator(
        self,
        run_engine: RunEngine,
        async_session: AsyncSession,
        sample_task_request: TaskRequest,
        sample_plan: PlanArtifact,
        sample_review: ReviewVerdict,
        mock_pr_creator,
    ):
        run_id = await self._setup_run_in_reviewing_state(
            async_session, run_engine, sample_task_request,
        )

        with patch("asyncio.create_subprocess_exec", return_value=_make_git_mock()):
            await run_engine._open_pr(
                run_id, sample_task_request, "/tmp/worktree",
                sample_plan, sample_review, SAMPLE_DIFF,
            )

        call_kwargs = mock_pr_creator.create_pr.call_args.kwargs
        assert call_kwargs["diff"] == SAMPLE_DIFF
        assert call_kwargs["plan"] == sample_plan
        assert call_kwargs["review_verdict"] == sample_review


# ---------------------------------------------------------------------------
# Migration guard tests
# ---------------------------------------------------------------------------


class TestMigrationGuard:
    async def test_migration_guard_rejection_blocks_pr(
        self,
        run_engine: RunEngine,
        sample_task_request: TaskRequest,
        mock_agent_runner,
        mock_pr_creator,
    ):
        """When migration guard rejects, the run should fail review."""
        # Diff must contain lines matching protected path patterns
        # _check_migration_guard looks for "^[ab]/migrations/" in diff --git lines
        migration_diff = (
            "diff --git a/migrations/001.py b/migrations/001.py\n"
            "--- a/migrations/001.py\n"
            "+++ b/migrations/001.py\n"
            "@@ -0,0 +1,5 @@\n"
            "+def upgrade():\n"
            "+    pass\n"
        )
        mock_agent_runner.run_implementer = AsyncMock(return_value=migration_diff)
        mock_agent_runner.run_migration_guard = AsyncMock(return_value=ReviewVerdict(
            verdict=ReviewVerdictType.REJECT,
            issues=[],
            summary="Unsafe migration",
        ))

        with patch("asyncio.create_subprocess_exec", return_value=_make_git_mock()):
            response = await run_engine.execute_run(sample_task_request)

        assert response.state == RunState.REVIEW_FAILED
        mock_pr_creator.create_pr.assert_not_called()
