"""Tests for migration guard automatic review escalation.

Verifies:
1. Protected path detection matches correct patterns.
2. Bug fix tasks are automatically rejected for protected paths.
3. Allowed task types escalate to LLM migration guard review.
4. Unauthorized task types are automatically rejected.
5. Migration guard integrates correctly with _run_review() lifecycle.
"""

import json
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock
from uuid import UUID

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from foundry.contracts.review_models import ReviewIssue, ReviewVerdict
from foundry.contracts.shared import (
    MCPProfile,
    ReviewSeverity,
    ReviewVerdictType,
    RunState,
    TaskType,
)
from foundry.contracts.task_types import TaskRequest
from foundry.db.queries.runs import create_run, get_run, get_run_events
from foundry.orchestration.run_engine import (
    MIGRATION_GUARD_ALLOWED_TASK_TYPES,
    RunEngine,
    _match_protected_paths,
)
from foundry.storage.artifact_store import ArtifactStore, ArtifactType


# ---------------------------------------------------------------------------
# Shared constants
# ---------------------------------------------------------------------------


SAFE_DIFF = """\
diff --git a/services/api/search/handler.go b/services/api/search/handler.go
--- a/services/api/search/handler.go
+++ b/services/api/search/handler.go
@@ -10,7 +10,7 @@
-    offset := (page - 1) * pageSize + 1
+    offset := (page - 1) * pageSize
"""

MIGRATION_DIFF = """\
diff --git a/migrations/0042_add_signals_table.py b/migrations/0042_add_signals_table.py
--- /dev/null
+++ b/migrations/0042_add_signals_table.py
@@ -0,0 +1,20 @@
+def upgrade():
+    op.create_table("signals", ...)
+
+def downgrade():
+    op.drop_table("signals")
"""

AUTH_DIFF = """\
diff --git a/auth/middleware.go b/auth/middleware.go
--- a/auth/middleware.go
+++ b/auth/middleware.go
@@ -15,7 +15,7 @@
-    if !hasPermission(user, "admin") {
+    if !hasPermission(user, "viewer") {
"""

DOCKERFILE_DIFF = """\
diff --git a/Dockerfile b/Dockerfile
--- a/Dockerfile
+++ b/Dockerfile
@@ -1,4 +1,4 @@
-FROM golang:1.21-alpine
+FROM golang:1.22-alpine
"""

SECRET_PATH_DIFF = """\
diff --git a/config/secrets.yaml b/config/secrets.yaml
--- /dev/null
+++ b/config/secrets.yaml
@@ -0,0 +1,3 @@
+db_password: changeme
"""


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_engine(
    session: AsyncSession,
    artifact_store: ArtifactStore,
    agent_runner: MagicMock,
) -> RunEngine:
    """Create a RunEngine with mocked dependencies."""
    return RunEngine(
        session=session,
        artifact_store=artifact_store,
        worktree_manager=MagicMock(),
        agent_runner=agent_runner,
        pr_creator=MagicMock(),
        verification_runner=MagicMock(),
    )


async def _setup_run_in_verification_passed_state(
    session: AsyncSession,
    engine: RunEngine,
    task_request: TaskRequest,
) -> UUID:
    """Create a run and advance it to VERIFICATION_PASSED state."""
    run = await create_run(session, task_request)
    run_id = run.id

    transitions = [
        (RunState.QUEUED, RunState.CREATING_WORKTREE),
        (RunState.CREATING_WORKTREE, RunState.PLANNING),
        (RunState.PLANNING, RunState.IMPLEMENTING),
        (RunState.IMPLEMENTING, RunState.VERIFYING),
        (RunState.VERIFYING, RunState.VERIFICATION_PASSED),
    ]
    for from_s, to_s in transitions:
        await engine._transition(run_id, from_s, to_s, f"{from_s.value} -> {to_s.value}")

    return run_id


def _make_approve_verdict() -> ReviewVerdict:
    return ReviewVerdict(
        verdict=ReviewVerdictType.APPROVE,
        issues=[],
        summary="Migration looks safe. Backwards compatible, reversible.",
        confidence=0.9,
    )


def _make_reject_verdict() -> ReviewVerdict:
    return ReviewVerdict(
        verdict=ReviewVerdictType.REJECT,
        issues=[
            ReviewIssue(
                severity=ReviewSeverity.CRITICAL,
                file_path="migrations/0042_add_signals_table.py",
                line_range="5-5",
                description="NOT NULL column added without default",
                suggestion="Add a default value or make the column nullable",
            ),
        ],
        summary="Migration adds NOT NULL column without default — forbidden.",
        confidence=0.95,
    )


def _make_request_changes_verdict() -> ReviewVerdict:
    return ReviewVerdict(
        verdict=ReviewVerdictType.REQUEST_CHANGES,
        issues=[
            ReviewIssue(
                severity=ReviewSeverity.MAJOR,
                file_path="migrations/0042_add_signals_table.py",
                line_range="10-10",
                description="Index creation should use CONCURRENTLY",
                suggestion="Use CREATE INDEX CONCURRENTLY to avoid locking",
            ),
        ],
        summary="Migration is mostly safe but needs concurrent index creation.",
        confidence=0.85,
    )


def _make_standard_approve_verdict() -> ReviewVerdict:
    """Standard blind review approve verdict (distinct from migration guard)."""
    return ReviewVerdict(
        verdict=ReviewVerdictType.APPROVE,
        issues=[],
        summary="Code looks good. No issues found.",
        confidence=0.9,
    )


def _make_agent_runner(
    guard_verdict: ReviewVerdict | None = None,
    review_verdict: ReviewVerdict | None = None,
) -> MagicMock:
    """Create a mock AgentRunner with configurable guard and review verdicts."""
    runner = MagicMock()
    if guard_verdict is not None:
        runner.run_migration_guard = AsyncMock(return_value=guard_verdict)
    else:
        runner.run_migration_guard = AsyncMock(return_value=_make_approve_verdict())
    if review_verdict is not None:
        runner.run_reviewer = AsyncMock(return_value=review_verdict)
    else:
        runner.run_reviewer = AsyncMock(return_value=_make_standard_approve_verdict())
    return runner


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def artifact_store(tmp_path: Path) -> ArtifactStore:
    return ArtifactStore(base_path=str(tmp_path / "artifacts"))


@pytest.fixture
def bug_fix_task() -> TaskRequest:
    return TaskRequest(
        task_type=TaskType.BUG_FIX,
        repo="unicorn-app",
        base_branch="main",
        title="Fix auth token validation",
        prompt="Fix the token validation bug in auth middleware",
        target_paths=["auth/middleware.go"],
        mcp_profile=MCPProfile.NONE,
    )


@pytest.fixture
def migration_task() -> TaskRequest:
    return TaskRequest(
        task_type=TaskType.MIGRATION_PLAN,
        repo="unicorn-app",
        base_branch="main",
        title="Add signals table",
        prompt="Create the signals table for event tracking",
        target_paths=["migrations/"],
        mcp_profile=MCPProfile.NONE,
    )


@pytest.fixture
def endpoint_task() -> TaskRequest:
    return TaskRequest(
        task_type=TaskType.ENDPOINT_BUILD,
        repo="unicorn-app",
        base_branch="main",
        title="Add company timeline endpoint",
        prompt="Build GET /v1/companies/{id}/timeline",
        target_paths=["services/api/"],
        mcp_profile=MCPProfile.NONE,
    )


@pytest.fixture
def refactor_task() -> TaskRequest:
    return TaskRequest(
        task_type=TaskType.REFACTOR,
        repo="unicorn-app",
        base_branch="main",
        title="Refactor auth module",
        prompt="Extract shared auth logic into middleware",
        target_paths=["auth/"],
        mcp_profile=MCPProfile.NONE,
    )


@pytest.fixture
def extraction_task() -> TaskRequest:
    """Task type that is NOT authorized for protected path changes."""
    return TaskRequest(
        task_type=TaskType.EXTRACTION_BATCH,
        repo="unicorn-app",
        base_branch="main",
        title="Extract funding signals",
        prompt="Extract funding round data from press releases",
        target_paths=["sources/"],
        mcp_profile=MCPProfile.NONE,
    )


# ---------------------------------------------------------------------------
# Test protected path detection
# ---------------------------------------------------------------------------


class TestProtectedPathDetection:
    """Verify _match_protected_paths correctly identifies protected files."""

    def test_migrations_prefix_detected(self):
        files = ["migrations/0042_add_signals_table.py"]
        assert _match_protected_paths(files) == files

    def test_nested_migrations_prefix_detected(self):
        files = ["foundry/db/migrations/0042_add_signals_table.py"]
        assert _match_protected_paths(files) == files

    def test_auth_prefix_detected(self):
        files = ["auth/middleware.go"]
        assert _match_protected_paths(files) == files

    def test_infra_prefix_detected(self):
        files = ["infra/terraform/main.tf"]
        assert _match_protected_paths(files) == files

    def test_dockerfile_glob_detected(self):
        files = ["Dockerfile"]
        assert _match_protected_paths(files) == files

    def test_dockerfile_with_suffix_detected(self):
        files = ["Dockerfile.prod"]
        assert _match_protected_paths(files) == files

    def test_nested_dockerfile_detected(self):
        files = ["services/api/Dockerfile"]
        assert _match_protected_paths(files) == files

    def test_docker_compose_detected(self):
        files = ["docker-compose.yml"]
        assert _match_protected_paths(files) == files

    def test_docker_compose_override_detected(self):
        files = ["docker-compose.override.yml"]
        assert _match_protected_paths(files) == files

    def test_secret_keyword_detected(self):
        files = ["config/secrets.yaml"]
        assert _match_protected_paths(files) == files

    def test_credential_keyword_detected(self):
        files = ["deploy/credentials.json"]
        assert _match_protected_paths(files) == files

    def test_token_keyword_detected(self):
        files = ["auth/token_store.go"]
        assert _match_protected_paths(files) == files

    def test_case_insensitive_keyword_matching(self):
        files = ["config/AWS_CREDENTIALS.json"]
        assert _match_protected_paths(files) == files

    def test_no_protected_paths_returns_empty(self):
        files = [
            "services/api/search/handler.go",
            "services/api/search/handler_test.go",
            "packages/contracts/openapi.yaml",
        ]
        assert _match_protected_paths(files) == []

    def test_empty_file_list_returns_empty(self):
        assert _match_protected_paths([]) == []

    def test_mixed_protected_and_normal_files(self):
        files = [
            "services/api/search/handler.go",
            "migrations/0042_add_signals_table.py",
            "auth/middleware.go",
            "packages/contracts/openapi.yaml",
        ]
        result = _match_protected_paths(files)
        assert "migrations/0042_add_signals_table.py" in result
        assert "auth/middleware.go" in result
        assert "services/api/search/handler.go" not in result
        assert "packages/contracts/openapi.yaml" not in result

    def test_multiple_protected_patterns_matched(self):
        files = [
            "migrations/0042.py",
            "auth/handler.go",
            "infra/main.tf",
            "Dockerfile",
            "docker-compose.yml",
            "config/secrets.yaml",
        ]
        result = _match_protected_paths(files)
        assert len(result) == 6


# ---------------------------------------------------------------------------
# Test bug_fix auto-reject
# ---------------------------------------------------------------------------


class TestBugFixAutoReject:
    """Bug fix tasks must not modify protected paths — auto-reject without LLM."""

    async def test_bug_fix_auto_rejects_migration_files(
        self,
        async_session: AsyncSession,
        artifact_store: ArtifactStore,
        bug_fix_task: TaskRequest,
    ):
        runner = _make_agent_runner()
        engine = _make_engine(async_session, artifact_store, runner)
        run_id = await _setup_run_in_verification_passed_state(
            async_session, engine, bug_fix_task,
        )

        # Transition to REVIEWING so _check_migration_guard can add events
        await engine._transition(
            run_id, RunState.VERIFICATION_PASSED, RunState.REVIEWING, "test",
        )

        verdict = await engine._check_migration_guard(
            run_id, MIGRATION_DIFF,
            ["migrations/0042_add_signals_table.py"],
            bug_fix_task,
        )

        assert verdict is not None
        assert verdict.verdict == ReviewVerdictType.REJECT

    async def test_bug_fix_auto_reject_includes_file_list(
        self,
        async_session: AsyncSession,
        artifact_store: ArtifactStore,
        bug_fix_task: TaskRequest,
    ):
        runner = _make_agent_runner()
        engine = _make_engine(async_session, artifact_store, runner)
        run_id = await _setup_run_in_verification_passed_state(
            async_session, engine, bug_fix_task,
        )
        await engine._transition(
            run_id, RunState.VERIFICATION_PASSED, RunState.REVIEWING, "test",
        )

        verdict = await engine._check_migration_guard(
            run_id, AUTH_DIFF,
            ["auth/middleware.go"],
            bug_fix_task,
        )

        assert verdict is not None
        assert "auth/middleware.go" in verdict.summary

    async def test_bug_fix_auto_reject_does_not_call_llm(
        self,
        async_session: AsyncSession,
        artifact_store: ArtifactStore,
        bug_fix_task: TaskRequest,
    ):
        runner = _make_agent_runner()
        engine = _make_engine(async_session, artifact_store, runner)
        run_id = await _setup_run_in_verification_passed_state(
            async_session, engine, bug_fix_task,
        )
        await engine._transition(
            run_id, RunState.VERIFICATION_PASSED, RunState.REVIEWING, "test",
        )

        await engine._check_migration_guard(
            run_id, MIGRATION_DIFF,
            ["migrations/0042_add_signals_table.py"],
            bug_fix_task,
        )

        runner.run_migration_guard.assert_not_called()

    async def test_bug_fix_auto_reject_has_critical_severity(
        self,
        async_session: AsyncSession,
        artifact_store: ArtifactStore,
        bug_fix_task: TaskRequest,
    ):
        runner = _make_agent_runner()
        engine = _make_engine(async_session, artifact_store, runner)
        run_id = await _setup_run_in_verification_passed_state(
            async_session, engine, bug_fix_task,
        )
        await engine._transition(
            run_id, RunState.VERIFICATION_PASSED, RunState.REVIEWING, "test",
        )

        verdict = await engine._check_migration_guard(
            run_id, MIGRATION_DIFF,
            ["migrations/0042_add_signals_table.py"],
            bug_fix_task,
        )

        assert verdict is not None
        assert len(verdict.issues) == 1
        assert verdict.issues[0].severity == ReviewSeverity.CRITICAL

    async def test_bug_fix_auto_reject_confidence_is_1(
        self,
        async_session: AsyncSession,
        artifact_store: ArtifactStore,
        bug_fix_task: TaskRequest,
    ):
        runner = _make_agent_runner()
        engine = _make_engine(async_session, artifact_store, runner)
        run_id = await _setup_run_in_verification_passed_state(
            async_session, engine, bug_fix_task,
        )
        await engine._transition(
            run_id, RunState.VERIFICATION_PASSED, RunState.REVIEWING, "test",
        )

        verdict = await engine._check_migration_guard(
            run_id, MIGRATION_DIFF,
            ["migrations/0042_add_signals_table.py"],
            bug_fix_task,
        )

        assert verdict is not None
        assert verdict.confidence == 1.0

    async def test_bug_fix_auto_reject_message_mentions_bug_fix(
        self,
        async_session: AsyncSession,
        artifact_store: ArtifactStore,
        bug_fix_task: TaskRequest,
    ):
        runner = _make_agent_runner()
        engine = _make_engine(async_session, artifact_store, runner)
        run_id = await _setup_run_in_verification_passed_state(
            async_session, engine, bug_fix_task,
        )
        await engine._transition(
            run_id, RunState.VERIFICATION_PASSED, RunState.REVIEWING, "test",
        )

        verdict = await engine._check_migration_guard(
            run_id, DOCKERFILE_DIFF,
            ["Dockerfile"],
            bug_fix_task,
        )

        assert verdict is not None
        assert "Bug fix tasks must not modify protected paths" in verdict.summary


# ---------------------------------------------------------------------------
# Test allowed task types escalate to LLM
# ---------------------------------------------------------------------------


class TestAllowedTaskTypeEscalation:
    """Allowed task types escalate to the migration guard LLM subagent."""

    async def test_migration_plan_calls_llm(
        self,
        async_session: AsyncSession,
        artifact_store: ArtifactStore,
        migration_task: TaskRequest,
    ):
        guard_verdict = _make_approve_verdict()
        runner = _make_agent_runner(guard_verdict=guard_verdict)
        engine = _make_engine(async_session, artifact_store, runner)
        run_id = await _setup_run_in_verification_passed_state(
            async_session, engine, migration_task,
        )
        await engine._transition(
            run_id, RunState.VERIFICATION_PASSED, RunState.REVIEWING, "test",
        )

        result = await engine._check_migration_guard(
            run_id, MIGRATION_DIFF,
            ["migrations/0042_add_signals_table.py"],
            migration_task,
        )

        runner.run_migration_guard.assert_called_once()
        assert result is not None
        assert result.verdict == ReviewVerdictType.APPROVE

    async def test_endpoint_build_calls_llm(
        self,
        async_session: AsyncSession,
        artifact_store: ArtifactStore,
        endpoint_task: TaskRequest,
    ):
        runner = _make_agent_runner(guard_verdict=_make_approve_verdict())
        engine = _make_engine(async_session, artifact_store, runner)
        run_id = await _setup_run_in_verification_passed_state(
            async_session, engine, endpoint_task,
        )
        await engine._transition(
            run_id, RunState.VERIFICATION_PASSED, RunState.REVIEWING, "test",
        )

        await engine._check_migration_guard(
            run_id, AUTH_DIFF,
            ["auth/middleware.go"],
            endpoint_task,
        )

        runner.run_migration_guard.assert_called_once()

    async def test_refactor_calls_llm(
        self,
        async_session: AsyncSession,
        artifact_store: ArtifactStore,
        refactor_task: TaskRequest,
    ):
        runner = _make_agent_runner(guard_verdict=_make_approve_verdict())
        engine = _make_engine(async_session, artifact_store, runner)
        run_id = await _setup_run_in_verification_passed_state(
            async_session, engine, refactor_task,
        )
        await engine._transition(
            run_id, RunState.VERIFICATION_PASSED, RunState.REVIEWING, "test",
        )

        await engine._check_migration_guard(
            run_id, AUTH_DIFF,
            ["auth/middleware.go"],
            refactor_task,
        )

        runner.run_migration_guard.assert_called_once()

    async def test_canon_update_calls_llm(
        self,
        async_session: AsyncSession,
        artifact_store: ArtifactStore,
    ):
        task = TaskRequest(
            task_type=TaskType.CANON_UPDATE,
            repo="unicorn-app",
            base_branch="main",
            title="Update event schema",
            prompt="Add new event fields",
            target_paths=["canon/schemas/"],
            mcp_profile=MCPProfile.NONE,
        )
        runner = _make_agent_runner(guard_verdict=_make_approve_verdict())
        engine = _make_engine(async_session, artifact_store, runner)
        run_id = await _setup_run_in_verification_passed_state(
            async_session, engine, task,
        )
        await engine._transition(
            run_id, RunState.VERIFICATION_PASSED, RunState.REVIEWING, "test",
        )

        await engine._check_migration_guard(
            run_id, MIGRATION_DIFF,
            ["migrations/0042_add_signals_table.py"],
            task,
        )

        runner.run_migration_guard.assert_called_once()

    async def test_passes_diff_and_protected_files_to_llm(
        self,
        async_session: AsyncSession,
        artifact_store: ArtifactStore,
        migration_task: TaskRequest,
    ):
        runner = _make_agent_runner(guard_verdict=_make_approve_verdict())
        engine = _make_engine(async_session, artifact_store, runner)
        run_id = await _setup_run_in_verification_passed_state(
            async_session, engine, migration_task,
        )
        await engine._transition(
            run_id, RunState.VERIFICATION_PASSED, RunState.REVIEWING, "test",
        )

        protected = ["migrations/0042_add_signals_table.py"]
        await engine._check_migration_guard(
            run_id, MIGRATION_DIFF, protected, migration_task,
        )

        call_kwargs = runner.run_migration_guard.call_args.kwargs
        assert call_kwargs["diff"] == MIGRATION_DIFF
        assert call_kwargs["changed_files"] == protected

    async def test_returns_llm_reject_verdict(
        self,
        async_session: AsyncSession,
        artifact_store: ArtifactStore,
        migration_task: TaskRequest,
    ):
        runner = _make_agent_runner(guard_verdict=_make_reject_verdict())
        engine = _make_engine(async_session, artifact_store, runner)
        run_id = await _setup_run_in_verification_passed_state(
            async_session, engine, migration_task,
        )
        await engine._transition(
            run_id, RunState.VERIFICATION_PASSED, RunState.REVIEWING, "test",
        )

        result = await engine._check_migration_guard(
            run_id, MIGRATION_DIFF,
            ["migrations/0042_add_signals_table.py"],
            migration_task,
        )

        assert result is not None
        assert result.verdict == ReviewVerdictType.REJECT

    async def test_returns_llm_request_changes_verdict(
        self,
        async_session: AsyncSession,
        artifact_store: ArtifactStore,
        migration_task: TaskRequest,
    ):
        runner = _make_agent_runner(guard_verdict=_make_request_changes_verdict())
        engine = _make_engine(async_session, artifact_store, runner)
        run_id = await _setup_run_in_verification_passed_state(
            async_session, engine, migration_task,
        )
        await engine._transition(
            run_id, RunState.VERIFICATION_PASSED, RunState.REVIEWING, "test",
        )

        result = await engine._check_migration_guard(
            run_id, MIGRATION_DIFF,
            ["migrations/0042_add_signals_table.py"],
            migration_task,
        )

        assert result is not None
        assert result.verdict == ReviewVerdictType.REQUEST_CHANGES


# ---------------------------------------------------------------------------
# Test unauthorized task types
# ---------------------------------------------------------------------------


class TestUnauthorizedTaskTypeReject:
    """Task types not in the allowed list auto-reject for protected paths."""

    async def test_extraction_batch_auto_rejects(
        self,
        async_session: AsyncSession,
        artifact_store: ArtifactStore,
        extraction_task: TaskRequest,
    ):
        runner = _make_agent_runner()
        engine = _make_engine(async_session, artifact_store, runner)
        run_id = await _setup_run_in_verification_passed_state(
            async_session, engine, extraction_task,
        )
        await engine._transition(
            run_id, RunState.VERIFICATION_PASSED, RunState.REVIEWING, "test",
        )

        verdict = await engine._check_migration_guard(
            run_id, MIGRATION_DIFF,
            ["migrations/0042_add_signals_table.py"],
            extraction_task,
        )

        assert verdict is not None
        assert verdict.verdict == ReviewVerdictType.REJECT
        assert "not authorized" in verdict.summary
        runner.run_migration_guard.assert_not_called()

    async def test_unauthorized_reject_mentions_task_type(
        self,
        async_session: AsyncSession,
        artifact_store: ArtifactStore,
        extraction_task: TaskRequest,
    ):
        runner = _make_agent_runner()
        engine = _make_engine(async_session, artifact_store, runner)
        run_id = await _setup_run_in_verification_passed_state(
            async_session, engine, extraction_task,
        )
        await engine._transition(
            run_id, RunState.VERIFICATION_PASSED, RunState.REVIEWING, "test",
        )

        verdict = await engine._check_migration_guard(
            run_id, MIGRATION_DIFF,
            ["migrations/0042_add_signals_table.py"],
            extraction_task,
        )

        assert verdict is not None
        assert "extraction_batch" in verdict.summary


# ---------------------------------------------------------------------------
# Test no protected paths
# ---------------------------------------------------------------------------


class TestNoProtectedPaths:
    """No protected paths touched → returns None (no guard needed)."""

    async def test_safe_diff_returns_none(
        self,
        async_session: AsyncSession,
        artifact_store: ArtifactStore,
        bug_fix_task: TaskRequest,
    ):
        runner = _make_agent_runner()
        engine = _make_engine(async_session, artifact_store, runner)
        run_id = await _setup_run_in_verification_passed_state(
            async_session, engine, bug_fix_task,
        )
        await engine._transition(
            run_id, RunState.VERIFICATION_PASSED, RunState.REVIEWING, "test",
        )

        verdict = await engine._check_migration_guard(
            run_id, SAFE_DIFF,
            ["services/api/search/handler.go"],
            bug_fix_task,
        )

        assert verdict is None
        runner.run_migration_guard.assert_not_called()

    async def test_empty_changed_files_returns_none(
        self,
        async_session: AsyncSession,
        artifact_store: ArtifactStore,
        bug_fix_task: TaskRequest,
    ):
        runner = _make_agent_runner()
        engine = _make_engine(async_session, artifact_store, runner)
        run_id = await _setup_run_in_verification_passed_state(
            async_session, engine, bug_fix_task,
        )
        await engine._transition(
            run_id, RunState.VERIFICATION_PASSED, RunState.REVIEWING, "test",
        )

        verdict = await engine._check_migration_guard(
            run_id, SAFE_DIFF, [], bug_fix_task,
        )

        assert verdict is None


# ---------------------------------------------------------------------------
# Test migration guard event logging
# ---------------------------------------------------------------------------


class TestMigrationGuardEvents:
    """Migration guard adds run events when triggered."""

    async def test_trigger_event_emitted(
        self,
        async_session: AsyncSession,
        artifact_store: ArtifactStore,
        bug_fix_task: TaskRequest,
    ):
        runner = _make_agent_runner()
        engine = _make_engine(async_session, artifact_store, runner)
        run_id = await _setup_run_in_verification_passed_state(
            async_session, engine, bug_fix_task,
        )
        await engine._transition(
            run_id, RunState.VERIFICATION_PASSED, RunState.REVIEWING, "test",
        )

        await engine._check_migration_guard(
            run_id, MIGRATION_DIFF,
            ["migrations/0042_add_signals_table.py"],
            bug_fix_task,
        )

        events = await get_run_events(async_session, run_id)
        guard_events = [
            e for e in events if "Migration guard triggered" in e.message
        ]
        assert len(guard_events) == 1
        assert "migrations/0042_add_signals_table.py" in guard_events[0].message

    async def test_no_trigger_event_for_safe_files(
        self,
        async_session: AsyncSession,
        artifact_store: ArtifactStore,
        bug_fix_task: TaskRequest,
    ):
        runner = _make_agent_runner()
        engine = _make_engine(async_session, artifact_store, runner)
        run_id = await _setup_run_in_verification_passed_state(
            async_session, engine, bug_fix_task,
        )
        await engine._transition(
            run_id, RunState.VERIFICATION_PASSED, RunState.REVIEWING, "test",
        )

        await engine._check_migration_guard(
            run_id, SAFE_DIFF,
            ["services/api/search/handler.go"],
            bug_fix_task,
        )

        events = await get_run_events(async_session, run_id)
        guard_events = [
            e for e in events if "Migration guard triggered" in e.message
        ]
        assert len(guard_events) == 0


# ---------------------------------------------------------------------------
# Test integration with _run_review()
# ---------------------------------------------------------------------------


class TestRunReviewIntegration:
    """Migration guard integrates with the full _run_review lifecycle."""

    async def test_guard_reject_skips_standard_review(
        self,
        async_session: AsyncSession,
        artifact_store: ArtifactStore,
        bug_fix_task: TaskRequest,
    ):
        """When migration guard rejects, standard blind review is NOT called."""
        runner = _make_agent_runner()
        engine = _make_engine(async_session, artifact_store, runner)
        run_id = await _setup_run_in_verification_passed_state(
            async_session, engine, bug_fix_task,
        )

        review = await engine._run_review(run_id, MIGRATION_DIFF, bug_fix_task)

        assert review.verdict == ReviewVerdictType.REJECT
        # Standard reviewer should NOT have been called
        runner.run_reviewer.assert_not_called()

    async def test_guard_reject_transitions_to_review_failed(
        self,
        async_session: AsyncSession,
        artifact_store: ArtifactStore,
        bug_fix_task: TaskRequest,
    ):
        runner = _make_agent_runner()
        engine = _make_engine(async_session, artifact_store, runner)
        run_id = await _setup_run_in_verification_passed_state(
            async_session, engine, bug_fix_task,
        )

        await engine._run_review(run_id, MIGRATION_DIFF, bug_fix_task)

        run = await get_run(async_session, run_id)
        assert run is not None
        assert run.state == RunState.REVIEW_FAILED.value

    async def test_guard_reject_sets_error_message(
        self,
        async_session: AsyncSession,
        artifact_store: ArtifactStore,
        bug_fix_task: TaskRequest,
    ):
        runner = _make_agent_runner()
        engine = _make_engine(async_session, artifact_store, runner)
        run_id = await _setup_run_in_verification_passed_state(
            async_session, engine, bug_fix_task,
        )

        await engine._run_review(run_id, MIGRATION_DIFF, bug_fix_task)

        run = await get_run(async_session, run_id)
        assert run is not None
        assert run.error_message is not None
        assert "Migration guard rejected" in run.error_message

    async def test_guard_reject_stores_migration_guard_artifact(
        self,
        async_session: AsyncSession,
        artifact_store: ArtifactStore,
        bug_fix_task: TaskRequest,
    ):
        runner = _make_agent_runner()
        engine = _make_engine(async_session, artifact_store, runner)
        run_id = await _setup_run_in_verification_passed_state(
            async_session, engine, bug_fix_task,
        )

        await engine._run_review(run_id, MIGRATION_DIFF, bug_fix_task)

        artifacts = await artifact_store.list_artifacts(run_id)
        guard_artifacts = [
            a for a in artifacts if "migration_guard_review" in a["filename"]
        ]
        assert len(guard_artifacts) == 1

    async def test_guard_reject_does_not_store_review_json(
        self,
        async_session: AsyncSession,
        artifact_store: ArtifactStore,
        bug_fix_task: TaskRequest,
    ):
        """When guard rejects, no standard review.json should be stored."""
        runner = _make_agent_runner()
        engine = _make_engine(async_session, artifact_store, runner)
        run_id = await _setup_run_in_verification_passed_state(
            async_session, engine, bug_fix_task,
        )

        await engine._run_review(run_id, MIGRATION_DIFF, bug_fix_task)

        artifacts = await artifact_store.list_artifacts(run_id)
        standard_review = [
            a for a in artifacts
            if a["filename"] == "review.json"
        ]
        assert len(standard_review) == 0

    async def test_guard_approve_proceeds_to_standard_review(
        self,
        async_session: AsyncSession,
        artifact_store: ArtifactStore,
        migration_task: TaskRequest,
    ):
        """When migration guard approves, standard blind review still runs."""
        guard_verdict = _make_approve_verdict()
        standard_verdict = _make_standard_approve_verdict()
        runner = _make_agent_runner(
            guard_verdict=guard_verdict,
            review_verdict=standard_verdict,
        )
        engine = _make_engine(async_session, artifact_store, runner)
        run_id = await _setup_run_in_verification_passed_state(
            async_session, engine, migration_task,
        )

        review = await engine._run_review(run_id, MIGRATION_DIFF, migration_task)

        # Both guard and standard reviewer should have been called
        runner.run_migration_guard.assert_called_once()
        runner.run_reviewer.assert_called_once()
        # Final verdict is from the standard review
        assert review.verdict == ReviewVerdictType.APPROVE

    async def test_guard_approve_stores_both_artifacts(
        self,
        async_session: AsyncSession,
        artifact_store: ArtifactStore,
        migration_task: TaskRequest,
    ):
        """Both migration_guard_review.json and review.json are stored."""
        runner = _make_agent_runner(
            guard_verdict=_make_approve_verdict(),
            review_verdict=_make_standard_approve_verdict(),
        )
        engine = _make_engine(async_session, artifact_store, runner)
        run_id = await _setup_run_in_verification_passed_state(
            async_session, engine, migration_task,
        )

        await engine._run_review(run_id, MIGRATION_DIFF, migration_task)

        artifacts = await artifact_store.list_artifacts(run_id)
        filenames = [a["filename"] for a in artifacts]
        assert "migration_guard_review.json" in filenames
        assert "review.json" in filenames

    async def test_guard_request_changes_proceeds_to_standard_review(
        self,
        async_session: AsyncSession,
        artifact_store: ArtifactStore,
        migration_task: TaskRequest,
    ):
        """REQUEST_CHANGES from guard still proceeds to standard review."""
        runner = _make_agent_runner(
            guard_verdict=_make_request_changes_verdict(),
            review_verdict=_make_standard_approve_verdict(),
        )
        engine = _make_engine(async_session, artifact_store, runner)
        run_id = await _setup_run_in_verification_passed_state(
            async_session, engine, migration_task,
        )

        review = await engine._run_review(run_id, MIGRATION_DIFF, migration_task)

        runner.run_migration_guard.assert_called_once()
        runner.run_reviewer.assert_called_once()
        assert review.verdict == ReviewVerdictType.APPROVE

    async def test_no_guard_needed_proceeds_directly_to_standard_review(
        self,
        async_session: AsyncSession,
        artifact_store: ArtifactStore,
        bug_fix_task: TaskRequest,
    ):
        """Safe diff skips migration guard entirely, goes straight to blind review."""
        runner = _make_agent_runner(
            review_verdict=_make_standard_approve_verdict(),
        )
        engine = _make_engine(async_session, artifact_store, runner)
        run_id = await _setup_run_in_verification_passed_state(
            async_session, engine, bug_fix_task,
        )

        review = await engine._run_review(run_id, SAFE_DIFF, bug_fix_task)

        # Migration guard NOT called, standard review IS called
        runner.run_migration_guard.assert_not_called()
        runner.run_reviewer.assert_called_once()
        assert review.verdict == ReviewVerdictType.APPROVE

    async def test_no_guard_does_not_store_migration_guard_artifact(
        self,
        async_session: AsyncSession,
        artifact_store: ArtifactStore,
        bug_fix_task: TaskRequest,
    ):
        runner = _make_agent_runner(
            review_verdict=_make_standard_approve_verdict(),
        )
        engine = _make_engine(async_session, artifact_store, runner)
        run_id = await _setup_run_in_verification_passed_state(
            async_session, engine, bug_fix_task,
        )

        await engine._run_review(run_id, SAFE_DIFF, bug_fix_task)

        artifacts = await artifact_store.list_artifacts(run_id)
        guard_artifacts = [
            a for a in artifacts if "migration_guard_review" in a["filename"]
        ]
        assert len(guard_artifacts) == 0

    async def test_guard_approve_emits_continuation_event(
        self,
        async_session: AsyncSession,
        artifact_store: ArtifactStore,
        migration_task: TaskRequest,
    ):
        """Guard APPROVE adds an event before proceeding to standard review."""
        runner = _make_agent_runner(
            guard_verdict=_make_approve_verdict(),
            review_verdict=_make_standard_approve_verdict(),
        )
        engine = _make_engine(async_session, artifact_store, runner)
        run_id = await _setup_run_in_verification_passed_state(
            async_session, engine, migration_task,
        )

        await engine._run_review(run_id, MIGRATION_DIFF, migration_task)

        events = await get_run_events(async_session, run_id)
        continuation_events = [
            e for e in events
            if "Migration guard verdict: approve" in e.message
        ]
        assert len(continuation_events) == 1
        assert "proceeding to standard review" in continuation_events[0].message

    async def test_llm_guard_reject_for_allowed_type_transitions_to_review_failed(
        self,
        async_session: AsyncSession,
        artifact_store: ArtifactStore,
        migration_task: TaskRequest,
    ):
        """LLM migration guard rejects → REVIEW_FAILED, standard review skipped."""
        runner = _make_agent_runner(guard_verdict=_make_reject_verdict())
        engine = _make_engine(async_session, artifact_store, runner)
        run_id = await _setup_run_in_verification_passed_state(
            async_session, engine, migration_task,
        )

        review = await engine._run_review(run_id, MIGRATION_DIFF, migration_task)

        assert review.verdict == ReviewVerdictType.REJECT
        runner.run_reviewer.assert_not_called()

        run = await get_run(async_session, run_id)
        assert run is not None
        assert run.state == RunState.REVIEW_FAILED.value
        assert "Migration guard rejected" in run.error_message


# ---------------------------------------------------------------------------
# Test MIGRATION_GUARD_ALLOWED_TASK_TYPES constant
# ---------------------------------------------------------------------------


class TestAllowedTaskTypesConstant:
    """Verify the allowed task types set is correctly populated."""

    def test_endpoint_build_is_allowed(self):
        assert TaskType.ENDPOINT_BUILD in MIGRATION_GUARD_ALLOWED_TASK_TYPES

    def test_refactor_is_allowed(self):
        assert TaskType.REFACTOR in MIGRATION_GUARD_ALLOWED_TASK_TYPES

    def test_migration_plan_is_allowed(self):
        assert TaskType.MIGRATION_PLAN in MIGRATION_GUARD_ALLOWED_TASK_TYPES

    def test_canon_update_is_allowed(self):
        assert TaskType.CANON_UPDATE in MIGRATION_GUARD_ALLOWED_TASK_TYPES

    def test_bug_fix_is_not_allowed(self):
        assert TaskType.BUG_FIX not in MIGRATION_GUARD_ALLOWED_TASK_TYPES

    def test_extraction_batch_is_not_allowed(self):
        assert TaskType.EXTRACTION_BATCH not in MIGRATION_GUARD_ALLOWED_TASK_TYPES
