"""Task implementation: migration_plan.

Produces a migration plan artifact using Opus for high-scrutiny planning.
Does NOT execute the migration — produces plan artifact only.
The migration guard subagent is auto-triggered for review.
"""

from uuid import UUID

from foundry.contracts.shared import MCPProfile, TaskType
from foundry.contracts.task_types import TaskRequest
from foundry.tasks import TaskExecutor, register_task


@register_task(TaskType.MIGRATION_PLAN)
class MigrationPlanTask(TaskExecutor):
    """Produces a database migration plan artifact.

    This task type only produces a plan — it does not implement the migration.
    Uses Opus for high-scrutiny architectural reasoning about schema changes.
    The migration guard subagent is automatically triggered during review.

    Workflow:
    1. Plan: Analyze the schema change requirement against current database
       state, application code references, and migration safety rules.
       Produce a detailed migration plan covering:
       - Forward migration (upgrade) steps
       - Rollback migration (downgrade) steps
       - Backwards compatibility analysis during rolling deploys
       - Multi-step breakdown for forbidden single-migration operations
    2. Review: Migration guard subagent validates the plan for safety,
       reversibility, and backwards compatibility.
    3. Store: Plan artifact is stored for human review and future execution.
    """

    default_model = "claude-opus-4-6"
    mcp_profile = MCPProfile.GITHUB_POSTGRES_READONLY
    requires_verification = True
    requires_review = True

    async def execute(
        self, run_id: UUID, task_request: TaskRequest, worktree_path: str
    ) -> dict:
        """Execute a migration planning task.

        Steps:
        1. Reconnaissance: read current schema, existing migrations,
           and application code that references affected tables/columns.
        2. Plan: produce a detailed migration PlanArtifact with upgrade,
           downgrade, compatibility analysis, and multi-step breakdown.
        3. Review: migration guard validates safety and reversibility.
        4. Store: persist plan artifact (no implementation, no PR).
        """
        raise NotImplementedError("Phase 1")

    async def get_plan_prompt(self, task_request: TaskRequest) -> str:
        """Generate planning prompt for migration plan.

        Instructs the planner to analyze schema change safety, reversibility,
        backwards compatibility, and produce a multi-step migration plan.
        """
        raise NotImplementedError("Phase 1")
