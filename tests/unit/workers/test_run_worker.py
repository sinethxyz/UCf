"""Tests for the RunWorker Redis consumer."""

import json
import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from foundry.contracts.run_models import RunResponse
from foundry.contracts.shared import RunState
from workers.run_worker import QUEUE_KEY, RunWorker


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def mock_engine():
    engine = AsyncMock()
    engine.execute_run = AsyncMock()
    return engine


@pytest.fixture
def worker(mock_engine):
    return RunWorker(redis_url="redis://localhost:6379", engine=mock_engine)


def _task_payload(run_id: uuid.UUID | None = None) -> dict:
    return {
        "_run_id": str(run_id or uuid.uuid4()),
        "task_type": "bug_fix",
        "repo": "unicorn-app",
        "base_branch": "main",
        "title": "Fix pagination bug",
        "prompt": "Fix the off-by-one error in search pagination",
        "mcp_profile": "none",
    }


# ---------------------------------------------------------------------------
# process_task
# ---------------------------------------------------------------------------

class TestProcessTask:
    async def test_process_task_calls_engine(self, worker, mock_engine):
        payload = _task_payload()
        mock_engine.execute_run.return_value = MagicMock()

        await worker.process_task(payload)

        mock_engine.execute_run.assert_called_once()
        task_request = mock_engine.execute_run.call_args[0][0]
        assert task_request.task_type.value == "bug_fix"
        assert task_request.title == "Fix pagination bug"

    async def test_process_task_strips_run_id(self, worker, mock_engine):
        """_run_id is internal metadata and should not be passed to TaskRequest."""
        payload = _task_payload()
        mock_engine.execute_run.return_value = MagicMock()

        await worker.process_task(payload)

        task_request = mock_engine.execute_run.call_args[0][0]
        assert not hasattr(task_request, "_run_id")

    async def test_process_task_logs_on_engine_error(self, worker, mock_engine):
        payload = _task_payload()
        mock_engine.execute_run.side_effect = RuntimeError("Worktree creation failed")

        # Should not raise — errors are caught and logged
        await worker.process_task(payload)
        mock_engine.execute_run.assert_called_once()

    async def test_process_task_rejects_invalid_payload(self, worker, mock_engine):
        """Invalid payload should raise a validation error."""
        bad_payload = {"task_type": "nonexistent", "repo": "bad"}

        with pytest.raises(Exception):
            await worker.process_task(bad_payload)


# ---------------------------------------------------------------------------
# start / shutdown
# ---------------------------------------------------------------------------

class TestStartShutdown:
    async def test_start_connects_to_redis(self, worker):
        mock_redis = AsyncMock()
        mock_redis.brpop = AsyncMock(return_value=None)
        mock_redis.aclose = AsyncMock()

        with patch("workers.run_worker.aioredis.from_url", return_value=mock_redis):
            async def stop_after_one_iteration(*args, **kwargs):
                worker._running = False
                return None

            mock_redis.brpop.side_effect = stop_after_one_iteration
            await worker.start()

        mock_redis.aclose.assert_called_once()

    async def test_start_processes_messages(self, worker, mock_engine):
        payload = json.dumps(_task_payload())
        mock_engine.execute_run.return_value = MagicMock()

        mock_redis = AsyncMock()
        mock_redis.aclose = AsyncMock()
        call_count = 0

        async def brpop_side_effect(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return (QUEUE_KEY, payload)
            worker._running = False
            return None

        mock_redis.brpop = AsyncMock(side_effect=brpop_side_effect)

        with patch("workers.run_worker.aioredis.from_url", return_value=mock_redis):
            await worker.start()

        mock_engine.execute_run.assert_called_once()

    async def test_start_continues_on_bad_payload(self, worker, mock_engine):
        """Worker should log and continue when a payload is invalid JSON."""
        mock_redis = AsyncMock()
        mock_redis.aclose = AsyncMock()
        call_count = 0

        async def brpop_side_effect(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return (QUEUE_KEY, "not valid json {{{")
            worker._running = False
            return None

        mock_redis.brpop = AsyncMock(side_effect=brpop_side_effect)

        with patch("workers.run_worker.aioredis.from_url", return_value=mock_redis):
            await worker.start()

        mock_engine.execute_run.assert_not_called()

    async def test_shutdown_sets_running_false(self, worker):
        await worker.shutdown()
        assert worker._running is False

    async def test_start_uses_brpop_with_timeout(self, worker):
        mock_redis = AsyncMock()
        mock_redis.aclose = AsyncMock()

        async def stop_immediately(*args, **kwargs):
            worker._running = False
            return None

        mock_redis.brpop = AsyncMock(side_effect=stop_immediately)

        with patch("workers.run_worker.aioredis.from_url", return_value=mock_redis):
            await worker.start()

        mock_redis.brpop.assert_called_with(QUEUE_KEY, timeout=5)
