"""Tests for the verification lifecycle in _run_verification().

Validates state transitions, artifact storage, error handling, and DB
persistence for both passing and failing verification scenarios.
"""

import json
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock
from uuid import UUID

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from foundry.contracts.shared import MCPProfile, RunState, TaskType
from foundry.contracts.task_types import TaskRequest
from foundry.db.queries.artifacts import get_artifacts
from foundry.db.queries.runs import create_run, get_run, get_run_events
from foundry.orchestration.run_engine import VALID_TRANSITIONS, RunEngine
from foundry.storage.artifact_store import ArtifactStore, ArtifactType
from foundry.verification.go_verify import VerificationResult


# ---------------------------------------------------------------------------
# Shared constants and helpers
# ---------------------------------------------------------------------------


SAMPLE_DIFF = """\
diff --git a/services/api/search/handler.go b/services/api/search/handler.go
--- a/services/api/search/handler.go
+++ b/services/api/search/handler.go
@@ -10,7 +10,7 @@
-    offset := (page - 1) * pageSize + 1
+    offset := (page - 1) * pageSize
diff --git a/services/api/search/handler_test.go b/services/api/search/handler_test.go
--- a/services/api/search/handler_test.go
+++ b/services/api/search/handler_test.go
@@ -100,6 +100,20 @@
+func TestSearch_Pagination_FirstPageOffset(t *testing.T) {
+    // regression test for off-by-one
+}
"""


def _make_engine(
    session: AsyncSession,
    artifact_store: ArtifactStore,
    verification_runner: MagicMock,
) -> RunEngine:
    """Create a RunEngine with only session, artifact_store, and verification_runner wired."""
    return RunEngine(
        session=session,
        artifact_store=artifact_store,
        worktree_manager=MagicMock(),
        agent_runner=MagicMock(),
        pr_creator=MagicMock(),
        verification_runner=verification_runner,
    )


async def _setup_run_in_implementing_state(
    session: AsyncSession,
    engine: RunEngine,
    task_request: TaskRequest,
    artifact_store: ArtifactStore,
) -> UUID:
    """Create a run and advance it to IMPLEMENTING state with a stored diff artifact."""
    from foundry.db.queries import artifacts as artifact_queries

    run = await create_run(session, task_request)
    run_id = run.id

    transitions = [
        (RunState.QUEUED, RunState.CREATING_WORKTREE),
        (RunState.CREATING_WORKTREE, RunState.PLANNING),
        (RunState.PLANNING, RunState.IMPLEMENTING),
    ]
    for from_s, to_s in transitions:
        await engine._transition(run_id, from_s, to_s, f"{from_s.value} -> {to_s.value}")

    # Store a diff artifact so _run_verification can extract changed files
    storage_path = await artifact_store.store(run_id, ArtifactType.DIFF, SAMPLE_DIFF)
    await artifact_queries.store_artifact(
        session, run_id, ArtifactType.DIFF.value,
        storage_path, len(SAMPLE_DIFF.encode()),
    )

    return run_id


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
def artifact_store(tmp_path: Path) -> ArtifactStore:
    return ArtifactStore(base_path=str(tmp_path / "artifacts"))


@pytest.fixture
def passing_verification_runner() -> MagicMock:
    runner = MagicMock()
    runner.run_all = AsyncMock(return_value=([
        VerificationResult(check_type="go_build", passed=True, output="ok", duration_ms=500),
        VerificationResult(check_type="go_vet", passed=True, output="ok", duration_ms=300),
        VerificationResult(check_type="go_test", passed=True, output="PASS", duration_ms=2000),
    ], True))
    return runner


@pytest.fixture
def failing_verification_runner() -> MagicMock:
    runner = MagicMock()
    runner.run_all = AsyncMock(return_value=([
        VerificationResult(check_type="go_build", passed=True, output="ok", duration_ms=500),
        VerificationResult(check_type="go_test", passed=False, output="FAIL: TestPagination", duration_ms=1500),
    ], False))
    return runner


# ---------------------------------------------------------------------------
# Test pass path
# ---------------------------------------------------------------------------


class TestVerificationPassPath:
    """Verification passes -> VERIFICATION_PASSED, artifacts stored, events emitted."""

    async def test_returns_true_on_pass(
        self,
        async_session: AsyncSession,
        artifact_store: ArtifactStore,
        passing_verification_runner: MagicMock,
        sample_task_request: TaskRequest,
    ):
        engine = _make_engine(async_session, artifact_store, passing_verification_runner)
        run_id = await _setup_run_in_implementing_state(
            async_session, engine, sample_task_request, artifact_store,
        )

        result = await engine._run_verification(run_id, "/tmp/worktree", sample_task_request)

        assert result is True

    async def test_transitions_to_verification_passed(
        self,
        async_session: AsyncSession,
        artifact_store: ArtifactStore,
        passing_verification_runner: MagicMock,
        sample_task_request: TaskRequest,
    ):
        engine = _make_engine(async_session, artifact_store, passing_verification_runner)
        run_id = await _setup_run_in_implementing_state(
            async_session, engine, sample_task_request, artifact_store,
        )

        await engine._run_verification(run_id, "/tmp/worktree", sample_task_request)

        run = await get_run(async_session, run_id)
        assert run is not None
        assert run.state == RunState.VERIFICATION_PASSED.value

    async def test_stores_verification_json_artifact(
        self,
        async_session: AsyncSession,
        artifact_store: ArtifactStore,
        passing_verification_runner: MagicMock,
        sample_task_request: TaskRequest,
    ):
        engine = _make_engine(async_session, artifact_store, passing_verification_runner)
        run_id = await _setup_run_in_implementing_state(
            async_session, engine, sample_task_request, artifact_store,
        )

        await engine._run_verification(run_id, "/tmp/worktree", sample_task_request)

        artifacts = await artifact_store.list_artifacts(run_id)
        verification_artifacts = [a for a in artifacts if "verification" in a]
        assert len(verification_artifacts) == 1

        content = json.loads(await artifact_store.retrieve(verification_artifacts[0]))
        assert len(content) == 3
        assert all(item["passed"] for item in content)

    async def test_registers_artifact_in_db_with_checksum(
        self,
        async_session: AsyncSession,
        artifact_store: ArtifactStore,
        passing_verification_runner: MagicMock,
        sample_task_request: TaskRequest,
    ):
        engine = _make_engine(async_session, artifact_store, passing_verification_runner)
        run_id = await _setup_run_in_implementing_state(
            async_session, engine, sample_task_request, artifact_store,
        )

        await engine._run_verification(run_id, "/tmp/worktree", sample_task_request)

        db_artifacts = await get_artifacts(async_session, run_id)
        verification_db = [a for a in db_artifacts if a.artifact_type == "verification"]
        assert len(verification_db) == 1
        assert verification_db[0].checksum is not None
        assert verification_db[0].size_bytes is not None
        assert verification_db[0].size_bytes > 0

    async def test_emits_verifying_and_passed_events(
        self,
        async_session: AsyncSession,
        artifact_store: ArtifactStore,
        passing_verification_runner: MagicMock,
        sample_task_request: TaskRequest,
    ):
        engine = _make_engine(async_session, artifact_store, passing_verification_runner)
        run_id = await _setup_run_in_implementing_state(
            async_session, engine, sample_task_request, artifact_store,
        )

        await engine._run_verification(run_id, "/tmp/worktree", sample_task_request)

        events = await get_run_events(async_session, run_id)
        event_states = [e.state for e in events]
        assert "verifying" in event_states
        assert "verification_passed" in event_states

    async def test_pass_does_not_set_error_message(
        self,
        async_session: AsyncSession,
        artifact_store: ArtifactStore,
        passing_verification_runner: MagicMock,
        sample_task_request: TaskRequest,
    ):
        engine = _make_engine(async_session, artifact_store, passing_verification_runner)
        run_id = await _setup_run_in_implementing_state(
            async_session, engine, sample_task_request, artifact_store,
        )

        await engine._run_verification(run_id, "/tmp/worktree", sample_task_request)

        run = await get_run(async_session, run_id)
        assert run is not None
        assert run.error_message is None

    async def test_extracts_changed_files_from_diff_artifact(
        self,
        async_session: AsyncSession,
        artifact_store: ArtifactStore,
        passing_verification_runner: MagicMock,
        sample_task_request: TaskRequest,
    ):
        engine = _make_engine(async_session, artifact_store, passing_verification_runner)
        run_id = await _setup_run_in_implementing_state(
            async_session, engine, sample_task_request, artifact_store,
        )

        await engine._run_verification(run_id, "/tmp/worktree", sample_task_request)

        call_args = passing_verification_runner.run_all.call_args
        changed_files = call_args[0][1]  # Second positional arg
        assert "services/api/search/handler.go" in changed_files
        assert "services/api/search/handler_test.go" in changed_files

    async def test_passes_run_id_and_session_to_runner(
        self,
        async_session: AsyncSession,
        artifact_store: ArtifactStore,
        passing_verification_runner: MagicMock,
        sample_task_request: TaskRequest,
    ):
        engine = _make_engine(async_session, artifact_store, passing_verification_runner)
        run_id = await _setup_run_in_implementing_state(
            async_session, engine, sample_task_request, artifact_store,
        )

        await engine._run_verification(run_id, "/tmp/worktree", sample_task_request)

        call_kwargs = passing_verification_runner.run_all.call_args.kwargs
        assert call_kwargs["run_id"] == run_id
        assert call_kwargs["session"] is async_session


# ---------------------------------------------------------------------------
# Test fail path
# ---------------------------------------------------------------------------


class TestVerificationFailPath:
    """Verification fails -> VERIFICATION_FAILED, error_message set, no review."""

    async def test_returns_false_on_fail(
        self,
        async_session: AsyncSession,
        artifact_store: ArtifactStore,
        failing_verification_runner: MagicMock,
        sample_task_request: TaskRequest,
    ):
        engine = _make_engine(async_session, artifact_store, failing_verification_runner)
        run_id = await _setup_run_in_implementing_state(
            async_session, engine, sample_task_request, artifact_store,
        )

        result = await engine._run_verification(run_id, "/tmp/worktree", sample_task_request)

        assert result is False

    async def test_transitions_to_verification_failed(
        self,
        async_session: AsyncSession,
        artifact_store: ArtifactStore,
        failing_verification_runner: MagicMock,
        sample_task_request: TaskRequest,
    ):
        engine = _make_engine(async_session, artifact_store, failing_verification_runner)
        run_id = await _setup_run_in_implementing_state(
            async_session, engine, sample_task_request, artifact_store,
        )

        await engine._run_verification(run_id, "/tmp/worktree", sample_task_request)

        run = await get_run(async_session, run_id)
        assert run is not None
        assert run.state == RunState.VERIFICATION_FAILED.value

    async def test_sets_error_message_with_failed_checks(
        self,
        async_session: AsyncSession,
        artifact_store: ArtifactStore,
        failing_verification_runner: MagicMock,
        sample_task_request: TaskRequest,
    ):
        engine = _make_engine(async_session, artifact_store, failing_verification_runner)
        run_id = await _setup_run_in_implementing_state(
            async_session, engine, sample_task_request, artifact_store,
        )

        await engine._run_verification(run_id, "/tmp/worktree", sample_task_request)

        run = await get_run(async_session, run_id)
        assert run is not None
        assert run.error_message is not None
        assert "go_test" in run.error_message
        assert "Verification failed" in run.error_message

    async def test_emits_verifying_and_failed_events(
        self,
        async_session: AsyncSession,
        artifact_store: ArtifactStore,
        failing_verification_runner: MagicMock,
        sample_task_request: TaskRequest,
    ):
        engine = _make_engine(async_session, artifact_store, failing_verification_runner)
        run_id = await _setup_run_in_implementing_state(
            async_session, engine, sample_task_request, artifact_store,
        )

        await engine._run_verification(run_id, "/tmp/worktree", sample_task_request)

        events = await get_run_events(async_session, run_id)
        event_states = [e.state for e in events]
        assert "verifying" in event_states
        assert "verification_failed" in event_states

        # The failure event message should describe what failed
        fail_events = [e for e in events if e.state == "verification_failed"]
        assert len(fail_events) == 1
        assert "go_test" in fail_events[0].message


# ---------------------------------------------------------------------------
# Test artifact storage on failure
# ---------------------------------------------------------------------------


class TestVerificationArtifactOnFailure:
    """verification.json is stored even when checks fail."""

    async def test_stores_verification_json_on_failure(
        self,
        async_session: AsyncSession,
        artifact_store: ArtifactStore,
        failing_verification_runner: MagicMock,
        sample_task_request: TaskRequest,
    ):
        engine = _make_engine(async_session, artifact_store, failing_verification_runner)
        run_id = await _setup_run_in_implementing_state(
            async_session, engine, sample_task_request, artifact_store,
        )

        await engine._run_verification(run_id, "/tmp/worktree", sample_task_request)

        artifacts = await artifact_store.list_artifacts(run_id)
        verification_artifacts = [a for a in artifacts if "verification" in a]
        assert len(verification_artifacts) == 1

        content = json.loads(await artifact_store.retrieve(verification_artifacts[0]))
        assert len(content) == 2  # go_build + go_test
        assert content[0]["passed"] is True   # go_build passed
        assert content[1]["passed"] is False  # go_test failed

    async def test_registers_artifact_in_db_on_failure(
        self,
        async_session: AsyncSession,
        artifact_store: ArtifactStore,
        failing_verification_runner: MagicMock,
        sample_task_request: TaskRequest,
    ):
        engine = _make_engine(async_session, artifact_store, failing_verification_runner)
        run_id = await _setup_run_in_implementing_state(
            async_session, engine, sample_task_request, artifact_store,
        )

        await engine._run_verification(run_id, "/tmp/worktree", sample_task_request)

        db_artifacts = await get_artifacts(async_session, run_id)
        verification_db = [a for a in db_artifacts if a.artifact_type == "verification"]
        assert len(verification_db) == 1
        assert verification_db[0].checksum is not None

    async def test_artifact_contains_failure_output(
        self,
        async_session: AsyncSession,
        artifact_store: ArtifactStore,
        failing_verification_runner: MagicMock,
        sample_task_request: TaskRequest,
    ):
        engine = _make_engine(async_session, artifact_store, failing_verification_runner)
        run_id = await _setup_run_in_implementing_state(
            async_session, engine, sample_task_request, artifact_store,
        )

        await engine._run_verification(run_id, "/tmp/worktree", sample_task_request)

        artifacts = await artifact_store.list_artifacts(run_id)
        verification_artifacts = [a for a in artifacts if "verification" in a]
        content = json.loads(await artifact_store.retrieve(verification_artifacts[0]))

        failed_item = [c for c in content if not c["passed"]][0]
        assert failed_item["check_type"] == "go_test"
        assert "FAIL" in failed_item["output"]

    async def test_persists_verification_results_to_db(
        self,
        async_session: AsyncSession,
        artifact_store: ArtifactStore,
        failing_verification_runner: MagicMock,
        sample_task_request: TaskRequest,
    ):
        """verification_runner.run_all is called with session and run_id for DB persistence."""
        engine = _make_engine(async_session, artifact_store, failing_verification_runner)
        run_id = await _setup_run_in_implementing_state(
            async_session, engine, sample_task_request, artifact_store,
        )

        await engine._run_verification(run_id, "/tmp/worktree", sample_task_request)

        call_kwargs = failing_verification_runner.run_all.call_args.kwargs
        assert call_kwargs["run_id"] == run_id
        assert call_kwargs["session"] is async_session


# ---------------------------------------------------------------------------
# Test state transitions
# ---------------------------------------------------------------------------


class TestVerificationStateTransitions:
    """State machine correctness for the verification lifecycle."""

    async def test_implementing_to_verifying_transition(
        self,
        async_session: AsyncSession,
        artifact_store: ArtifactStore,
        passing_verification_runner: MagicMock,
        sample_task_request: TaskRequest,
    ):
        """_run_verification transitions from IMPLEMENTING to VERIFYING first."""
        engine = _make_engine(async_session, artifact_store, passing_verification_runner)
        run_id = await _setup_run_in_implementing_state(
            async_session, engine, sample_task_request, artifact_store,
        )

        await engine._run_verification(run_id, "/tmp/worktree", sample_task_request)

        events = await get_run_events(async_session, run_id)
        event_states = [e.state for e in events]
        idx_verifying = event_states.index("verifying")
        idx_passed = event_states.index("verification_passed")
        assert idx_verifying < idx_passed

    async def test_full_pass_transition_chain(
        self,
        async_session: AsyncSession,
        artifact_store: ArtifactStore,
        passing_verification_runner: MagicMock,
        sample_task_request: TaskRequest,
    ):
        """IMPLEMENTING -> VERIFYING -> VERIFICATION_PASSED."""
        engine = _make_engine(async_session, artifact_store, passing_verification_runner)
        run_id = await _setup_run_in_implementing_state(
            async_session, engine, sample_task_request, artifact_store,
        )

        await engine._run_verification(run_id, "/tmp/worktree", sample_task_request)

        run = await get_run(async_session, run_id)
        assert run.state == RunState.VERIFICATION_PASSED.value

        events = await get_run_events(async_session, run_id)
        event_states = [e.state for e in events]
        # Last two events should be verifying -> verification_passed
        assert event_states[-2] == "verifying"
        assert event_states[-1] == "verification_passed"

    async def test_full_fail_transition_chain(
        self,
        async_session: AsyncSession,
        artifact_store: ArtifactStore,
        failing_verification_runner: MagicMock,
        sample_task_request: TaskRequest,
    ):
        """IMPLEMENTING -> VERIFYING -> VERIFICATION_FAILED."""
        engine = _make_engine(async_session, artifact_store, failing_verification_runner)
        run_id = await _setup_run_in_implementing_state(
            async_session, engine, sample_task_request, artifact_store,
        )

        await engine._run_verification(run_id, "/tmp/worktree", sample_task_request)

        run = await get_run(async_session, run_id)
        assert run.state == RunState.VERIFICATION_FAILED.value

        events = await get_run_events(async_session, run_id)
        event_states = [e.state for e in events]
        assert event_states[-2] == "verifying"
        assert event_states[-1] == "verification_failed"

    async def test_verification_failed_only_allows_retry(self):
        """VERIFICATION_FAILED can only transition back to QUEUED (retry)."""
        allowed = VALID_TRANSITIONS[RunState.VERIFICATION_FAILED]
        assert allowed == {RunState.QUEUED}

    async def test_verification_failed_is_retryable(
        self,
        async_session: AsyncSession,
        artifact_store: ArtifactStore,
        failing_verification_runner: MagicMock,
        sample_task_request: TaskRequest,
    ):
        """A run in VERIFICATION_FAILED state can be retried back to QUEUED."""
        engine = _make_engine(async_session, artifact_store, failing_verification_runner)
        run_id = await _setup_run_in_implementing_state(
            async_session, engine, sample_task_request, artifact_store,
        )

        await engine._run_verification(run_id, "/tmp/worktree", sample_task_request)

        response = await engine.retry_run(run_id)
        assert response.state == RunState.QUEUED
