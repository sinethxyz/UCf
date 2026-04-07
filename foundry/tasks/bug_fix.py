"""Task implementation: bug_fix.

Diagnoses and fixes a reported bug with a mandatory regression test.
"""

from uuid import UUID

from foundry.contracts.shared import MCPProfile, TaskType
from foundry.contracts.task_types import TaskRequest
from foundry.tasks import TaskExecutor, register_task


@register_task(TaskType.BUG_FIX)
class BugFixTask(TaskExecutor):
    """Diagnoses and fixes a reported bug.

    Workflow:
    1. Plan: Analyze the bug report to build a reproduction understanding.
       Identify the root cause through code analysis. Produce a fix plan
       that includes a regression test.
    2. Implement: Dispatch to the appropriate implementer subagent to
       apply the fix and write a regression test that fails before the
       fix and passes after.
    3. Verify: Run build and test suite to confirm the fix and ensure
       no regressions.
    4. Review: Independent reviewer evaluates the diff.
    5. PR: Open a pull request with artifacts.
    """

    default_model = "claude-sonnet-4-6"
    mcp_profile = MCPProfile.GITHUB_ONLY
    requires_verification = True
    requires_review = True

    async def execute(
        self, run_id: UUID, task_request: TaskRequest, worktree_path: str
    ) -> dict:
        """Execute a bug fix task.

        Steps:
        1. Reconnaissance: analyze bug report, read related code to
           understand the root cause.
        2. Plan: produce a PlanArtifact with root cause analysis,
           fix strategy, and regression test plan.
        3. Implement: apply fix + write regression test.
        4. Verify: build + test (regression test must pass).
        5. Review: independent diff review.
        6. PR: open PR with artifacts.
        """
        raise NotImplementedError("Phase 1")

    async def get_plan_prompt(self, task_request: TaskRequest) -> str:
        """Generate planning prompt for bug fix.

        Instructs the planner to reproduce the bug understanding, identify
        the root cause, and plan both the fix and a regression test.
        """
        raise NotImplementedError("Phase 1")
