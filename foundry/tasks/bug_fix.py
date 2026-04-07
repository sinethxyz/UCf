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

        This is a thin wrapper — the RunEngine owns the lifecycle orchestration.
        The task executor provides task-specific configuration and prompts.

        Returns:
            Dict with task-specific results.
        """
        return {
            "task_type": "bug_fix",
            "run_id": str(run_id),
            "requires_verification": self.requires_verification,
            "requires_review": self.requires_review,
            "language": "go",
        }

    async def get_plan_prompt(self, task_request: TaskRequest) -> str:
        """Generate planning prompt for bug fix.

        Instructs the planner to reproduce the bug understanding, identify
        the root cause, and plan both the fix and a regression test.
        """
        target_paths = "\n".join(f"  - {p}" for p in task_request.target_paths) if task_request.target_paths else "  - (not specified — explore to find relevant files)"

        return f"""\
You are planning a bug fix for the following issue:

**Title**: {task_request.title}

**Bug Report**:
{task_request.prompt}

**Target paths (hints)**:
{target_paths}

**Repository**: {task_request.repo}

Your plan must include:
1. **Root cause analysis**: Read the relevant code to understand what causes the bug.
2. **Fix strategy**: Identify the exact file(s) and function(s) to modify.
3. **Regression test**: Plan a test that reproduces the bug (fails before fix, passes after).
4. **Verification**: The fix must pass `go build`, `go vet`, and `go test`.

Return a PlanArtifact JSON with ordered steps. Each step should target a specific file \
with a clear rationale. Include a regression test step.

Remember: every bug fix MUST include a regression test. A fix without a test is incomplete.\
"""
