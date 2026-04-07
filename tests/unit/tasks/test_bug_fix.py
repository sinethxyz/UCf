"""Tests for BugFixTask.get_plan_prompt()."""

import pytest

from foundry.contracts.shared import MCPProfile, TaskType
from foundry.contracts.task_types import TaskRequest
from foundry.tasks.bug_fix import BugFixTask


@pytest.fixture
def bug_fix_task() -> BugFixTask:
    return BugFixTask()


@pytest.fixture
def bug_task_request() -> TaskRequest:
    return TaskRequest(
        task_type=TaskType.BUG_FIX,
        repo="unicorn-app",
        base_branch="main",
        title="Fix search pagination",
        prompt="Search results show wrong page when clicking next. "
        "The offset calculation appears to skip one result per page.",
        target_paths=[
            "services/api/search/handler.go",
            "services/api/search/handler_test.go",
        ],
        mcp_profile=MCPProfile.NONE,
    )


class TestGetPlanPrompt:
    """Tests for BugFixTask.get_plan_prompt()."""

    async def test_includes_bug_title(
        self, bug_fix_task: BugFixTask, bug_task_request: TaskRequest
    ):
        prompt = await bug_fix_task.get_plan_prompt(bug_task_request)
        assert bug_task_request.title in prompt

    async def test_includes_bug_description(
        self, bug_fix_task: BugFixTask, bug_task_request: TaskRequest
    ):
        prompt = await bug_fix_task.get_plan_prompt(bug_task_request)
        assert bug_task_request.prompt in prompt

    async def test_includes_target_paths(
        self, bug_fix_task: BugFixTask, bug_task_request: TaskRequest
    ):
        prompt = await bug_fix_task.get_plan_prompt(bug_task_request)
        for path in bug_task_request.target_paths:
            assert path in prompt

    async def test_includes_root_cause_analysis_instruction(
        self, bug_fix_task: BugFixTask, bug_task_request: TaskRequest
    ):
        prompt = await bug_fix_task.get_plan_prompt(bug_task_request)
        assert "root cause" in prompt.lower()

    async def test_includes_regression_test_instruction(
        self, bug_fix_task: BugFixTask, bug_task_request: TaskRequest
    ):
        prompt = await bug_fix_task.get_plan_prompt(bug_task_request)
        assert "regression test" in prompt.lower()

    async def test_includes_fix_strategy(
        self, bug_fix_task: BugFixTask, bug_task_request: TaskRequest
    ):
        prompt = await bug_fix_task.get_plan_prompt(bug_task_request)
        assert "fix" in prompt.lower()

    async def test_includes_verification_instruction(
        self, bug_fix_task: BugFixTask, bug_task_request: TaskRequest
    ):
        """Prompt must instruct verification via go build/vet/test."""
        prompt = await bug_fix_task.get_plan_prompt(bug_task_request)
        assert "go build" in prompt.lower() or "verification" in prompt.lower()

    async def test_includes_repo_name(
        self, bug_fix_task: BugFixTask, bug_task_request: TaskRequest
    ):
        prompt = await bug_fix_task.get_plan_prompt(bug_task_request)
        assert bug_task_request.repo in prompt

    async def test_handles_empty_target_paths(self, bug_fix_task: BugFixTask):
        """When no target paths are specified, the prompt should indicate that."""
        request = TaskRequest(
            task_type=TaskType.BUG_FIX,
            repo="unicorn-app",
            title="Fix login bug",
            prompt="Users can't log in after password reset",
            target_paths=[],
            mcp_profile=MCPProfile.NONE,
        )
        prompt = await bug_fix_task.get_plan_prompt(request)
        assert "not specified" in prompt.lower()

    async def test_requests_plan_artifact_json(
        self, bug_fix_task: BugFixTask, bug_task_request: TaskRequest
    ):
        """Prompt requests PlanArtifact JSON output with ordered steps."""
        prompt = await bug_fix_task.get_plan_prompt(bug_task_request)
        assert "planartifact" in prompt.lower() or "plan" in prompt.lower()
        assert "step" in prompt.lower()

    async def test_lists_all_affected_files_with_rationale(
        self, bug_fix_task: BugFixTask, bug_task_request: TaskRequest
    ):
        """Prompt instructs listing files with rationale."""
        prompt = await bug_fix_task.get_plan_prompt(bug_task_request)
        assert "rationale" in prompt.lower() or "file" in prompt.lower()
