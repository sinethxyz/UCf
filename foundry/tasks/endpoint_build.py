"""Task implementation: endpoint_build.

Builds a new API endpoint in unicorn-app following existing domain patterns.
Uses the planner, backend-implementer, and reviewer subagents.
"""

from __future__ import annotations

from typing import TYPE_CHECKING
from uuid import UUID

from foundry.contracts.shared import MCPProfile, TaskType
from foundry.contracts.task_types import TaskRequest
from foundry.tasks import TaskExecutor, register_task

if TYPE_CHECKING:
    from foundry.orchestration.run_engine import RunEngine


@register_task(TaskType.ENDPOINT_BUILD)
class EndpointBuildTask(TaskExecutor):
    """Builds a new API endpoint in unicorn-app.

    Workflow:
    1. Plan: Read target domain patterns in unicorn-app (models, handlers,
       routes, tests) to understand conventions. Generate a structured plan
       covering handler, model, routes, OpenAPI spec update, and tests.
    2. Implement: Dispatch to the backend-implementer subagent to execute
       the plan within the worktree.
    3. Verify: Run go build, go test, go vet, and OpenAPI spec validation
       to confirm the implementation is correct.
    4. Review: Independent reviewer subagent evaluates the diff.
    5. PR: Open a pull request if review passes.
    """

    default_model = "claude-sonnet-4-6"
    mcp_profile = MCPProfile.GITHUB_POSTGRES_READONLY
    requires_verification = True
    requires_review = True

    async def execute(
        self,
        run_engine: RunEngine,
        run_id: UUID,
        task_request: TaskRequest,
        worktree_path: str,
    ) -> dict:
        """Execute an endpoint build task.

        Steps:
        1. Reconnaissance: read existing domain patterns (handler structure,
           model conventions, route registration, test patterns).
        2. Plan: produce a PlanArtifact with steps for handler, model,
           routes, OpenAPI spec, and test files.
        3. Implement: run backend-implementer subagent with the plan.
        4. Verify: go build + go test + OpenAPI validate.
        5. Review: independent diff review.
        6. PR: open PR with artifacts.
        """
        raise NotImplementedError("Phase 1")

    async def get_plan_prompt(self, task_request: TaskRequest) -> str:
        """Generate planning prompt for endpoint build.

        Instructs the planner to read target domain patterns and produce
        a plan covering handler, model, routes, OpenAPI spec, and tests.
        """
        raise NotImplementedError("Phase 1")
