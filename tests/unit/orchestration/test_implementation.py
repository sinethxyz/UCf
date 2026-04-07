"""Tests for the implementation phase: run_implementer, _run_implementation, and BugFixTask.execute.

Tests verify:
- AgentRunner.run_implementer() selects the correct system prompt, model,
  tools, and working directory, then captures git diff.
- RunEngine._run_implementation() manages state transitions (PLANNING ->
  IMPLEMENTING -> VERIFYING), environment variables, diff artifact storage,
  and error handling (transition to ERRORED on failure).
- BugFixTask.execute() delegates to run_engine lifecycle phases and returns
  structured results with diff, plan, and files_changed.
"""

import json
import os
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import UUID, uuid4

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from foundry.contracts.shared import Complexity, MCPProfile, RunState, TaskType
from foundry.contracts.task_types import PlanArtifact, PlanStep, TaskRequest
from foundry.db.queries.runs import create_run, get_run, get_run_events
from foundry.orchestration.agent_runner import (
    IMPLEMENTER_TOOLS,
    AgentRunner,
)
from foundry.orchestration.run_engine import RunEngine
from foundry.storage.artifact_store import ArtifactStore, ArtifactType
from foundry.tasks.bug_fix import BugFixTask, _extract_files_from_diff


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
def sample_plan_artifact() -> PlanArtifact:
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
                rationale="Add regression test for pagination edge case",
            ),
        ],
        risks=["Might affect other pagination endpoints"],
        open_questions=[],
        estimated_complexity=Complexity.SMALL,
    )


SAMPLE_DIFF = """\
diff --git a/services/api/search/handler.go b/services/api/search/handler.go
index abc1234..def5678 100644
--- a/services/api/search/handler.go
+++ b/services/api/search/handler.go
@@ -42,7 +42,7 @@ func (h *SearchHandler) Search(w http.ResponseWriter, r *http.Request) {
-    offset := (page - 1) * pageSize + 1
+    offset := (page - 1) * pageSize
diff --git a/services/api/search/handler_test.go b/services/api/search/handler_test.go
index 1111111..2222222 100644
--- a/services/api/search/handler_test.go
+++ b/services/api/search/handler_test.go
@@ -100,6 +100,20 @@ func TestSearch_Pagination(t *testing.T) {
+func TestSearch_Pagination_FirstPageOffset(t *testing.T) {
+    // regression test for off-by-one
+}
"""


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


# ---------------------------------------------------------------------------
# _extract_files_from_diff tests
# ---------------------------------------------------------------------------


class TestExtractFilesFromDiff:
    """Tests for the diff file extraction helper."""

    def test_extracts_files_from_diff(self):
        files = _extract_files_from_diff(SAMPLE_DIFF)
        assert files == [
            "services/api/search/handler.go",
            "services/api/search/handler_test.go",
        ]

    def test_empty_diff_returns_empty_list(self):
        assert _extract_files_from_diff("") == []

    def test_no_diff_headers_returns_empty_list(self):
        assert _extract_files_from_diff("some random text\nno diff here") == []

    def test_deduplicates_files(self):
        dup_diff = (
            "diff --git a/file.go b/file.go\n"
            "diff --git a/file.go b/file.go\n"
        )
        assert _extract_files_from_diff(dup_diff) == ["file.go"]

    def test_returns_sorted_files(self):
        multi_diff = (
            "diff --git a/z_file.go b/z_file.go\n"
            "diff --git a/a_file.go b/a_file.go\n"
        )
        files = _extract_files_from_diff(multi_diff)
        assert files == ["a_file.go", "z_file.go"]


# ---------------------------------------------------------------------------
# AgentRunner.run_implementer tests
# ---------------------------------------------------------------------------


class TestRunImplementer:
    """Tests for AgentRunner.run_implementer()."""

    async def test_run_implementer_uses_backend_system_prompt_for_go(
        self,
        runner: AgentRunner,
        sample_plan_artifact: PlanArtifact,
        sample_task_request: TaskRequest,
    ):
        """run_implementer uses BACKEND_IMPLEMENTER_SYSTEM for Go."""
        from foundry.orchestration.prompt_templates import BACKEND_IMPLEMENTER_SYSTEM

        runner.provider = MagicMock()
        runner.provider.run = AsyncMock(return_value={
            "response": {"files_changed": []},
            "raw_text": "{}",
            "model": "claude-sonnet-4-6",
            "tokens_in": 500,
            "tokens_out": 200,
            "duration_ms": 5000,
        })

        with patch("asyncio.create_subprocess_exec") as mock_exec:
            # Mock git diff HEAD
            mock_proc = AsyncMock()
            mock_proc.communicate = AsyncMock(return_value=(b"diff output", b""))
            mock_proc.returncode = 0
            # Second call for git diff --cached
            mock_proc2 = AsyncMock()
            mock_proc2.communicate = AsyncMock(return_value=(b"", b""))
            mock_proc2.returncode = 0
            mock_exec.side_effect = [mock_proc, mock_proc2]

            await runner.run_implementer(
                plan=sample_plan_artifact,
                task_request=sample_task_request,
                worktree_path="/tmp/worktree",
                language="go",
            )

        call_kwargs = runner.provider.run.call_args.kwargs
        assert call_kwargs["system_prompt"] == BACKEND_IMPLEMENTER_SYSTEM

    async def test_run_implementer_uses_frontend_system_prompt_for_typescript(
        self,
        runner: AgentRunner,
        sample_plan_artifact: PlanArtifact,
        sample_task_request: TaskRequest,
    ):
        """run_implementer uses FRONTEND_IMPLEMENTER_SYSTEM for TypeScript."""
        from foundry.orchestration.prompt_templates import FRONTEND_IMPLEMENTER_SYSTEM

        runner.provider = MagicMock()
        runner.provider.run = AsyncMock(return_value={
            "response": {"files_changed": []},
            "raw_text": "{}",
            "model": "claude-sonnet-4-6",
            "tokens_in": 500,
            "tokens_out": 200,
            "duration_ms": 5000,
        })

        with patch("asyncio.create_subprocess_exec") as mock_exec:
            mock_proc = AsyncMock()
            mock_proc.communicate = AsyncMock(return_value=(b"diff", b""))
            mock_proc2 = AsyncMock()
            mock_proc2.communicate = AsyncMock(return_value=(b"", b""))
            mock_exec.side_effect = [mock_proc, mock_proc2]

            await runner.run_implementer(
                plan=sample_plan_artifact,
                task_request=sample_task_request,
                worktree_path="/tmp/worktree",
                language="typescript",
            )

        call_kwargs = runner.provider.run.call_args.kwargs
        assert call_kwargs["system_prompt"] == FRONTEND_IMPLEMENTER_SYSTEM

    async def test_run_implementer_resolves_correct_model(
        self,
        runner: AgentRunner,
        sample_plan_artifact: PlanArtifact,
        sample_task_request: TaskRequest,
    ):
        """run_implementer resolves model via model_router for bug_fix + implementer."""
        runner.provider = MagicMock()
        runner.provider.run = AsyncMock(return_value={
            "response": {},
            "raw_text": "{}",
            "model": "claude-sonnet-4-6",
            "tokens_in": 100,
            "tokens_out": 50,
            "duration_ms": 1000,
        })

        with patch("asyncio.create_subprocess_exec") as mock_exec:
            mock_proc = AsyncMock()
            mock_proc.communicate = AsyncMock(return_value=(b"diff", b""))
            mock_proc2 = AsyncMock()
            mock_proc2.communicate = AsyncMock(return_value=(b"", b""))
            mock_exec.side_effect = [mock_proc, mock_proc2]

            await runner.run_implementer(
                plan=sample_plan_artifact,
                task_request=sample_task_request,
                worktree_path="/tmp/worktree",
                language="go",
            )

        call_kwargs = runner.provider.run.call_args.kwargs
        assert call_kwargs["model"] == "claude-sonnet-4-6"

    async def test_run_implementer_passes_implementer_tools(
        self,
        runner: AgentRunner,
        sample_plan_artifact: PlanArtifact,
        sample_task_request: TaskRequest,
    ):
        """run_implementer passes IMPLEMENTER_TOOLS (Read, Write, Edit, Bash, Grep, Glob)."""
        runner.provider = MagicMock()
        runner.provider.run = AsyncMock(return_value={
            "response": {},
            "raw_text": "{}",
            "model": "claude-sonnet-4-6",
            "tokens_in": 100,
            "tokens_out": 50,
            "duration_ms": 1000,
        })

        with patch("asyncio.create_subprocess_exec") as mock_exec:
            mock_proc = AsyncMock()
            mock_proc.communicate = AsyncMock(return_value=(b"diff", b""))
            mock_proc2 = AsyncMock()
            mock_proc2.communicate = AsyncMock(return_value=(b"", b""))
            mock_exec.side_effect = [mock_proc, mock_proc2]

            await runner.run_implementer(
                plan=sample_plan_artifact,
                task_request=sample_task_request,
                worktree_path="/tmp/worktree",
                language="go",
            )

        call_kwargs = runner.provider.run.call_args.kwargs
        assert call_kwargs["tools"] == IMPLEMENTER_TOOLS

    async def test_run_implementer_scopes_to_worktree(
        self,
        runner: AgentRunner,
        sample_plan_artifact: PlanArtifact,
        sample_task_request: TaskRequest,
    ):
        """run_implementer scopes tools to the worktree via working_directory."""
        runner.provider = MagicMock()
        runner.provider.run = AsyncMock(return_value={
            "response": {},
            "raw_text": "{}",
            "model": "claude-sonnet-4-6",
            "tokens_in": 100,
            "tokens_out": 50,
            "duration_ms": 1000,
        })

        with patch("asyncio.create_subprocess_exec") as mock_exec:
            mock_proc = AsyncMock()
            mock_proc.communicate = AsyncMock(return_value=(b"diff", b""))
            mock_proc2 = AsyncMock()
            mock_proc2.communicate = AsyncMock(return_value=(b"", b""))
            mock_exec.side_effect = [mock_proc, mock_proc2]

            await runner.run_implementer(
                plan=sample_plan_artifact,
                task_request=sample_task_request,
                worktree_path="/tmp/test-worktree",
                language="go",
            )

        call_kwargs = runner.provider.run.call_args.kwargs
        assert call_kwargs["working_directory"] == "/tmp/test-worktree"

    async def test_run_implementer_includes_plan_in_user_message(
        self,
        runner: AgentRunner,
        sample_plan_artifact: PlanArtifact,
        sample_task_request: TaskRequest,
    ):
        """run_implementer includes serialized plan JSON in the user message."""
        runner.provider = MagicMock()
        runner.provider.run = AsyncMock(return_value={
            "response": {},
            "raw_text": "{}",
            "model": "claude-sonnet-4-6",
            "tokens_in": 100,
            "tokens_out": 50,
            "duration_ms": 1000,
        })

        with patch("asyncio.create_subprocess_exec") as mock_exec:
            mock_proc = AsyncMock()
            mock_proc.communicate = AsyncMock(return_value=(b"diff", b""))
            mock_proc2 = AsyncMock()
            mock_proc2.communicate = AsyncMock(return_value=(b"", b""))
            mock_exec.side_effect = [mock_proc, mock_proc2]

            await runner.run_implementer(
                plan=sample_plan_artifact,
                task_request=sample_task_request,
                worktree_path="/tmp/worktree",
                language="go",
            )

        call_kwargs = runner.provider.run.call_args.kwargs
        user_msg = call_kwargs["user_message"]
        assert sample_task_request.title in user_msg
        assert "handler.go" in user_msg  # plan step file path

    async def test_run_implementer_captures_git_diff(
        self,
        runner: AgentRunner,
        sample_plan_artifact: PlanArtifact,
        sample_task_request: TaskRequest,
    ):
        """run_implementer captures combined unstaged + staged diff."""
        runner.provider = MagicMock()
        runner.provider.run = AsyncMock(return_value={
            "response": {},
            "raw_text": "{}",
            "model": "claude-sonnet-4-6",
            "tokens_in": 100,
            "tokens_out": 50,
            "duration_ms": 1000,
        })

        with patch("asyncio.create_subprocess_exec") as mock_exec:
            mock_proc = AsyncMock()
            mock_proc.communicate = AsyncMock(return_value=(b"unstaged diff\n", b""))
            mock_proc2 = AsyncMock()
            mock_proc2.communicate = AsyncMock(return_value=(b"staged diff\n", b""))
            mock_exec.side_effect = [mock_proc, mock_proc2]

            diff = await runner.run_implementer(
                plan=sample_plan_artifact,
                task_request=sample_task_request,
                worktree_path="/tmp/worktree",
                language="go",
            )

        assert "unstaged diff" in diff
        assert "staged diff" in diff

    async def test_run_implementer_returns_empty_string_when_no_changes(
        self,
        runner: AgentRunner,
        sample_plan_artifact: PlanArtifact,
        sample_task_request: TaskRequest,
    ):
        """run_implementer returns empty string when git diff produces nothing."""
        runner.provider = MagicMock()
        runner.provider.run = AsyncMock(return_value={
            "response": {},
            "raw_text": "{}",
            "model": "claude-sonnet-4-6",
            "tokens_in": 100,
            "tokens_out": 50,
            "duration_ms": 1000,
        })

        with patch("asyncio.create_subprocess_exec") as mock_exec:
            mock_proc1 = AsyncMock()
            mock_proc1.communicate = AsyncMock(return_value=(b"", b""))
            mock_proc2 = AsyncMock()
            mock_proc2.communicate = AsyncMock(return_value=(b"", b""))
            # Third call for git status --porcelain
            mock_proc3 = AsyncMock()
            mock_proc3.communicate = AsyncMock(return_value=(b"", b""))
            mock_exec.side_effect = [mock_proc1, mock_proc2, mock_proc3]

            diff = await runner.run_implementer(
                plan=sample_plan_artifact,
                task_request=sample_task_request,
                worktree_path="/tmp/worktree",
                language="go",
            )

        assert diff == ""

    async def test_run_implementer_propagates_provider_errors(
        self,
        runner: AgentRunner,
        sample_plan_artifact: PlanArtifact,
        sample_task_request: TaskRequest,
    ):
        """run_implementer propagates exceptions from the provider."""
        runner.provider = MagicMock()
        runner.provider.run = AsyncMock(
            side_effect=RuntimeError("Agent session failed")
        )

        with pytest.raises(RuntimeError, match="Agent session failed"):
            await runner.run_implementer(
                plan=sample_plan_artifact,
                task_request=sample_task_request,
                worktree_path="/tmp/worktree",
                language="go",
            )


# ---------------------------------------------------------------------------
# RunEngine._run_implementation tests
# ---------------------------------------------------------------------------


class TestRunImplementation:
    """Tests for RunEngine._run_implementation() state transitions and artifact storage."""

    async def _setup_run_in_planning_state(
        self,
        session: AsyncSession,
        run_engine: RunEngine,
        task_request: TaskRequest,
    ) -> UUID:
        """Create a run and advance it to PLANNING state."""
        run = await create_run(session, task_request)
        run_id = run.id
        await run_engine._transition(
            run_id, RunState.QUEUED, RunState.CREATING_WORKTREE, "Creating worktree",
        )
        await run_engine._transition(
            run_id, RunState.CREATING_WORKTREE, RunState.PLANNING, "Starting planning",
        )
        return run_id

    async def test_transitions_planning_to_implementing_to_verifying(
        self,
        async_session: AsyncSession,
        run_engine: RunEngine,
        sample_task_request: TaskRequest,
        sample_plan_artifact: PlanArtifact,
    ):
        """On success: PLANNING -> IMPLEMENTING -> VERIFYING."""
        run_id = await self._setup_run_in_planning_state(
            async_session, run_engine, sample_task_request,
        )
        run_engine.agent_runner.run_implementer = AsyncMock(return_value=SAMPLE_DIFF)

        diff = await run_engine._run_implementation(
            run_id, sample_plan_artifact, sample_task_request, "/tmp/worktree",
        )

        assert diff == SAMPLE_DIFF
        run = await get_run(async_session, run_id)
        assert run is not None
        assert run.state == RunState.VERIFYING.value

    async def test_transitions_to_errored_on_failure(
        self,
        async_session: AsyncSession,
        run_engine: RunEngine,
        sample_task_request: TaskRequest,
        sample_plan_artifact: PlanArtifact,
    ):
        """On failure: PLANNING -> IMPLEMENTING -> ERRORED."""
        run_id = await self._setup_run_in_planning_state(
            async_session, run_engine, sample_task_request,
        )
        run_engine.agent_runner.run_implementer = AsyncMock(
            side_effect=RuntimeError("Agent crashed"),
        )

        diff = await run_engine._run_implementation(
            run_id, sample_plan_artifact, sample_task_request, "/tmp/worktree",
        )

        assert diff is None
        run = await get_run(async_session, run_id)
        assert run is not None
        assert run.state == RunState.ERRORED.value

    async def test_stores_diff_artifact_on_success(
        self,
        async_session: AsyncSession,
        run_engine: RunEngine,
        sample_task_request: TaskRequest,
        sample_plan_artifact: PlanArtifact,
        artifact_store: ArtifactStore,
    ):
        """Diff is stored as an artifact (diff.patch) on success."""
        run_id = await self._setup_run_in_planning_state(
            async_session, run_engine, sample_task_request,
        )
        run_engine.agent_runner.run_implementer = AsyncMock(return_value=SAMPLE_DIFF)

        await run_engine._run_implementation(
            run_id, sample_plan_artifact, sample_task_request, "/tmp/worktree",
        )

        artifacts = await artifact_store.list_artifacts(run_id)
        assert len(artifacts) == 1
        assert "diff" in artifacts[0]

        content = await artifact_store.retrieve(artifacts[0])
        assert b"handler.go" in content

    async def test_stores_error_log_on_failure(
        self,
        async_session: AsyncSession,
        run_engine: RunEngine,
        sample_task_request: TaskRequest,
        sample_plan_artifact: PlanArtifact,
        artifact_store: ArtifactStore,
    ):
        """Error log artifact is stored when implementation fails."""
        run_id = await self._setup_run_in_planning_state(
            async_session, run_engine, sample_task_request,
        )
        run_engine.agent_runner.run_implementer = AsyncMock(
            side_effect=RuntimeError("Agent crashed"),
        )

        await run_engine._run_implementation(
            run_id, sample_plan_artifact, sample_task_request, "/tmp/worktree",
        )

        artifacts = await artifact_store.list_artifacts(run_id)
        assert len(artifacts) == 1
        content = json.loads(await artifact_store.retrieve(artifacts[0]))
        assert content["error"] == "Agent crashed"
        assert content["phase"] == "implementation"

    async def test_sets_environment_variables(
        self,
        async_session: AsyncSession,
        run_engine: RunEngine,
        sample_task_request: TaskRequest,
        sample_plan_artifact: PlanArtifact,
    ):
        """Environment variables are set during agent execution."""
        run_id = await self._setup_run_in_planning_state(
            async_session, run_engine, sample_task_request,
        )

        captured_env: dict[str, str | None] = {}

        async def _capture_env(**kwargs):
            captured_env["RUN_ID"] = os.environ.get("RUN_ID")
            captured_env["RUN_STATE"] = os.environ.get("RUN_STATE")
            captured_env["RUN_TASK_TYPE"] = os.environ.get("RUN_TASK_TYPE")
            captured_env["WORKTREE_PATH"] = os.environ.get("WORKTREE_PATH")
            captured_env["ARTIFACT_DIR"] = os.environ.get("ARTIFACT_DIR")
            return SAMPLE_DIFF

        run_engine.agent_runner.run_implementer = AsyncMock(side_effect=_capture_env)

        await run_engine._run_implementation(
            run_id, sample_plan_artifact, sample_task_request, "/tmp/worktree",
        )

        assert captured_env["RUN_ID"] == str(run_id)
        assert captured_env["RUN_STATE"] == "implementing"
        assert captured_env["RUN_TASK_TYPE"] == "bug_fix"
        assert captured_env["WORKTREE_PATH"] == "/tmp/worktree"
        assert captured_env["ARTIFACT_DIR"] is not None

    async def test_cleans_up_environment_variables_on_success(
        self,
        async_session: AsyncSession,
        run_engine: RunEngine,
        sample_task_request: TaskRequest,
        sample_plan_artifact: PlanArtifact,
    ):
        """Environment variables are cleaned up after successful execution."""
        run_id = await self._setup_run_in_planning_state(
            async_session, run_engine, sample_task_request,
        )
        run_engine.agent_runner.run_implementer = AsyncMock(return_value=SAMPLE_DIFF)

        # Ensure env vars don't exist before
        for key in ("RUN_ID", "RUN_STATE", "RUN_TASK_TYPE", "ARTIFACT_DIR", "WORKTREE_PATH"):
            os.environ.pop(key, None)

        await run_engine._run_implementation(
            run_id, sample_plan_artifact, sample_task_request, "/tmp/worktree",
        )

        # Env vars should be cleaned up
        for key in ("RUN_ID", "RUN_STATE", "RUN_TASK_TYPE", "ARTIFACT_DIR", "WORKTREE_PATH"):
            assert os.environ.get(key) is None

    async def test_cleans_up_environment_variables_on_failure(
        self,
        async_session: AsyncSession,
        run_engine: RunEngine,
        sample_task_request: TaskRequest,
        sample_plan_artifact: PlanArtifact,
    ):
        """Environment variables are cleaned up even when execution fails."""
        run_id = await self._setup_run_in_planning_state(
            async_session, run_engine, sample_task_request,
        )
        run_engine.agent_runner.run_implementer = AsyncMock(
            side_effect=RuntimeError("fail"),
        )

        for key in ("RUN_ID", "RUN_STATE", "RUN_TASK_TYPE", "ARTIFACT_DIR", "WORKTREE_PATH"):
            os.environ.pop(key, None)

        await run_engine._run_implementation(
            run_id, sample_plan_artifact, sample_task_request, "/tmp/worktree",
        )

        for key in ("RUN_ID", "RUN_STATE", "RUN_TASK_TYPE", "ARTIFACT_DIR", "WORKTREE_PATH"):
            assert os.environ.get(key) is None

    async def test_creates_run_events_for_transitions(
        self,
        async_session: AsyncSession,
        run_engine: RunEngine,
        sample_task_request: TaskRequest,
        sample_plan_artifact: PlanArtifact,
    ):
        """State transitions create RunEvent records."""
        run_id = await self._setup_run_in_planning_state(
            async_session, run_engine, sample_task_request,
        )
        run_engine.agent_runner.run_implementer = AsyncMock(return_value=SAMPLE_DIFF)

        await run_engine._run_implementation(
            run_id, sample_plan_artifact, sample_task_request, "/tmp/worktree",
        )

        events = await get_run_events(async_session, run_id)
        event_states = [e.state for e in events]
        # Should have: creating_worktree, planning (from setup), implementing, verifying
        assert "implementing" in event_states
        assert "verifying" in event_states

    async def test_empty_diff_does_not_store_artifact(
        self,
        async_session: AsyncSession,
        run_engine: RunEngine,
        sample_task_request: TaskRequest,
        sample_plan_artifact: PlanArtifact,
        artifact_store: ArtifactStore,
    ):
        """Empty diff does not produce a stored artifact."""
        run_id = await self._setup_run_in_planning_state(
            async_session, run_engine, sample_task_request,
        )
        run_engine.agent_runner.run_implementer = AsyncMock(return_value="  \n  ")

        await run_engine._run_implementation(
            run_id, sample_plan_artifact, sample_task_request, "/tmp/worktree",
        )

        artifacts = await artifact_store.list_artifacts(run_id)
        assert len(artifacts) == 0

    async def test_restores_preexisting_environment_variables(
        self,
        async_session: AsyncSession,
        run_engine: RunEngine,
        sample_task_request: TaskRequest,
        sample_plan_artifact: PlanArtifact,
    ):
        """Pre-existing environment variables are restored after execution."""
        run_id = await self._setup_run_in_planning_state(
            async_session, run_engine, sample_task_request,
        )
        run_engine.agent_runner.run_implementer = AsyncMock(return_value=SAMPLE_DIFF)

        os.environ["RUN_ID"] = "previous-run-id"
        os.environ["WORKTREE_PATH"] = "/previous/path"

        try:
            await run_engine._run_implementation(
                run_id, sample_plan_artifact, sample_task_request, "/tmp/worktree",
            )
            assert os.environ.get("RUN_ID") == "previous-run-id"
            assert os.environ.get("WORKTREE_PATH") == "/previous/path"
        finally:
            os.environ.pop("RUN_ID", None)
            os.environ.pop("WORKTREE_PATH", None)


# ---------------------------------------------------------------------------
# BugFixTask.execute tests
# ---------------------------------------------------------------------------


class TestBugFixExecute:
    """Tests for BugFixTask.execute() delegation to run_engine."""

    async def test_execute_returns_diff_plan_files_changed(
        self,
        async_session: AsyncSession,
        run_engine: RunEngine,
        sample_task_request: TaskRequest,
        sample_plan_artifact: PlanArtifact,
    ):
        """execute() returns dict with diff, plan, and files_changed."""
        run_id = uuid4()
        run_engine._run_planning = AsyncMock(return_value=sample_plan_artifact)
        run_engine._run_implementation = AsyncMock(return_value=SAMPLE_DIFF)

        task = BugFixTask()
        result = await task.execute(
            run_engine, run_id, sample_task_request, "/tmp/worktree",
        )

        assert result["diff"] == SAMPLE_DIFF
        assert result["plan"] == sample_plan_artifact.model_dump()
        assert "services/api/search/handler.go" in result["files_changed"]
        assert "services/api/search/handler_test.go" in result["files_changed"]

    async def test_execute_returns_empty_on_plan_failure(
        self,
        run_engine: RunEngine,
        sample_task_request: TaskRequest,
    ):
        """execute() returns empty results when planning fails."""
        run_engine._run_planning = AsyncMock(return_value=None)
        run_engine._run_implementation = AsyncMock()

        task = BugFixTask()
        result = await task.execute(
            run_engine, uuid4(), sample_task_request, "/tmp/worktree",
        )

        assert result["diff"] == ""
        assert result["plan"] is None
        assert result["files_changed"] == []
        run_engine._run_implementation.assert_not_called()

    async def test_execute_returns_empty_diff_on_implementation_failure(
        self,
        run_engine: RunEngine,
        sample_task_request: TaskRequest,
        sample_plan_artifact: PlanArtifact,
    ):
        """execute() returns empty diff when implementation fails."""
        run_engine._run_planning = AsyncMock(return_value=sample_plan_artifact)
        run_engine._run_implementation = AsyncMock(return_value=None)

        task = BugFixTask()
        result = await task.execute(
            run_engine, uuid4(), sample_task_request, "/tmp/worktree",
        )

        assert result["diff"] == ""
        assert result["plan"] is not None
        assert result["files_changed"] == []

    async def test_execute_delegates_planning_to_run_engine(
        self,
        run_engine: RunEngine,
        sample_task_request: TaskRequest,
        sample_plan_artifact: PlanArtifact,
    ):
        """execute() calls run_engine._run_planning with correct args."""
        run_id = uuid4()
        worktree_path = "/tmp/worktree"
        run_engine._run_planning = AsyncMock(return_value=sample_plan_artifact)
        run_engine._run_implementation = AsyncMock(return_value=SAMPLE_DIFF)

        task = BugFixTask()
        await task.execute(run_engine, run_id, sample_task_request, worktree_path)

        run_engine._run_planning.assert_called_once_with(
            run_id, sample_task_request, worktree_path,
        )

    async def test_execute_delegates_implementation_to_run_engine(
        self,
        run_engine: RunEngine,
        sample_task_request: TaskRequest,
        sample_plan_artifact: PlanArtifact,
    ):
        """execute() calls run_engine._run_implementation with plan and correct args."""
        run_id = uuid4()
        worktree_path = "/tmp/worktree"
        run_engine._run_planning = AsyncMock(return_value=sample_plan_artifact)
        run_engine._run_implementation = AsyncMock(return_value=SAMPLE_DIFF)

        task = BugFixTask()
        await task.execute(run_engine, run_id, sample_task_request, worktree_path)

        run_engine._run_implementation.assert_called_once_with(
            run_id, sample_plan_artifact, sample_task_request, worktree_path,
        )

    async def test_execute_skips_implementation_when_plan_fails(
        self,
        run_engine: RunEngine,
        sample_task_request: TaskRequest,
    ):
        """execute() does not call _run_implementation when planning returns None."""
        run_engine._run_planning = AsyncMock(return_value=None)
        run_engine._run_implementation = AsyncMock()

        task = BugFixTask()
        await task.execute(run_engine, uuid4(), sample_task_request, "/tmp/worktree")

        run_engine._run_implementation.assert_not_called()

    async def test_execute_handles_empty_diff(
        self,
        run_engine: RunEngine,
        sample_task_request: TaskRequest,
        sample_plan_artifact: PlanArtifact,
    ):
        """execute() handles an empty diff string gracefully."""
        run_engine._run_planning = AsyncMock(return_value=sample_plan_artifact)
        run_engine._run_implementation = AsyncMock(return_value="")

        task = BugFixTask()
        result = await task.execute(
            run_engine, uuid4(), sample_task_request, "/tmp/worktree",
        )

        assert result["diff"] == ""
        assert result["files_changed"] == []
        assert result["plan"] is not None
