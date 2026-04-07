"""Task implementation: refactor.

Performs structural code changes in atomic, verifiable steps.
Uses the safe-refactor pattern: make one change, verify, repeat.
"""

from __future__ import annotations

from typing import TYPE_CHECKING
from uuid import UUID

from foundry.contracts.shared import MCPProfile, TaskType
from foundry.contracts.task_types import TaskRequest
from foundry.tasks import TaskExecutor, register_task

if TYPE_CHECKING:
    from foundry.orchestration.run_engine import RunEngine


@register_task(TaskType.REFACTOR)
class RefactorTask(TaskExecutor):
    """Performs structural code refactoring in atomic steps.

    Workflow:
    1. Plan: Analyze the refactoring scope and break it into atomic steps.
       Each step must be independently verifiable (build + test pass after
       each step).
    2. Implement: Execute each atomic step sequentially, running verification
       after each step. If any step breaks verification, roll back that step
       and report.
    3. Verify: Final full verification after all steps complete.
    4. Review: Independent reviewer evaluates the combined diff.
    5. PR: Open a pull request with artifacts.
    """

    default_model = "claude-sonnet-4-6"
    mcp_profile = MCPProfile.GITHUB_ONLY
    requires_verification = True
    requires_review = True

    async def execute(
        self,
        run_engine: RunEngine,
        run_id: UUID,
        task_request: TaskRequest,
        worktree_path: str,
    ) -> dict:
        """Execute a refactor task.

        Steps:
        1. Reconnaissance: read code to understand current structure.
        2. Plan: produce a PlanArtifact with ordered atomic refactor steps.
        3. For each step:
           a. Apply the change.
           b. Run verification (build + test).
           c. If verification fails, roll back and report.
        4. Final verification: full build + test + lint.
        5. Review: independent diff review.
        6. PR: open PR with artifacts.
        """
        raise NotImplementedError("Phase 1")

    async def get_plan_prompt(self, task_request: TaskRequest) -> str:
        """Generate planning prompt for refactor.

        Instructs the planner to break the refactoring into atomic,
        independently verifiable steps.
        """
        raise NotImplementedError("Phase 1")
