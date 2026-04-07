"""Task implementation: extraction_batch.

Runs batch extraction of startup signals into structured events/evidence
using the Message Batches API. Does not use the Agent SDK.
Validates all output against canon JSON schemas.
"""

from __future__ import annotations

from typing import TYPE_CHECKING
from uuid import UUID

from foundry.contracts.shared import MCPProfile, TaskType
from foundry.contracts.task_types import TaskRequest
from foundry.tasks import TaskExecutor, register_task

if TYPE_CHECKING:
    from foundry.orchestration.run_engine import RunEngine


@register_task(TaskType.EXTRACTION_BATCH)
class ExtractionBatchTask(TaskExecutor):
    """Extracts startup signals into structured events via batch processing.

    Unlike agentic tasks, this uses the Message Batches API for cost-efficient
    bulk extraction. No code changes are made — output is structured JSON
    validated against canon schemas.

    Workflow:
    1. Load: Read input signals/sources from the task request metadata.
    2. Prepare: Build extraction prompts for each signal, referencing
       the event taxonomy and evidence taxonomy from canon docs.
    3. Submit: Send batch of extraction requests via Message Batches API.
    4. Poll: Wait for batch completion.
    5. Validate: Validate each extraction result against canon/schemas/.
       Invalid results are flagged as failures.
    6. Store: Persist validated extraction results as artifacts.
    """

    default_model = "claude-sonnet-4-6"
    mcp_profile = MCPProfile.NONE
    requires_verification = False
    requires_review = False

    async def execute(
        self,
        run_engine: RunEngine,
        run_id: UUID,
        task_request: TaskRequest,
        worktree_path: str,
    ) -> dict:
        """Execute a batch extraction task.

        Steps:
        1. Load input signals from task_request.metadata.
        2. Build extraction prompts referencing canon event/evidence taxonomy.
        3. Submit batch via Message Batches API (claude_batch provider).
        4. Poll for batch completion.
        5. Validate each result against canon/schemas/.
        6. Store validated results as artifacts, flag invalid ones.
        """
        raise NotImplementedError("Phase 1")

    async def get_plan_prompt(self, task_request: TaskRequest) -> str:
        """Generate planning prompt for extraction batch.

        Extraction batches don't use a traditional planning phase —
        returns a prompt describing the extraction scope and schema targets.
        """
        raise NotImplementedError("Phase 1")
