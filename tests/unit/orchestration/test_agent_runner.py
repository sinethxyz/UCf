"""Tests for AgentRunner — mock Claude client.

Tests verify that run_agent and run_planner correctly delegate to the
ClaudeAgentProvider with expected arguments and handle responses properly.
"""

from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from foundry.contracts.shared import Complexity, MCPProfile, TaskType
from foundry.contracts.task_types import PlanArtifact, PlanStep, TaskRequest
from foundry.orchestration.agent_runner import AgentRunner, PLANNER_TOOLS


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


@pytest.fixture
def runner() -> AgentRunner:
    return AgentRunner(api_key="test-key")


# ---------------------------------------------------------------------------
# run_agent tests
# ---------------------------------------------------------------------------


class TestRunAgent:
    """Tests for AgentRunner.run_agent()."""

    async def test_run_agent_delegates_to_provider_run(self, runner: AgentRunner):
        """run_agent without output_schema calls provider.run()."""
        runner.provider = MagicMock()
        runner.provider.run = AsyncMock(return_value={
            "response": {"result": "done"},
            "raw_text": '{"result": "done"}',
            "model": "claude-sonnet-4-6",
            "tokens_in": 100,
            "tokens_out": 50,
            "duration_ms": 1000,
        })

        result = await runner.run_agent(
            system_prompt="Test prompt",
            user_message="Do something",
            tools=[],
            model="claude-sonnet-4-6",
        )

        assert result["response"] == {"result": "done"}
        assert result["tokens_in"] == 100
        assert result["tokens_out"] == 50
        runner.provider.run.assert_called_once()

    async def test_run_agent_with_output_schema_delegates_to_structured(
        self, runner: AgentRunner, sample_plan_artifact: PlanArtifact
    ):
        """run_agent with output_schema calls provider.run_with_structured_output()."""
        runner.provider = MagicMock()
        runner.provider.run_with_structured_output = AsyncMock(return_value={
            "response": sample_plan_artifact,
            "model": "claude-sonnet-4-6",
            "tokens_in": 200,
            "tokens_out": 100,
            "duration_ms": 2000,
        })

        result = await runner.run_agent(
            system_prompt="Test",
            user_message="Plan",
            tools=PLANNER_TOOLS,
            model="claude-sonnet-4-6",
            output_schema=PlanArtifact,
        )

        assert isinstance(result["response"], PlanArtifact)
        runner.provider.run_with_structured_output.assert_called_once()

    async def test_run_agent_passes_worktree_path(self, runner: AgentRunner):
        """run_agent forwards worktree_path as working_directory."""
        runner.provider = MagicMock()
        runner.provider.run = AsyncMock(return_value={
            "response": "ok",
            "raw_text": "ok",
            "model": "claude-sonnet-4-6",
            "tokens_in": 10,
            "tokens_out": 5,
            "duration_ms": 100,
        })

        await runner.run_agent(
            system_prompt="Test",
            user_message="Explore",
            tools=PLANNER_TOOLS,
            model="claude-sonnet-4-6",
            worktree_path="/tmp/test-worktree",
        )

        call_kwargs = runner.provider.run.call_args.kwargs
        assert call_kwargs["working_directory"] == "/tmp/test-worktree"

    async def test_run_agent_passes_empty_tools_as_none(self, runner: AgentRunner):
        """Empty tool list is passed as None to the provider."""
        runner.provider = MagicMock()
        runner.provider.run = AsyncMock(return_value={
            "response": "ok",
            "raw_text": "ok",
            "model": "claude-sonnet-4-6",
            "tokens_in": 10,
            "tokens_out": 5,
            "duration_ms": 100,
        })

        await runner.run_agent(
            system_prompt="Test",
            user_message="Review",
            tools=[],
            model="claude-opus-4-6",
        )

        call_kwargs = runner.provider.run.call_args.kwargs
        assert call_kwargs["tools"] is None


# ---------------------------------------------------------------------------
# run_planner tests
# ---------------------------------------------------------------------------


class TestRunPlanner:
    """Tests for AgentRunner.run_planner()."""

    async def test_run_planner_returns_plan_artifact(
        self,
        runner: AgentRunner,
        sample_task_request: TaskRequest,
        sample_plan_artifact: PlanArtifact,
    ):
        """run_planner returns a validated PlanArtifact."""
        runner.provider = MagicMock()
        runner.provider.run_with_structured_output = AsyncMock(return_value={
            "response": sample_plan_artifact,
            "model": "claude-sonnet-4-6",
            "tokens_in": 500,
            "tokens_out": 200,
            "duration_ms": 5000,
        })

        plan = await runner.run_planner(sample_task_request, "/tmp/worktree")

        assert isinstance(plan, PlanArtifact)
        assert plan.task_id == sample_plan_artifact.task_id
        assert len(plan.steps) == 2

    async def test_run_planner_uses_correct_model(
        self,
        runner: AgentRunner,
        sample_task_request: TaskRequest,
        sample_plan_artifact: PlanArtifact,
    ):
        """run_planner resolves the model via model_router for bug_fix + planner."""
        runner.provider = MagicMock()
        runner.provider.run_with_structured_output = AsyncMock(return_value={
            "response": sample_plan_artifact,
            "model": "claude-sonnet-4-6",
            "tokens_in": 100,
            "tokens_out": 50,
            "duration_ms": 1000,
        })

        await runner.run_planner(sample_task_request, "/tmp/worktree")

        call_kwargs = runner.provider.run_with_structured_output.call_args.kwargs
        # bug_fix + planner resolves to claude-sonnet-4-6 per model_router
        assert call_kwargs["model"] == "claude-sonnet-4-6"

    async def test_run_planner_passes_planner_tools(
        self,
        runner: AgentRunner,
        sample_task_request: TaskRequest,
        sample_plan_artifact: PlanArtifact,
    ):
        """run_planner passes read-only PLANNER_TOOLS (Read, Grep, Glob)."""
        runner.provider = MagicMock()
        runner.provider.run_with_structured_output = AsyncMock(return_value={
            "response": sample_plan_artifact,
            "model": "claude-sonnet-4-6",
            "tokens_in": 100,
            "tokens_out": 50,
            "duration_ms": 1000,
        })

        await runner.run_planner(sample_task_request, "/tmp/worktree")

        call_kwargs = runner.provider.run_with_structured_output.call_args.kwargs
        assert call_kwargs["tools"] == ["Read", "Grep", "Glob"]

    async def test_run_planner_passes_worktree_as_working_directory(
        self,
        runner: AgentRunner,
        sample_task_request: TaskRequest,
        sample_plan_artifact: PlanArtifact,
    ):
        """run_planner scopes tools to the worktree via working_directory."""
        runner.provider = MagicMock()
        runner.provider.run_with_structured_output = AsyncMock(return_value={
            "response": sample_plan_artifact,
            "model": "claude-sonnet-4-6",
            "tokens_in": 100,
            "tokens_out": 50,
            "duration_ms": 1000,
        })

        await runner.run_planner(sample_task_request, "/tmp/test-worktree")

        call_kwargs = runner.provider.run_with_structured_output.call_args.kwargs
        assert call_kwargs["working_directory"] == "/tmp/test-worktree"

    async def test_run_planner_passes_plan_artifact_schema(
        self,
        runner: AgentRunner,
        sample_task_request: TaskRequest,
        sample_plan_artifact: PlanArtifact,
    ):
        """run_planner requests PlanArtifact as the output_schema."""
        runner.provider = MagicMock()
        runner.provider.run_with_structured_output = AsyncMock(return_value={
            "response": sample_plan_artifact,
            "model": "claude-sonnet-4-6",
            "tokens_in": 100,
            "tokens_out": 50,
            "duration_ms": 1000,
        })

        await runner.run_planner(sample_task_request, "/tmp/worktree")

        call_kwargs = runner.provider.run_with_structured_output.call_args.kwargs
        assert call_kwargs["output_schema"] is PlanArtifact

    async def test_run_planner_uses_planner_system_prompt(
        self,
        runner: AgentRunner,
        sample_task_request: TaskRequest,
        sample_plan_artifact: PlanArtifact,
    ):
        """run_planner uses the PLANNER_SYSTEM prompt template."""
        from foundry.orchestration.prompt_templates import PLANNER_SYSTEM

        runner.provider = MagicMock()
        runner.provider.run_with_structured_output = AsyncMock(return_value={
            "response": sample_plan_artifact,
            "model": "claude-sonnet-4-6",
            "tokens_in": 100,
            "tokens_out": 50,
            "duration_ms": 1000,
        })

        await runner.run_planner(sample_task_request, "/tmp/worktree")

        call_kwargs = runner.provider.run_with_structured_output.call_args.kwargs
        assert call_kwargs["system_prompt"] == PLANNER_SYSTEM

    async def test_run_planner_includes_task_info_in_user_message(
        self,
        runner: AgentRunner,
        sample_task_request: TaskRequest,
        sample_plan_artifact: PlanArtifact,
    ):
        """run_planner builds a user message containing task type, title, and prompt."""
        runner.provider = MagicMock()
        runner.provider.run_with_structured_output = AsyncMock(return_value={
            "response": sample_plan_artifact,
            "model": "claude-sonnet-4-6",
            "tokens_in": 100,
            "tokens_out": 50,
            "duration_ms": 1000,
        })

        await runner.run_planner(sample_task_request, "/tmp/worktree")

        call_kwargs = runner.provider.run_with_structured_output.call_args.kwargs
        user_msg = call_kwargs["user_message"]
        assert sample_task_request.title in user_msg
        assert sample_task_request.prompt in user_msg
        assert sample_task_request.task_type.value in user_msg

    async def test_run_planner_handles_dict_response(
        self,
        runner: AgentRunner,
        sample_task_request: TaskRequest,
        sample_plan_artifact: PlanArtifact,
    ):
        """run_planner validates dict responses into PlanArtifact."""
        runner.provider = MagicMock()
        runner.provider.run_with_structured_output = AsyncMock(return_value={
            "response": sample_plan_artifact.model_dump(),
            "model": "claude-sonnet-4-6",
            "tokens_in": 100,
            "tokens_out": 50,
            "duration_ms": 1000,
        })

        plan = await runner.run_planner(sample_task_request, "/tmp/worktree")

        assert isinstance(plan, PlanArtifact)
        assert plan.estimated_complexity == Complexity.SMALL

    async def test_run_planner_propagates_provider_errors(
        self,
        runner: AgentRunner,
        sample_task_request: TaskRequest,
    ):
        """run_planner propagates exceptions from the provider."""
        runner.provider = MagicMock()
        runner.provider.run_with_structured_output = AsyncMock(
            side_effect=ValueError("Model unavailable")
        )

        with pytest.raises(ValueError, match="Model unavailable"):
            await runner.run_planner(sample_task_request, "/tmp/worktree")
