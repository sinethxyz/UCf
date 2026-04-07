"""Task implementation: eval_run.

Runs an evaluation dataset through a model, scores results, aggregates
metrics, and stores eval artifacts.
"""

from uuid import UUID

from foundry.contracts.shared import MCPProfile, TaskType
from foundry.contracts.task_types import TaskRequest
from foundry.tasks import TaskExecutor, register_task


@register_task(TaskType.EVAL_RUN)
class EvalRunTask(TaskExecutor):
    """Runs model evaluations against curated datasets.

    Uses the Message Batches API for cost-efficient inference across
    eval datasets. No code changes are made.

    Workflow:
    1. Load: Read eval dataset and scorer configuration from the task
       request metadata and evals/ directory.
    2. Inference: Run each dataset item through the model via Batches API.
    3. Score: Apply the configured scorer(s) to each model output.
    4. Aggregate: Compute aggregate metrics (accuracy, precision, recall,
       custom domain metrics).
    5. Store: Persist eval results, per-item scores, and aggregate metrics
       as structured artifacts.
    """

    default_model = "claude-sonnet-4-6"
    mcp_profile = MCPProfile.NONE
    requires_verification = False
    requires_review = False

    async def execute(
        self, run_id: UUID, task_request: TaskRequest, worktree_path: str
    ) -> dict:
        """Execute an eval run task.

        Steps:
        1. Load eval dataset and scorer config from task_request.metadata.
        2. Submit inference batch via Message Batches API.
        3. Poll for batch completion.
        4. Score each result using configured scorer(s).
        5. Aggregate metrics across all results.
        6. Store eval results and metrics as artifacts.
        """
        raise NotImplementedError("Phase 1")

    async def get_plan_prompt(self, task_request: TaskRequest) -> str:
        """Generate planning prompt for eval run.

        Eval runs don't use a traditional planning phase — returns a prompt
        describing the eval dataset, model, and scoring methodology.
        """
        raise NotImplementedError("Phase 1")
