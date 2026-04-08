"""Tests for comprehensive run event logging.

Runs a mocked execute_run through the full lifecycle and verifies that
all expected events are created in order with correct messages and metadata.
"""

import json
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

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
from foundry.db.queries.runs import get_run_events
from foundry.orchestration.run_engine import RunEngine
from foundry.storage.artifact_store import ArtifactStore
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
        confidence=0.95,
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
        confidence=0.9,
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
    runner.run_all = AsyncMock(return_value=([
        VerificationResult(check_type="go_build", passed=True, output="ok", duration_ms=1000),
        VerificationResult(check_type="go_vet", passed=True, output="ok", duration_ms=500),
        VerificationResult(check_type="go_test", passed=True, output="PASS", duration_ms=2000),
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
# Happy path event logging
# ---------------------------------------------------------------------------


class TestHappyPathEventLogging:
    """Verify all expected events are emitted during a successful run."""

    async def test_all_lifecycle_events_present(
        self,
        run_engine: RunEngine,
        sample_task_request: TaskRequest,
        async_session: AsyncSession,
    ):
        """Every lifecycle boundary must emit an event."""
        with patch("asyncio.create_subprocess_exec", return_value=_make_git_mock()):
            response = await run_engine.execute_run(sample_task_request)

        events = await get_run_events(async_session, response.id)
        messages = [e.message for e in events]

        # Check for required messages at each boundary
        assert any("accepted and queued" in m for m in messages)
        assert any("Worktree created at" in m for m in messages)
        assert any("Planning started" in m for m in messages)
        assert any("Plan generated with" in m for m in messages)
        assert any("Implementation started" in m for m in messages)
        assert any("Implementation completed" in m for m in messages)
        assert any("Verification started" in m for m in messages)
        assert any("go_build passed" in m for m in messages)
        assert any("go_test passed" in m for m in messages)
        assert any("Verification passed" in m for m in messages)
        assert any("Blind review started" in m for m in messages)
        assert any("Review verdict:" in m for m in messages)
        assert any("PR #99 opened" in m for m in messages)
        assert any("Run completed successfully" in m for m in messages)

    async def test_events_are_chronologically_ordered(
        self,
        run_engine: RunEngine,
        sample_task_request: TaskRequest,
        async_session: AsyncSession,
    ):
        """Events must be ordered by created_at ascending."""
        with patch("asyncio.create_subprocess_exec", return_value=_make_git_mock()):
            response = await run_engine.execute_run(sample_task_request)

        events = await get_run_events(async_session, response.id)
        timestamps = [e.created_at for e in events]
        assert timestamps == sorted(timestamps)

    async def test_queued_event_has_task_metadata(
        self,
        run_engine: RunEngine,
        sample_task_request: TaskRequest,
        async_session: AsyncSession,
    ):
        """The initial queued event must include task type and repo metadata."""
        with patch("asyncio.create_subprocess_exec", return_value=_make_git_mock()):
            response = await run_engine.execute_run(sample_task_request)

        events = await get_run_events(async_session, response.id)
        queued_event = next(e for e in events if "accepted and queued" in e.message)
        assert queued_event.metadata_["task_type"] == "bug_fix"
        assert queued_event.metadata_["repo"] == "unicorn-app"

    async def test_worktree_event_has_path_and_branch(
        self,
        run_engine: RunEngine,
        sample_task_request: TaskRequest,
        async_session: AsyncSession,
    ):
        """Worktree creation event must include path and branch metadata."""
        with patch("asyncio.create_subprocess_exec", return_value=_make_git_mock()):
            response = await run_engine.execute_run(sample_task_request)

        events = await get_run_events(async_session, response.id)
        wt_event = next(e for e in events if "Worktree created at" in e.message)
        assert wt_event.metadata_["path"] == "/tmp/foundry-worktrees/test-run"
        assert "foundry/" in wt_event.metadata_["branch"]
        assert wt_event.duration_ms is not None

    async def test_planning_started_has_model(
        self,
        run_engine: RunEngine,
        sample_task_request: TaskRequest,
        async_session: AsyncSession,
    ):
        """Planning started event must include the model name."""
        with patch("asyncio.create_subprocess_exec", return_value=_make_git_mock()):
            response = await run_engine.execute_run(sample_task_request)

        events = await get_run_events(async_session, response.id)
        plan_started = next(e for e in events if e.message == "Planning started")
        assert "model" in plan_started.metadata_
        assert plan_started.model_used is not None

    async def test_planning_completed_has_step_count(
        self,
        run_engine: RunEngine,
        sample_task_request: TaskRequest,
        async_session: AsyncSession,
    ):
        """Planning completed event must report step count and artifact."""
        with patch("asyncio.create_subprocess_exec", return_value=_make_git_mock()):
            response = await run_engine.execute_run(sample_task_request)

        events = await get_run_events(async_session, response.id)
        plan_done = next(e for e in events if "Plan generated with" in e.message)
        assert "2 steps" in plan_done.message
        assert plan_done.metadata_["artifact"] == "plan.json"
        assert plan_done.metadata_["step_count"] == 2
        assert plan_done.duration_ms is not None

    async def test_implementation_events_have_model_and_language(
        self,
        run_engine: RunEngine,
        sample_task_request: TaskRequest,
        async_session: AsyncSession,
    ):
        """Implementation events must include model and language metadata."""
        with patch("asyncio.create_subprocess_exec", return_value=_make_git_mock()):
            response = await run_engine.execute_run(sample_task_request)

        events = await get_run_events(async_session, response.id)
        impl_started = next(e for e in events if e.message == "Implementation started")
        assert impl_started.metadata_["language"] == "go"
        assert impl_started.model_used is not None

        impl_done = next(e for e in events if "Implementation completed" in e.message)
        assert "files changed" in impl_done.message
        assert impl_done.metadata_["artifact"] == "diff.patch"
        assert impl_done.duration_ms is not None

    async def test_verification_events_per_check(
        self,
        run_engine: RunEngine,
        sample_task_request: TaskRequest,
        async_session: AsyncSession,
    ):
        """Each verification check must emit its own event with duration."""
        with patch("asyncio.create_subprocess_exec", return_value=_make_git_mock()):
            response = await run_engine.execute_run(sample_task_request)

        events = await get_run_events(async_session, response.id)
        check_events = [e for e in events if "passed" in e.message and e.state == "verifying" and e.message != "Verification passed"]

        # Should have events for go_build, go_vet, go_test
        check_names = [e.metadata_["check_type"] for e in check_events]
        assert "go_build" in check_names
        assert "go_vet" in check_names
        assert "go_test" in check_names

        for e in check_events:
            assert e.duration_ms is not None
            assert "output_snippet" in e.metadata_

    async def test_verification_overall_result_event(
        self,
        run_engine: RunEngine,
        sample_task_request: TaskRequest,
        async_session: AsyncSession,
    ):
        """Overall verification result event must be emitted."""
        with patch("asyncio.create_subprocess_exec", return_value=_make_git_mock()):
            response = await run_engine.execute_run(sample_task_request)

        events = await get_run_events(async_session, response.id)
        v_passed = next(e for e in events if e.message == "Verification passed")
        assert "checks_passed" in v_passed.metadata_

    async def test_review_events_have_model_and_verdict(
        self,
        run_engine: RunEngine,
        sample_task_request: TaskRequest,
        async_session: AsyncSession,
    ):
        """Review events must include model, verdict, and issue count."""
        with patch("asyncio.create_subprocess_exec", return_value=_make_git_mock()):
            response = await run_engine.execute_run(sample_task_request)

        events = await get_run_events(async_session, response.id)
        review_started = next(e for e in events if e.message == "Blind review started")
        assert review_started.model_used is not None
        assert "model" in review_started.metadata_

        review_done = next(e for e in events if "Review verdict:" in e.message)
        assert "approve" in review_done.metadata_["verdict"]
        assert review_done.metadata_["issue_count"] == 0
        assert review_done.duration_ms is not None

    async def test_pr_opened_event_has_url_and_number(
        self,
        run_engine: RunEngine,
        sample_task_request: TaskRequest,
        async_session: AsyncSession,
    ):
        """PR opened event must include URL and PR number."""
        with patch("asyncio.create_subprocess_exec", return_value=_make_git_mock()):
            response = await run_engine.execute_run(sample_task_request)

        events = await get_run_events(async_session, response.id)
        pr_event = next(e for e in events if "PR #99 opened" in e.message)
        assert pr_event.metadata_["url"] == "https://github.com/sinethxyz/unicorn-app/pull/99"
        assert pr_event.metadata_["number"] == 99
        assert pr_event.metadata_["artifact"] == "pr_metadata.json"

    async def test_completed_event_is_final(
        self,
        run_engine: RunEngine,
        sample_task_request: TaskRequest,
        async_session: AsyncSession,
    ):
        """The 'Run completed successfully' event must be the last event."""
        with patch("asyncio.create_subprocess_exec", return_value=_make_git_mock()):
            response = await run_engine.execute_run(sample_task_request)

        events = await get_run_events(async_session, response.id)
        assert events[-1].message == "Run completed successfully"
        assert events[-1].state == RunState.COMPLETED.value

    async def test_event_count_minimum(
        self,
        run_engine: RunEngine,
        sample_task_request: TaskRequest,
        async_session: AsyncSession,
    ):
        """A happy path run should produce at least 15 events.

        queued, creating_worktree, worktree_created, planning(transition),
        planning_started, plan_completed, implementing(transition),
        impl_started, impl_completed, verifying(transition), verification_started,
        per-check events (3), verification_passed_event, verification_passed(transition),
        reviewing(transition), review_started, review_completed,
        pr_opened(transition), pr_opened_event, completed(transition).
        """
        with patch("asyncio.create_subprocess_exec", return_value=_make_git_mock()):
            response = await run_engine.execute_run(sample_task_request)

        events = await get_run_events(async_session, response.id)
        # At minimum: queued + transitions (8) + intra-phase events (12+)
        assert len(events) >= 15


# ---------------------------------------------------------------------------
# Failure path event logging
# ---------------------------------------------------------------------------


class TestFailurePathEventLogging:
    """Verify events are correctly emitted during failure scenarios."""

    async def test_planning_failure_emits_planning_failed_event(
        self,
        run_engine: RunEngine,
        sample_task_request: TaskRequest,
        async_session: AsyncSession,
        mock_agent_runner,
    ):
        """Planning failure must emit a 'Planning failed' event with error metadata."""
        mock_agent_runner.run_planner = AsyncMock(
            side_effect=RuntimeError("Model timeout"),
        )

        response = await run_engine.execute_run(sample_task_request)
        assert response.state == RunState.PLAN_FAILED

        events = await get_run_events(async_session, response.id)
        messages = [e.message for e in events]

        assert any("Planning started" in m for m in messages)
        assert any("Planning failed: Model timeout" in m for m in messages)

        fail_event = next(e for e in events if "Planning failed:" in e.message and e.state == "planning")
        assert fail_event.metadata_["error"] == "Model timeout"

    async def test_implementation_failure_emits_error_event(
        self,
        run_engine: RunEngine,
        sample_task_request: TaskRequest,
        async_session: AsyncSession,
        mock_agent_runner,
    ):
        """Implementation failure must emit proper error events."""
        mock_agent_runner.run_implementer = AsyncMock(
            side_effect=RuntimeError("Tool crashed"),
        )

        response = await run_engine.execute_run(sample_task_request)
        assert response.state == RunState.ERRORED

        events = await get_run_events(async_session, response.id)
        messages = [e.message for e in events]

        assert any("Implementation started" in m for m in messages)
        # The transition event should have the error info
        errored_events = [e for e in events if e.state == "errored"]
        assert len(errored_events) >= 1

    async def test_verification_failure_emits_per_check_and_overall_events(
        self,
        run_engine: RunEngine,
        sample_task_request: TaskRequest,
        async_session: AsyncSession,
        mock_verification_runner,
    ):
        """Verification failure must emit per-check events and overall failure."""
        mock_verification_runner.run_all = AsyncMock(return_value=([
            VerificationResult(check_type="go_build", passed=True, output="ok", duration_ms=1000),
            VerificationResult(check_type="go_test", passed=False, output="FAIL: TestHandler", duration_ms=2000),
        ], False))

        with patch("asyncio.create_subprocess_exec", return_value=_make_git_mock()):
            response = await run_engine.execute_run(sample_task_request)

        assert response.state == RunState.VERIFICATION_FAILED

        events = await get_run_events(async_session, response.id)
        messages = [e.message for e in events]

        assert any("go_build passed" in m for m in messages)
        assert any("go_test failed" in m for m in messages)
        assert any("Verification failed" == m for m in messages)

        # The go_test failed event should have output_snippet
        test_fail = next(e for e in events if "go_test failed" in e.message)
        assert "FAIL: TestHandler" in test_fail.metadata_["output_snippet"]

    async def test_review_rejection_emits_review_events(
        self,
        run_engine: RunEngine,
        sample_task_request: TaskRequest,
        async_session: AsyncSession,
        mock_agent_runner,
        rejected_review,
    ):
        """Review rejection must emit review started, verdict, and failure events."""
        mock_agent_runner.run_reviewer = AsyncMock(return_value=rejected_review)

        with patch("asyncio.create_subprocess_exec", return_value=_make_git_mock()):
            response = await run_engine.execute_run(sample_task_request)

        assert response.state == RunState.REVIEW_FAILED

        events = await get_run_events(async_session, response.id)
        messages = [e.message for e in events]

        assert any("Blind review started" in m for m in messages)
        assert any("Review verdict: reject" in m for m in messages)

        # The transition event to review_failed should have verdict metadata
        fail_events = [e for e in events if e.state == "review_failed"]
        assert len(fail_events) >= 1

    async def test_unexpected_error_emits_error_event_with_traceback(
        self,
        run_engine: RunEngine,
        sample_task_request: TaskRequest,
        async_session: AsyncSession,
        mock_worktree_manager,
    ):
        """Unexpected errors must emit an errored event with traceback metadata."""
        mock_worktree_manager.create = AsyncMock(
            side_effect=RuntimeError("Disk full"),
        )

        response = await run_engine.execute_run(sample_task_request)
        assert response.state == RunState.ERRORED

        events = await get_run_events(async_session, response.id)
        error_events = [e for e in events if e.state == "errored"]
        assert len(error_events) >= 1

        err = error_events[0]
        assert "Run failed:" in err.message
        assert "traceback" in err.metadata_
        assert "Disk full" in err.metadata_["traceback"]


# ---------------------------------------------------------------------------
# Cancel and retry event logging
# ---------------------------------------------------------------------------


class TestCancelRetryEventLogging:
    """Verify cancel and retry emit proper events."""

    async def test_cancel_emits_event_with_previous_state(
        self,
        run_engine: RunEngine,
        sample_task_request: TaskRequest,
        async_session: AsyncSession,
    ):
        """Cancelling a run must emit an event with the previous state in metadata."""
        from foundry.db.queries.runs import create_run

        run = await create_run(async_session, sample_task_request)
        run_id = run.id

        response = await run_engine.cancel_run(run_id)
        assert response.state == RunState.CANCELLED

        events = await get_run_events(async_session, run_id)
        cancel_event = next(e for e in events if e.state == "cancelled")
        assert "Run cancelled by user" in cancel_event.message
        assert cancel_event.metadata_["previous_state"] == "queued"

    async def test_retry_emits_event_with_previous_state(
        self,
        run_engine: RunEngine,
        sample_task_request: TaskRequest,
        async_session: AsyncSession,
        mock_agent_runner,
    ):
        """Retrying a failed run must emit a re-queued event with previous state."""
        mock_agent_runner.run_planner = AsyncMock(
            side_effect=RuntimeError("Planner crashed"),
        )

        response = await run_engine.execute_run(sample_task_request)
        assert response.state == RunState.PLAN_FAILED

        retry_response = await run_engine.retry_run(response.id)
        assert retry_response.state == RunState.QUEUED

        events = await get_run_events(async_session, response.id)
        retry_event = next(
            e for e in events
            if "re-queued" in e.message
        )
        assert retry_event.metadata_["previous_state"] == "plan_failed"


# ---------------------------------------------------------------------------
# Event ordering integrity
# ---------------------------------------------------------------------------


class TestEventOrdering:
    """Verify the event timeline tells a coherent lifecycle story."""

    async def test_state_transitions_appear_in_order(
        self,
        run_engine: RunEngine,
        sample_task_request: TaskRequest,
        async_session: AsyncSession,
    ):
        """State transition events must appear in lifecycle order."""
        with patch("asyncio.create_subprocess_exec", return_value=_make_git_mock()):
            response = await run_engine.execute_run(sample_task_request)

        events = await get_run_events(async_session, response.id)

        # Extract the ordered list of states from transition events
        transition_states = []
        seen = set()
        for e in events:
            if e.state not in seen:
                transition_states.append(e.state)
                seen.add(e.state)

        # Verify the happy path order
        expected_order = [
            "queued",
            "creating_worktree",
            "planning",
            "implementing",
            "verifying",
            "verification_passed",
            "reviewing",
            "pr_opened",
            "completed",
        ]
        # All expected states must appear in order
        idx = 0
        for expected in expected_order:
            while idx < len(transition_states) and transition_states[idx] != expected:
                idx += 1
            assert idx < len(transition_states), (
                f"Expected state '{expected}' not found in order. "
                f"Got: {transition_states}"
            )
            idx += 1
