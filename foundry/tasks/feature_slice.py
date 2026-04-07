"""Task implementation: feature_slice.

Implements a feature slice that may span both backend (Go) and frontend
(TypeScript/Next.js). Coordinates between backend-implementer and
frontend-implementer subagents.
"""

from uuid import UUID

from foundry.contracts.shared import MCPProfile, TaskType
from foundry.contracts.task_types import TaskRequest
from foundry.tasks import TaskExecutor, register_task


@register_task(TaskType.FEATURE_SLICE)
class FeatureSliceTask(TaskExecutor):
    """Implements a cross-cutting feature slice across backend and frontend.

    Workflow:
    1. Plan: Analyze the feature requirement and identify backend (Go API)
       and frontend (Next.js) changes needed. Produce a structured plan
       covering both layers.
    2. Implement backend: Dispatch to backend-implementer for Go changes
       (handlers, models, routes, tests).
    3. Implement frontend: Dispatch to frontend-implementer for TypeScript
       changes (components, hooks, API client, tests).
    4. Verify: Run go build + go test for backend, tsc + eslint for frontend.
    5. Review: Independent reviewer evaluates the combined diff.
    6. PR: Open a pull request with artifacts.
    """

    default_model = "claude-sonnet-4-6"
    mcp_profile = MCPProfile.GITHUB_POSTGRES_READONLY
    requires_verification = True
    requires_review = True

    async def execute(
        self, run_id: UUID, task_request: TaskRequest, worktree_path: str
    ) -> dict:
        """Execute a feature slice task.

        Steps:
        1. Reconnaissance: read existing patterns in both backend and frontend.
        2. Plan: produce a PlanArtifact covering both Go and TS changes.
        3. Implement backend: run backend-implementer subagent.
        4. Implement frontend: run frontend-implementer subagent.
        5. Verify: go build + go test + tsc + eslint.
        6. Review: independent diff review.
        7. PR: open PR with artifacts.
        """
        raise NotImplementedError("Phase 1")

    async def get_plan_prompt(self, task_request: TaskRequest) -> str:
        """Generate planning prompt for feature slice.

        Instructs the planner to analyze both backend and frontend layers
        and produce a unified plan covering the full feature slice.
        """
        raise NotImplementedError("Phase 1")
