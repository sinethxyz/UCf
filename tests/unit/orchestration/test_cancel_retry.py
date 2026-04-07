"""Tests for RunEngine.cancel_run() and retry_run() operations."""

import json
from unittest.mock import AsyncMock, MagicMock

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from foundry.contracts.shared import RunState
from foundry.contracts.task_types import TaskRequest
from foundry.db.queries.runs import create_run, get_run
from foundry.orchestration.run_engine import (
    QUEUE_KEY,
    VALID_TRANSITIONS,
    RunEngine,
    _CANCELLABLE_STATES,
    _RETRYABLE_STATES,
)


@pytest.fixture
def mock_worktree_manager() -> MagicMock:
    mgr = MagicMock()
    mgr.cleanup = AsyncMock()
    return mgr


@pytest.fixture
def mock_redis() -> AsyncMock:
    r = AsyncMock()
    r.lpush = AsyncMock()
    return r


@pytest.fixture
def run_engine(
    async_session: AsyncSession,
    mock_worktree_manager: MagicMock,
    mock_redis: AsyncMock,
) -> RunEngine:
    """Return a RunEngine with mock dependencies (only session is real)."""
    return RunEngine(
        session=async_session,
        artifact_store=MagicMock(),
        worktree_manager=mock_worktree_manager,
        agent_runner=MagicMock(),
        pr_creator=MagicMock(),
        verification_runner=MagicMock(),
        redis=mock_redis,
    )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


async def _transition_run_to(
    engine: RunEngine,
    run_id,
    target_state: RunState,
) -> None:
    """Walk the run through the happy path (or failure branch) to reach target_state."""
    paths: dict[RunState, list[tuple[RunState, RunState]]] = {
        RunState.QUEUED: [],
        RunState.CREATING_WORKTREE: [
            (RunState.QUEUED, RunState.CREATING_WORKTREE),
        ],
        RunState.PLANNING: [
            (RunState.QUEUED, RunState.CREATING_WORKTREE),
            (RunState.CREATING_WORKTREE, RunState.PLANNING),
        ],
        RunState.IMPLEMENTING: [
            (RunState.QUEUED, RunState.CREATING_WORKTREE),
            (RunState.CREATING_WORKTREE, RunState.PLANNING),
            (RunState.PLANNING, RunState.IMPLEMENTING),
        ],
        RunState.VERIFYING: [
            (RunState.QUEUED, RunState.CREATING_WORKTREE),
            (RunState.CREATING_WORKTREE, RunState.PLANNING),
            (RunState.PLANNING, RunState.IMPLEMENTING),
            (RunState.IMPLEMENTING, RunState.VERIFYING),
        ],
        RunState.REVIEWING: [
            (RunState.QUEUED, RunState.CREATING_WORKTREE),
            (RunState.CREATING_WORKTREE, RunState.PLANNING),
            (RunState.PLANNING, RunState.IMPLEMENTING),
            (RunState.IMPLEMENTING, RunState.VERIFYING),
            (RunState.VERIFYING, RunState.VERIFICATION_PASSED),
            (RunState.VERIFICATION_PASSED, RunState.REVIEWING),
        ],
        RunState.PLAN_FAILED: [
            (RunState.QUEUED, RunState.CREATING_WORKTREE),
            (RunState.CREATING_WORKTREE, RunState.PLANNING),
            (RunState.PLANNING, RunState.PLAN_FAILED),
        ],
        RunState.VERIFICATION_FAILED: [
            (RunState.QUEUED, RunState.CREATING_WORKTREE),
            (RunState.CREATING_WORKTREE, RunState.PLANNING),
            (RunState.PLANNING, RunState.IMPLEMENTING),
            (RunState.IMPLEMENTING, RunState.VERIFYING),
            (RunState.VERIFYING, RunState.VERIFICATION_FAILED),
        ],
        RunState.REVIEW_FAILED: [
            (RunState.QUEUED, RunState.CREATING_WORKTREE),
            (RunState.CREATING_WORKTREE, RunState.PLANNING),
            (RunState.PLANNING, RunState.IMPLEMENTING),
            (RunState.IMPLEMENTING, RunState.VERIFYING),
            (RunState.VERIFYING, RunState.VERIFICATION_PASSED),
            (RunState.VERIFICATION_PASSED, RunState.REVIEWING),
            (RunState.REVIEWING, RunState.REVIEW_FAILED),
        ],
        RunState.VERIFICATION_PASSED: [
            (RunState.QUEUED, RunState.CREATING_WORKTREE),
            (RunState.CREATING_WORKTREE, RunState.PLANNING),
            (RunState.PLANNING, RunState.IMPLEMENTING),
            (RunState.IMPLEMENTING, RunState.VERIFYING),
            (RunState.VERIFYING, RunState.VERIFICATION_PASSED),
        ],
        RunState.PR_OPENED: [
            (RunState.QUEUED, RunState.CREATING_WORKTREE),
            (RunState.CREATING_WORKTREE, RunState.PLANNING),
            (RunState.PLANNING, RunState.IMPLEMENTING),
            (RunState.IMPLEMENTING, RunState.VERIFYING),
            (RunState.VERIFYING, RunState.VERIFICATION_PASSED),
            (RunState.VERIFICATION_PASSED, RunState.REVIEWING),
            (RunState.REVIEWING, RunState.PR_OPENED),
        ],
        RunState.ERRORED: [
            (RunState.QUEUED, RunState.CREATING_WORKTREE),
            (RunState.CREATING_WORKTREE, RunState.ERRORED),
        ],
        RunState.COMPLETED: [
            (RunState.QUEUED, RunState.CREATING_WORKTREE),
            (RunState.CREATING_WORKTREE, RunState.PLANNING),
            (RunState.PLANNING, RunState.IMPLEMENTING),
            (RunState.IMPLEMENTING, RunState.VERIFYING),
            (RunState.VERIFYING, RunState.VERIFICATION_PASSED),
            (RunState.VERIFICATION_PASSED, RunState.REVIEWING),
            (RunState.REVIEWING, RunState.PR_OPENED),
            (RunState.PR_OPENED, RunState.COMPLETED),
        ],
        RunState.CANCELLED: [
            (RunState.QUEUED, RunState.CANCELLED),
        ],
    }
    for from_s, to_s in paths[target_state]:
        await engine._transition(run_id, from_s, to_s, f"test: {from_s.value} -> {to_s.value}")


# ===========================================================================
# cancel_run tests
# ===========================================================================


class TestCancelRun:
    """Tests for RunEngine.cancel_run()."""

    @pytest.mark.parametrize("state", list(_CANCELLABLE_STATES))
    async def test_cancel_from_cancellable_state(
        self,
        async_session: AsyncSession,
        sample_task_request: TaskRequest,
        run_engine: RunEngine,
        state: RunState,
    ):
        """cancel_run succeeds from every cancellable state."""
        run = await create_run(async_session, sample_task_request)
        await _transition_run_to(run_engine, run.id, state)

        response = await run_engine.cancel_run(run.id)

        assert response.state == RunState.CANCELLED

        updated = await get_run(async_session, run.id)
        assert updated is not None
        assert updated.state == RunState.CANCELLED.value

    @pytest.mark.parametrize(
        "state",
        [
            RunState.COMPLETED,
            RunState.CANCELLED,
            RunState.ERRORED,
            RunState.VERIFICATION_PASSED,
            RunState.PR_OPENED,
        ],
    )
    async def test_cancel_from_non_cancellable_state_raises(
        self,
        async_session: AsyncSession,
        sample_task_request: TaskRequest,
        run_engine: RunEngine,
        state: RunState,
    ):
        """cancel_run raises ValueError for states not in _CANCELLABLE_STATES."""
        run = await create_run(async_session, sample_task_request)
        await _transition_run_to(run_engine, run.id, state)

        with pytest.raises(ValueError, match="cannot be cancelled"):
            await run_engine.cancel_run(run.id)

    async def test_cancel_not_found_raises(
        self,
        run_engine: RunEngine,
    ):
        """cancel_run raises ValueError for a nonexistent run_id."""
        import uuid

        with pytest.raises(ValueError, match="not found"):
            await run_engine.cancel_run(uuid.uuid4())

    async def test_cancel_cleans_up_worktree(
        self,
        async_session: AsyncSession,
        sample_task_request: TaskRequest,
        run_engine: RunEngine,
        mock_worktree_manager: MagicMock,
    ):
        """cancel_run calls worktree_manager.cleanup when worktree_path is set."""
        run = await create_run(async_session, sample_task_request)
        run.worktree_path = "/tmp/foundry-worktrees/test-wt"
        await async_session.flush()

        await _transition_run_to(run_engine, run.id, RunState.PLANNING)

        await run_engine.cancel_run(run.id)

        mock_worktree_manager.cleanup.assert_awaited_once_with(
            "/tmp/foundry-worktrees/test-wt"
        )

    async def test_cancel_no_worktree_skips_cleanup(
        self,
        async_session: AsyncSession,
        sample_task_request: TaskRequest,
        run_engine: RunEngine,
        mock_worktree_manager: MagicMock,
    ):
        """cancel_run skips cleanup when worktree_path is None."""
        run = await create_run(async_session, sample_task_request)
        # worktree_path is None by default
        await run_engine.cancel_run(run.id)

        mock_worktree_manager.cleanup.assert_not_awaited()

    async def test_cancel_worktree_cleanup_failure_does_not_raise(
        self,
        async_session: AsyncSession,
        sample_task_request: TaskRequest,
        run_engine: RunEngine,
        mock_worktree_manager: MagicMock,
    ):
        """Worktree cleanup errors are swallowed — cancel still succeeds."""
        run = await create_run(async_session, sample_task_request)
        run.worktree_path = "/tmp/foundry-worktrees/bad-wt"
        await async_session.flush()

        mock_worktree_manager.cleanup.side_effect = RuntimeError("rm failed")

        response = await run_engine.cancel_run(run.id)
        assert response.state == RunState.CANCELLED


# ===========================================================================
# retry_run tests
# ===========================================================================


class TestRetryRun:
    """Tests for RunEngine.retry_run()."""

    @pytest.mark.parametrize("state", list(_RETRYABLE_STATES))
    async def test_retry_from_retryable_state(
        self,
        async_session: AsyncSession,
        sample_task_request: TaskRequest,
        run_engine: RunEngine,
        state: RunState,
    ):
        """retry_run succeeds from every retryable state."""
        run = await create_run(async_session, sample_task_request)
        await _transition_run_to(run_engine, run.id, state)

        response = await run_engine.retry_run(run.id)

        assert response.state == RunState.QUEUED

        updated = await get_run(async_session, run.id)
        assert updated is not None
        assert updated.state == RunState.QUEUED.value

    @pytest.mark.parametrize(
        "state",
        [
            RunState.QUEUED,
            RunState.CREATING_WORKTREE,
            RunState.PLANNING,
            RunState.IMPLEMENTING,
            RunState.VERIFYING,
            RunState.COMPLETED,
            RunState.CANCELLED,
        ],
    )
    async def test_retry_from_non_retryable_state_raises(
        self,
        async_session: AsyncSession,
        sample_task_request: TaskRequest,
        run_engine: RunEngine,
        state: RunState,
    ):
        """retry_run raises ValueError for states not in _RETRYABLE_STATES."""
        run = await create_run(async_session, sample_task_request)
        await _transition_run_to(run_engine, run.id, state)

        with pytest.raises(ValueError, match="is not retryable"):
            await run_engine.retry_run(run.id)

    async def test_retry_not_found_raises(
        self,
        run_engine: RunEngine,
    ):
        """retry_run raises ValueError for a nonexistent run_id."""
        import uuid

        with pytest.raises(ValueError, match="not found"):
            await run_engine.retry_run(uuid.uuid4())

    async def test_retry_cleans_up_worktree_and_clears_path(
        self,
        async_session: AsyncSession,
        sample_task_request: TaskRequest,
        run_engine: RunEngine,
        mock_worktree_manager: MagicMock,
    ):
        """retry_run calls worktree cleanup and clears worktree_path on the run."""
        run = await create_run(async_session, sample_task_request)
        run.worktree_path = "/tmp/foundry-worktrees/retry-wt"
        await async_session.flush()

        await _transition_run_to(run_engine, run.id, RunState.PLAN_FAILED)

        await run_engine.retry_run(run.id)

        mock_worktree_manager.cleanup.assert_awaited_once_with(
            "/tmp/foundry-worktrees/retry-wt"
        )

        updated = await get_run(async_session, run.id)
        assert updated is not None
        assert updated.worktree_path is None

    async def test_retry_no_worktree_skips_cleanup(
        self,
        async_session: AsyncSession,
        sample_task_request: TaskRequest,
        run_engine: RunEngine,
        mock_worktree_manager: MagicMock,
    ):
        """retry_run skips cleanup when worktree_path is None."""
        run = await create_run(async_session, sample_task_request)
        await _transition_run_to(run_engine, run.id, RunState.ERRORED)

        await run_engine.retry_run(run.id)

        mock_worktree_manager.cleanup.assert_not_awaited()

    async def test_retry_enqueues_to_redis(
        self,
        async_session: AsyncSession,
        sample_task_request: TaskRequest,
        run_engine: RunEngine,
        mock_redis: AsyncMock,
    ):
        """retry_run pushes the run onto the Redis queue via LPUSH."""
        run = await create_run(async_session, sample_task_request)
        await _transition_run_to(run_engine, run.id, RunState.PLAN_FAILED)

        await run_engine.retry_run(run.id)

        mock_redis.lpush.assert_awaited_once()
        call_args = mock_redis.lpush.call_args
        assert call_args[0][0] == QUEUE_KEY

        payload = json.loads(call_args[0][1])
        assert payload["_run_id"] == str(run.id)
        assert payload["task_type"] == run.task_type
        assert payload["repo"] == run.repo
        assert payload["title"] == run.title

    async def test_retry_without_redis_skips_enqueue(
        self,
        async_session: AsyncSession,
        sample_task_request: TaskRequest,
        mock_worktree_manager: MagicMock,
    ):
        """retry_run succeeds without raising when redis is None."""
        engine = RunEngine(
            session=async_session,
            artifact_store=MagicMock(),
            worktree_manager=mock_worktree_manager,
            agent_runner=MagicMock(),
            pr_creator=MagicMock(),
            verification_runner=MagicMock(),
            redis=None,
        )
        run = await create_run(async_session, sample_task_request)
        await _transition_run_to(engine, run.id, RunState.ERRORED)

        response = await engine.retry_run(run.id)
        assert response.state == RunState.QUEUED

    async def test_retry_worktree_cleanup_failure_does_not_raise(
        self,
        async_session: AsyncSession,
        sample_task_request: TaskRequest,
        run_engine: RunEngine,
        mock_worktree_manager: MagicMock,
    ):
        """Worktree cleanup errors are swallowed — retry still succeeds."""
        run = await create_run(async_session, sample_task_request)
        run.worktree_path = "/tmp/foundry-worktrees/bad-wt"
        await async_session.flush()
        await _transition_run_to(run_engine, run.id, RunState.REVIEW_FAILED)

        mock_worktree_manager.cleanup.side_effect = RuntimeError("rm failed")

        response = await run_engine.retry_run(run.id)
        assert response.state == RunState.QUEUED


# ===========================================================================
# VALID_TRANSITIONS structure tests for cancel/retry
# ===========================================================================


class TestTransitionMapCancelRetry:
    """Verify VALID_TRANSITIONS supports cancel and retry paths."""

    def test_all_cancellable_states_allow_cancelled_transition(self):
        """Every state in _CANCELLABLE_STATES must have CANCELLED in VALID_TRANSITIONS."""
        for state in _CANCELLABLE_STATES:
            assert RunState.CANCELLED in VALID_TRANSITIONS[state], (
                f"State {state.value} is cancellable but CANCELLED not in VALID_TRANSITIONS"
            )

    def test_non_cancellable_states_disallow_cancelled_transition(self):
        """States not in _CANCELLABLE_STATES must NOT have CANCELLED in VALID_TRANSITIONS."""
        for state in RunState:
            if state in _CANCELLABLE_STATES:
                continue
            assert RunState.CANCELLED not in VALID_TRANSITIONS.get(state, set()), (
                f"State {state.value} is not cancellable but CANCELLED is in VALID_TRANSITIONS"
            )

    def test_all_retryable_states_allow_queued_transition(self):
        """Every state in _RETRYABLE_STATES must have QUEUED in VALID_TRANSITIONS."""
        for state in _RETRYABLE_STATES:
            assert RunState.QUEUED in VALID_TRANSITIONS[state], (
                f"State {state.value} is retryable but QUEUED not in VALID_TRANSITIONS"
            )

    def test_errored_is_retryable(self):
        """ERRORED must be in _RETRYABLE_STATES."""
        assert RunState.ERRORED in _RETRYABLE_STATES

    def test_errored_can_transition_to_queued(self):
        """ERRORED -> QUEUED must be a valid transition."""
        assert RunState.QUEUED in VALID_TRANSITIONS[RunState.ERRORED]
