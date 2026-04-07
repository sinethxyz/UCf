"""Task implementation: review_diff.

Independent code review of a diff without access to the plan.
Produces a ReviewVerdict artifact. This IS the review — it does not
itself get reviewed.
"""

from __future__ import annotations

from typing import TYPE_CHECKING
from uuid import UUID

from foundry.contracts.shared import MCPProfile, TaskType
from foundry.contracts.task_types import TaskRequest
from foundry.tasks import TaskExecutor, register_task

if TYPE_CHECKING:
    from foundry.orchestration.run_engine import RunEngine


@register_task(TaskType.REVIEW_DIFF)
class ReviewDiffTask(TaskExecutor):
    """Performs standalone independent code review of a diff.

    Uses Opus for high-quality review reasoning. The reviewer does NOT
    have access to the original plan — it judges the diff purely on its
    own merits to prevent confirmation bias.

    Workflow:
    1. Load: Read the diff from task_request metadata or worktree.
    2. Analyze: Review the diff for correctness, safety, performance,
       test coverage, API contract compliance, and style.
    3. Verdict: Produce a ReviewVerdict (approve / request_changes / reject)
       with categorized issues (critical, major, minor, nit).
    4. Store: Persist the ReviewVerdict as an artifact.
    """

    default_model = "claude-opus-4-6"
    mcp_profile = MCPProfile.GITHUB_ONLY
    requires_verification = False
    requires_review = False

    async def execute(
        self,
        run_engine: RunEngine,
        run_id: UUID,
        task_request: TaskRequest,
        worktree_path: str,
    ) -> dict:
        """Execute a diff review task.

        Steps:
        1. Load diff from worktree or task_request.metadata.
        2. Analyze for correctness, safety, performance, tests, contracts.
        3. Produce ReviewVerdict with categorized issues.
        4. Store ReviewVerdict artifact.
        """
        raise NotImplementedError("Phase 1")

    async def get_plan_prompt(self, task_request: TaskRequest) -> str:
        """Generate planning prompt for review diff.

        Review tasks don't use a traditional planning phase — returns
        a prompt describing the review criteria and output format.
        """
        raise NotImplementedError("Phase 1")
