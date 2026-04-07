"""Tests for blind review: run_reviewer, _run_review, and _check_migration_guard.

Tests verify:
- AgentRunner.run_reviewer() uses model_router, structured output with
  ReviewVerdict schema, REVIEWER_SYSTEM prompt, and does NOT receive the plan.
- RunEngine._run_review() manages state transitions (VERIFICATION_PASSED ->
  REVIEWING -> PR_OPENED or REVIEW_FAILED), migration guard integration,
  artifact storage, and verdict handling.
- RunEngine._check_migration_guard() detects protected paths, rejects bug_fix
  tasks immediately, and delegates to the migration guard agent otherwise.
"""

import json
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock
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
from foundry.orchestration.agent_runner import AgentRunner, REVIEWER_TOOLS
from foundry.orchestration.run_engine import RunEngine
from foundry.storage.artifact_store import ArtifactStore, ArtifactType


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
        metadata={"run_id": str(uuid4())},
    )


@pytest.fixture
def endpoint_task_request() -> TaskRequest:
    return TaskRequest(
        task_type=TaskType.ENDPOINT_BUILD,
        repo="unicorn-app",
        base_branch="main",
        title="Add company timeline endpoint",
        prompt="Add GET /v1/companies/{id}/timeline endpoint",
        target_paths=["services/api/company/handler.go"],
        mcp_profile=MCPProfile.NONE,
        metadata={},
    )


@pytest.fixture
def migration_task_request() -> TaskRequest:
    return TaskRequest(
        task_type=TaskType.MIGRATION_PLAN,
        repo="unicorn-app",
        base_branch="main",
        title="Add signals table",
        prompt="Create a new company_signals table",
        target_paths=["migrations/"],
        mcp_profile=MCPProfile.NONE,
        metadata={},
    )


@pytest.fixture
def approve_verdict() -> ReviewVerdict:
    return ReviewVerdict(
        verdict=ReviewVerdictType.APPROVE,
        issues=[],
        summary="Code looks good. No issues found.",
    )


@pytest.fixture
def reject_verdict() -> ReviewVerdict:
    return ReviewVerdict(
        verdict=ReviewVerdictType.REJECT,
        issues=[
            ReviewIssue(
                severity=ReviewSeverity.CRITICAL,
                file_path="services/api/search/handler.go",
                description="SQL injection vulnerability in query construction",
            ),
        ],
        summary="Critical security issue found.",
    )


@pytest.fixture
def request_changes_verdict() -> ReviewVerdict:
    return ReviewVerdict(
        verdict=ReviewVerdictType.REQUEST_CHANGES,
        issues=[
            ReviewIssue(
                severity=ReviewSeverity.MAJOR,
                file_path="services/api/search/handler.go",
                line_range="42-45",
                description="Missing error handling for database query",
                suggestion="Add error check after db.Query()",
            ),
        ],
        summary="Major issues that should be addressed before merge.",
    )


@pytest.fixture
def runner() -> AgentRunner:
    return AgentRunner(api_key="test-key")


@pytest.fixture
def artifact_store(tmp_path: Path) -> ArtifactStore:
    return ArtifactStore(base_path=str(tmp_path / "artifacts"))


@pytest.fixture
def run_engine(async_session: AsyncSession, artifact_store: ArtifactStore) -> RunEngine:
    """RunEngine with mock dependencies except session and artifact_store."""
    return RunEngine(
        session=async_session,
        artifact_store=artifact_store,
        worktree_manager=MagicMock(),
        agent_runner=MagicMock(),
        pr_creator=MagicMock(),
        verification_runner=MagicMock(),
    )


SAMPLE_DIFF = """\
diff --git a/services/api/search/handler.go b/services/api/search/handler.go
index abc1234..def5678 100644
--- a/services/api/search/handler.go
+++ b/services/api/search/handler.go
@@ -42,7 +42,7 @@ func (h *SearchHandler) Search(w http.ResponseWriter, r *http.Request) {
-    offset := (page - 1) * pageSize + 1
+    offset := (page - 1) * pageSize
"""

MIGRATION_DIFF = """\
diff --git a/migrations/0001_add_signals.py b/migrations/0001_add_signals.py
--- /dev/null
+++ b/migrations/0001_add_signals.py
@@ -0,0 +1,20 @@
+def upgrade():
+    pass
+def downgrade():
+    pass
"""

AUTH_DIFF = """\
diff --git a/auth/middleware.go b/auth/middleware.go
--- a/auth/middleware.go
+++ b/auth/middleware.go
@@ -10,7 +10,7 @@
-    token := r.Header.Get("Authorization")
+    token := r.Header.Get("X-Auth-Token")
"""

INFRA_DIFF = """\
diff --git a/infra/terraform/main.tf b/infra/terraform/main.tf
--- a/infra/terraform/main.tf
+++ b/infra/terraform/main.tf
@@ -1,5 +1,5 @@
-    instance_type = "t3.medium"
+    instance_type = "t3.large"
"""

DOCKER_DIFF = """\
diff --git a/Dockerfile b/Dockerfile
--- a/Dockerfile
+++ b/Dockerfile
@@ -1,3 +1,3 @@
-FROM golang:1.21
+FROM golang:1.22
"""


# ---------------------------------------------------------------------------
# AgentRunner.run_reviewer tests
# ---------------------------------------------------------------------------


class TestRunReviewer:
    """Tests for AgentRunner.run_reviewer() — blind review."""

    async def test_uses_reviewer_system_prompt(
        self, runner: AgentRunner, approve_verdict: ReviewVerdict,
    ):
        """run_reviewer uses REVIEWER_SYSTEM prompt template."""
        from foundry.orchestration.prompt_templates import REVIEWER_SYSTEM

        runner.provider = MagicMock()
        runner.provider.run_with_structured_output = AsyncMock(return_value={
            "response": approve_verdict,
            "model": "claude-opus-4-6",
            "tokens_in": 500,
            "tokens_out": 200,
            "duration_ms": 3000,
        })

        await runner.run_reviewer(
            diff=SAMPLE_DIFF, pr_title="Test PR", pr_description="Test desc",
        )

        call_kwargs = runner.provider.run_with_structured_output.call_args.kwargs
        assert call_kwargs["system_prompt"] == REVIEWER_SYSTEM

    async def test_builds_user_message_with_diff_title_description(
        self, runner: AgentRunner, approve_verdict: ReviewVerdict,
    ):
        """run_reviewer builds user message containing diff, PR title, and description."""
        runner.provider = MagicMock()
        runner.provider.run_with_structured_output = AsyncMock(return_value={
            "response": approve_verdict,
            "model": "claude-opus-4-6",
            "tokens_in": 500,
            "tokens_out": 200,
            "duration_ms": 3000,
        })

        await runner.run_reviewer(
            diff=SAMPLE_DIFF,
            pr_title="[Foundry] bug_fix: Fix pagination",
            pr_description="Fix off-by-one in search",
        )

        call_kwargs = runner.provider.run_with_structured_output.call_args.kwargs
        user_msg = call_kwargs["user_message"]
        assert "Fix pagination" in user_msg
        assert "Fix off-by-one" in user_msg
        assert "handler.go" in user_msg

    async def test_does_not_include_plan_in_message(
        self, runner: AgentRunner, approve_verdict: ReviewVerdict,
    ):
        """CRITICAL: run_reviewer must not pass the plan — blind review."""
        runner.provider = MagicMock()
        runner.provider.run_with_structured_output = AsyncMock(return_value={
            "response": approve_verdict,
            "model": "claude-opus-4-6",
            "tokens_in": 500,
            "tokens_out": 200,
            "duration_ms": 3000,
        })

        await runner.run_reviewer(
            diff=SAMPLE_DIFF,
            pr_title="Test PR",
            pr_description="Test desc",
        )

        call_kwargs = runner.provider.run_with_structured_output.call_args.kwargs
        user_msg = call_kwargs["user_message"]
        assert "plan" not in user_msg.lower() or "do not have access to the original plan" in user_msg.lower()

    async def test_uses_model_router_for_model_selection(
        self, runner: AgentRunner, approve_verdict: ReviewVerdict,
    ):
        """run_reviewer resolves model via model_router (reviewer role -> opus)."""
        runner.provider = MagicMock()
        runner.provider.run_with_structured_output = AsyncMock(return_value={
            "response": approve_verdict,
            "model": "claude-opus-4-6",
            "tokens_in": 500,
            "tokens_out": 200,
            "duration_ms": 3000,
        })

        await runner.run_reviewer(
            diff=SAMPLE_DIFF,
            pr_title="Test PR",
            pr_description="Test desc",
            task_type=TaskType.BUG_FIX,
        )

        call_kwargs = runner.provider.run_with_structured_output.call_args.kwargs
        # bug_fix + reviewer resolves to claude-opus-4-6 per model_router
        assert call_kwargs["model"] == "claude-opus-4-6"

    async def test_uses_structured_output_with_review_verdict_schema(
        self, runner: AgentRunner, approve_verdict: ReviewVerdict,
    ):
        """run_reviewer calls run_with_structured_output with ReviewVerdict schema."""
        runner.provider = MagicMock()
        runner.provider.run_with_structured_output = AsyncMock(return_value={
            "response": approve_verdict,
            "model": "claude-opus-4-6",
            "tokens_in": 500,
            "tokens_out": 200,
            "duration_ms": 3000,
        })

        await runner.run_reviewer(
            diff=SAMPLE_DIFF, pr_title="Test PR", pr_description="Test desc",
        )

        runner.provider.run_with_structured_output.assert_called_once()
        call_kwargs = runner.provider.run_with_structured_output.call_args.kwargs
        assert call_kwargs["output_schema"] is ReviewVerdict

    async def test_passes_empty_reviewer_tools(
        self, runner: AgentRunner, approve_verdict: ReviewVerdict,
    ):
        """run_reviewer passes no tools — reviewer is judge-only."""
        runner.provider = MagicMock()
        runner.provider.run_with_structured_output = AsyncMock(return_value={
            "response": approve_verdict,
            "model": "claude-opus-4-6",
            "tokens_in": 500,
            "tokens_out": 200,
            "duration_ms": 3000,
        })

        await runner.run_reviewer(
            diff=SAMPLE_DIFF, pr_title="Test PR", pr_description="Test desc",
        )

        call_kwargs = runner.provider.run_with_structured_output.call_args.kwargs
        # REVIEWER_TOOLS is [] → passed as None
        assert call_kwargs["tools"] is None

    async def test_returns_review_verdict(
        self, runner: AgentRunner, approve_verdict: ReviewVerdict,
    ):
        """run_reviewer returns a validated ReviewVerdict."""
        runner.provider = MagicMock()
        runner.provider.run_with_structured_output = AsyncMock(return_value={
            "response": approve_verdict,
            "model": "claude-opus-4-6",
            "tokens_in": 500,
            "tokens_out": 200,
            "duration_ms": 3000,
        })

        result = await runner.run_reviewer(
            diff=SAMPLE_DIFF, pr_title="Test PR", pr_description="Test desc",
        )

        assert isinstance(result, ReviewVerdict)
        assert result.verdict == ReviewVerdictType.APPROVE

    async def test_handles_dict_response(self, runner: AgentRunner):
        """run_reviewer validates dict responses into ReviewVerdict."""
        runner.provider = MagicMock()
        runner.provider.run_with_structured_output = AsyncMock(return_value={
            "response": {
                "verdict": ReviewVerdictType.REJECT,
                "issues": [{
                    "severity": ReviewSeverity.CRITICAL,
                    "file_path": "handler.go",
                    "description": "SQL injection",
                }],
                "summary": "Critical issue",
            },
            "model": "claude-opus-4-6",
            "tokens_in": 500,
            "tokens_out": 200,
            "duration_ms": 3000,
        })

        result = await runner.run_reviewer(
            diff=SAMPLE_DIFF, pr_title="Test PR", pr_description="Test desc",
        )

        assert isinstance(result, ReviewVerdict)
        assert result.verdict == ReviewVerdictType.REJECT

    async def test_propagates_provider_errors(self, runner: AgentRunner):
        """run_reviewer propagates exceptions from the provider."""
        runner.provider = MagicMock()
        runner.provider.run_with_structured_output = AsyncMock(
            side_effect=ValueError("Model unavailable")
        )

        with pytest.raises(ValueError, match="Model unavailable"):
            await runner.run_reviewer(
                diff=SAMPLE_DIFF, pr_title="Test PR", pr_description="Test desc",
            )

    async def test_default_task_type_is_review_diff(
        self, runner: AgentRunner, approve_verdict: ReviewVerdict,
    ):
        """run_reviewer defaults to REVIEW_DIFF task type for model routing."""
        runner.provider = MagicMock()
        runner.provider.run_with_structured_output = AsyncMock(return_value={
            "response": approve_verdict,
            "model": "claude-opus-4-6",
            "tokens_in": 500,
            "tokens_out": 200,
            "duration_ms": 3000,
        })

        # Call without task_type — should use default
        await runner.run_reviewer(
            diff=SAMPLE_DIFF, pr_title="Test PR", pr_description="Test desc",
        )

        call_kwargs = runner.provider.run_with_structured_output.call_args.kwargs
        # review_diff + reviewer resolves to claude-opus-4-6
        assert call_kwargs["model"] == "claude-opus-4-6"


# ---------------------------------------------------------------------------
# RunEngine._check_migration_guard tests
# ---------------------------------------------------------------------------


class TestCheckMigrationGuard:
    """Tests for RunEngine._check_migration_guard() protected path detection."""

    async def _setup_run_in_reviewing_state(
        self,
        session: AsyncSession,
        run_engine: RunEngine,
        task_request: TaskRequest,
    ) -> UUID:
        """Create a run and advance it to REVIEWING state."""
        run = await create_run(session, task_request)
        run_id = run.id
        await run_engine._transition(run_id, RunState.QUEUED, RunState.CREATING_WORKTREE, "Creating worktree")
        await run_engine._transition(run_id, RunState.CREATING_WORKTREE, RunState.PLANNING, "Planning")
        await run_engine._transition(run_id, RunState.PLANNING, RunState.IMPLEMENTING, "Implementing")
        await run_engine._transition(run_id, RunState.IMPLEMENTING, RunState.VERIFYING, "Verifying")
        await run_engine._transition(run_id, RunState.VERIFYING, RunState.VERIFICATION_PASSED, "Passed")
        await run_engine._transition(run_id, RunState.VERIFICATION_PASSED, RunState.REVIEWING, "Reviewing")
        return run_id

    async def test_returns_none_for_safe_diff(
        self,
        async_session: AsyncSession,
        run_engine: RunEngine,
        sample_task_request: TaskRequest,
    ):
        """No guard needed when diff doesn't touch protected paths."""
        run_id = await self._setup_run_in_reviewing_state(
            async_session, run_engine, sample_task_request,
        )

        result = await run_engine._check_migration_guard(
            run_id, SAMPLE_DIFF, TaskType.BUG_FIX,
        )

        assert result is None

    async def test_rejects_bug_fix_touching_migrations(
        self,
        async_session: AsyncSession,
        run_engine: RunEngine,
        sample_task_request: TaskRequest,
    ):
        """Bug fix tasks are rejected immediately when touching migrations/."""
        run_id = await self._setup_run_in_reviewing_state(
            async_session, run_engine, sample_task_request,
        )

        result = await run_engine._check_migration_guard(
            run_id, MIGRATION_DIFF, TaskType.BUG_FIX,
        )

        assert result is not None
        assert result.verdict == ReviewVerdictType.REJECT
        assert len(result.issues) == 1
        assert result.issues[0].severity == ReviewSeverity.CRITICAL
        # Should NOT call the migration guard agent
        run_engine.agent_runner.run_migration_guard.assert_not_called()

    async def test_rejects_bug_fix_touching_auth(
        self,
        async_session: AsyncSession,
        run_engine: RunEngine,
        sample_task_request: TaskRequest,
    ):
        """Bug fix tasks are rejected when touching auth/."""
        run_id = await self._setup_run_in_reviewing_state(
            async_session, run_engine, sample_task_request,
        )

        result = await run_engine._check_migration_guard(
            run_id, AUTH_DIFF, TaskType.BUG_FIX,
        )

        assert result is not None
        assert result.verdict == ReviewVerdictType.REJECT

    async def test_rejects_bug_fix_touching_infra(
        self,
        async_session: AsyncSession,
        run_engine: RunEngine,
        sample_task_request: TaskRequest,
    ):
        """Bug fix tasks are rejected when touching infra/."""
        run_id = await self._setup_run_in_reviewing_state(
            async_session, run_engine, sample_task_request,
        )

        result = await run_engine._check_migration_guard(
            run_id, INFRA_DIFF, TaskType.BUG_FIX,
        )

        assert result is not None
        assert result.verdict == ReviewVerdictType.REJECT

    async def test_rejects_bug_fix_touching_dockerfile(
        self,
        async_session: AsyncSession,
        run_engine: RunEngine,
        sample_task_request: TaskRequest,
    ):
        """Bug fix tasks are rejected when touching Dockerfile."""
        run_id = await self._setup_run_in_reviewing_state(
            async_session, run_engine, sample_task_request,
        )

        result = await run_engine._check_migration_guard(
            run_id, DOCKER_DIFF, TaskType.BUG_FIX,
        )

        assert result is not None
        assert result.verdict == ReviewVerdictType.REJECT

    async def test_delegates_to_guard_agent_for_non_bugfix(
        self,
        async_session: AsyncSession,
        run_engine: RunEngine,
        migration_task_request: TaskRequest,
        approve_verdict: ReviewVerdict,
    ):
        """Non-bug_fix tasks touching protected paths invoke the migration guard agent."""
        run_id = await self._setup_run_in_reviewing_state(
            async_session, run_engine, migration_task_request,
        )
        run_engine.agent_runner.run_migration_guard = AsyncMock(
            return_value=approve_verdict,
        )

        result = await run_engine._check_migration_guard(
            run_id, MIGRATION_DIFF, TaskType.MIGRATION_PLAN,
        )

        assert result is not None
        assert result.verdict == ReviewVerdictType.APPROVE
        run_engine.agent_runner.run_migration_guard.assert_called_once_with(
            MIGRATION_DIFF,
        )

    async def test_returns_guard_reject_for_non_bugfix(
        self,
        async_session: AsyncSession,
        run_engine: RunEngine,
        migration_task_request: TaskRequest,
        reject_verdict: ReviewVerdict,
    ):
        """Migration guard can reject non-bug_fix tasks too."""
        run_id = await self._setup_run_in_reviewing_state(
            async_session, run_engine, migration_task_request,
        )
        run_engine.agent_runner.run_migration_guard = AsyncMock(
            return_value=reject_verdict,
        )

        result = await run_engine._check_migration_guard(
            run_id, MIGRATION_DIFF, TaskType.MIGRATION_PLAN,
        )

        assert result is not None
        assert result.verdict == ReviewVerdictType.REJECT


# ---------------------------------------------------------------------------
# RunEngine._run_review tests
# ---------------------------------------------------------------------------


class TestRunReview:
    """Tests for RunEngine._run_review() state transitions and artifact storage."""

    async def _setup_run_in_verification_passed(
        self,
        session: AsyncSession,
        run_engine: RunEngine,
        task_request: TaskRequest,
    ) -> UUID:
        """Create a run and advance it to VERIFICATION_PASSED state."""
        run = await create_run(session, task_request)
        run_id = run.id
        await run_engine._transition(run_id, RunState.QUEUED, RunState.CREATING_WORKTREE, "Creating worktree")
        await run_engine._transition(run_id, RunState.CREATING_WORKTREE, RunState.PLANNING, "Planning")
        await run_engine._transition(run_id, RunState.PLANNING, RunState.IMPLEMENTING, "Implementing")
        await run_engine._transition(run_id, RunState.IMPLEMENTING, RunState.VERIFYING, "Verifying")
        await run_engine._transition(run_id, RunState.VERIFYING, RunState.VERIFICATION_PASSED, "Passed")
        return run_id

    async def test_transitions_to_reviewing(
        self,
        async_session: AsyncSession,
        run_engine: RunEngine,
        sample_task_request: TaskRequest,
        approve_verdict: ReviewVerdict,
    ):
        """_run_review transitions VERIFICATION_PASSED -> REVIEWING."""
        run_id = await self._setup_run_in_verification_passed(
            async_session, run_engine, sample_task_request,
        )
        run_engine.agent_runner.run_reviewer = AsyncMock(return_value=approve_verdict)

        await run_engine._run_review(run_id, SAMPLE_DIFF, sample_task_request)

        events = await get_run_events(async_session, run_id)
        event_states = [e.state for e in events]
        assert "reviewing" in event_states

    async def test_approve_verdict_stays_in_reviewing(
        self,
        async_session: AsyncSession,
        run_engine: RunEngine,
        sample_task_request: TaskRequest,
        approve_verdict: ReviewVerdict,
    ):
        """Approved review keeps run in REVIEWING (caller handles next transition)."""
        run_id = await self._setup_run_in_verification_passed(
            async_session, run_engine, sample_task_request,
        )
        run_engine.agent_runner.run_reviewer = AsyncMock(return_value=approve_verdict)

        review = await run_engine._run_review(run_id, SAMPLE_DIFF, sample_task_request)

        assert review.verdict == ReviewVerdictType.APPROVE
        run = await get_run(async_session, run_id)
        assert run.state == RunState.REVIEWING.value

    async def test_reject_verdict_transitions_to_review_failed(
        self,
        async_session: AsyncSession,
        run_engine: RunEngine,
        sample_task_request: TaskRequest,
        reject_verdict: ReviewVerdict,
    ):
        """Rejected review transitions to REVIEW_FAILED."""
        run_id = await self._setup_run_in_verification_passed(
            async_session, run_engine, sample_task_request,
        )
        run_engine.agent_runner.run_reviewer = AsyncMock(return_value=reject_verdict)

        review = await run_engine._run_review(run_id, SAMPLE_DIFF, sample_task_request)

        assert review.verdict == ReviewVerdictType.REJECT
        run = await get_run(async_session, run_id)
        assert run.state == RunState.REVIEW_FAILED.value

    async def test_request_changes_stays_in_reviewing(
        self,
        async_session: AsyncSession,
        run_engine: RunEngine,
        sample_task_request: TaskRequest,
        request_changes_verdict: ReviewVerdict,
    ):
        """REQUEST_CHANGES keeps run in REVIEWING (PR opens with advisory notes)."""
        run_id = await self._setup_run_in_verification_passed(
            async_session, run_engine, sample_task_request,
        )
        run_engine.agent_runner.run_reviewer = AsyncMock(
            return_value=request_changes_verdict,
        )

        review = await run_engine._run_review(run_id, SAMPLE_DIFF, sample_task_request)

        assert review.verdict == ReviewVerdictType.REQUEST_CHANGES
        run = await get_run(async_session, run_id)
        assert run.state == RunState.REVIEWING.value

    async def test_stores_review_artifact(
        self,
        async_session: AsyncSession,
        run_engine: RunEngine,
        sample_task_request: TaskRequest,
        approve_verdict: ReviewVerdict,
        artifact_store: ArtifactStore,
    ):
        """_run_review stores review.json artifact."""
        run_id = await self._setup_run_in_verification_passed(
            async_session, run_engine, sample_task_request,
        )
        run_engine.agent_runner.run_reviewer = AsyncMock(return_value=approve_verdict)

        await run_engine._run_review(run_id, SAMPLE_DIFF, sample_task_request)

        artifacts = await artifact_store.list_artifacts(run_id)
        assert len(artifacts) == 1
        assert "review" in artifacts[0]

        content = json.loads(await artifact_store.retrieve(artifacts[0]))
        assert content["verdict"] == "approve"

    async def test_generates_pr_title_with_task_type(
        self,
        async_session: AsyncSession,
        run_engine: RunEngine,
        sample_task_request: TaskRequest,
        approve_verdict: ReviewVerdict,
    ):
        """PR title uses task_type value: '[Foundry] bug_fix: {title}'."""
        run_id = await self._setup_run_in_verification_passed(
            async_session, run_engine, sample_task_request,
        )
        run_engine.agent_runner.run_reviewer = AsyncMock(return_value=approve_verdict)

        await run_engine._run_review(run_id, SAMPLE_DIFF, sample_task_request)

        call_kwargs = run_engine.agent_runner.run_reviewer.call_args.kwargs
        assert call_kwargs["pr_title"] == "[Foundry] bug_fix: Fix pagination bug"

    async def test_generates_pr_description_from_prompt(
        self,
        async_session: AsyncSession,
        run_engine: RunEngine,
        sample_task_request: TaskRequest,
        approve_verdict: ReviewVerdict,
    ):
        """PR description is derived from task request prompt."""
        run_id = await self._setup_run_in_verification_passed(
            async_session, run_engine, sample_task_request,
        )
        run_engine.agent_runner.run_reviewer = AsyncMock(return_value=approve_verdict)

        await run_engine._run_review(run_id, SAMPLE_DIFF, sample_task_request)

        call_kwargs = run_engine.agent_runner.run_reviewer.call_args.kwargs
        assert "off-by-one" in call_kwargs["pr_description"]

    async def test_passes_task_type_to_reviewer(
        self,
        async_session: AsyncSession,
        run_engine: RunEngine,
        sample_task_request: TaskRequest,
        approve_verdict: ReviewVerdict,
    ):
        """_run_review passes task_type to run_reviewer for model routing."""
        run_id = await self._setup_run_in_verification_passed(
            async_session, run_engine, sample_task_request,
        )
        run_engine.agent_runner.run_reviewer = AsyncMock(return_value=approve_verdict)

        await run_engine._run_review(run_id, SAMPLE_DIFF, sample_task_request)

        call_kwargs = run_engine.agent_runner.run_reviewer.call_args.kwargs
        assert call_kwargs["task_type"] == TaskType.BUG_FIX

    async def test_migration_guard_reject_blocks_review(
        self,
        async_session: AsyncSession,
        run_engine: RunEngine,
        sample_task_request: TaskRequest,
    ):
        """Migration guard rejection transitions to REVIEW_FAILED before reviewer runs."""
        run_id = await self._setup_run_in_verification_passed(
            async_session, run_engine, sample_task_request,
        )
        # run_reviewer should NOT be called if guard rejects
        run_engine.agent_runner.run_reviewer = AsyncMock()

        # bug_fix + migration diff → immediate reject (no agent call)
        review = await run_engine._run_review(
            run_id, MIGRATION_DIFF, sample_task_request,
        )

        assert review.verdict == ReviewVerdictType.REJECT
        run = await get_run(async_session, run_id)
        assert run.state == RunState.REVIEW_FAILED.value
        run_engine.agent_runner.run_reviewer.assert_not_called()

    async def test_migration_guard_approve_proceeds_to_review(
        self,
        async_session: AsyncSession,
        run_engine: RunEngine,
        migration_task_request: TaskRequest,
        approve_verdict: ReviewVerdict,
    ):
        """Migration guard approval proceeds to the normal review."""
        run_id = await self._setup_run_in_verification_passed(
            async_session, run_engine, migration_task_request,
        )
        guard_approve = ReviewVerdict(
            verdict=ReviewVerdictType.APPROVE,
            issues=[],
            summary="Migration looks safe.",
        )
        run_engine.agent_runner.run_migration_guard = AsyncMock(
            return_value=guard_approve,
        )
        run_engine.agent_runner.run_reviewer = AsyncMock(
            return_value=approve_verdict,
        )

        review = await run_engine._run_review(
            run_id, MIGRATION_DIFF, migration_task_request,
        )

        assert review.verdict == ReviewVerdictType.APPROVE
        run_engine.agent_runner.run_migration_guard.assert_called_once()
        run_engine.agent_runner.run_reviewer.assert_called_once()

    async def test_creates_run_events_for_transitions(
        self,
        async_session: AsyncSession,
        run_engine: RunEngine,
        sample_task_request: TaskRequest,
        reject_verdict: ReviewVerdict,
    ):
        """State transitions create RunEvent records."""
        run_id = await self._setup_run_in_verification_passed(
            async_session, run_engine, sample_task_request,
        )
        run_engine.agent_runner.run_reviewer = AsyncMock(return_value=reject_verdict)

        await run_engine._run_review(run_id, SAMPLE_DIFF, sample_task_request)

        events = await get_run_events(async_session, run_id)
        event_states = [e.state for e in events]
        assert "reviewing" in event_states
        assert "review_failed" in event_states

    async def test_returns_review_verdict(
        self,
        async_session: AsyncSession,
        run_engine: RunEngine,
        sample_task_request: TaskRequest,
        approve_verdict: ReviewVerdict,
    ):
        """_run_review returns the ReviewVerdict from the reviewer."""
        run_id = await self._setup_run_in_verification_passed(
            async_session, run_engine, sample_task_request,
        )
        run_engine.agent_runner.run_reviewer = AsyncMock(return_value=approve_verdict)

        result = await run_engine._run_review(run_id, SAMPLE_DIFF, sample_task_request)

        assert isinstance(result, ReviewVerdict)
        assert result.verdict == ReviewVerdictType.APPROVE
        assert result.summary == approve_verdict.summary
