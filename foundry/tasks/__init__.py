"""Task type implementations — one module per task type.

Each task type is a class that orchestrates a specific kind of Foundry run
using the orchestration engine, providers, and verification modules.
"""

from abc import ABC, abstractmethod
from uuid import UUID

from foundry.contracts.shared import MCPProfile, TaskType
from foundry.contracts.task_types import TaskRequest


class TaskExecutor(ABC):
    """Base class for task type implementations.

    Every task executor defines class-level configuration that controls
    how the orchestration engine handles the run: which model to use,
    which MCP profile to attach, and whether verification and review
    are required.

    Subclasses must implement execute() and get_plan_prompt().
    """

    default_model: str
    mcp_profile: MCPProfile
    requires_verification: bool = True
    requires_review: bool = True

    @abstractmethod
    async def execute(
        self, run_id: UUID, task_request: TaskRequest, worktree_path: str
    ) -> dict:
        """Execute the task within the given worktree.

        Args:
            run_id: Unique identifier for this run.
            task_request: Validated task request with prompt, scope, etc.
            worktree_path: Filesystem path to the isolated git worktree.

        Returns:
            Dict containing task results and artifact references.
        """
        ...

    @abstractmethod
    async def get_plan_prompt(self, task_request: TaskRequest) -> str:
        """Generate the planning prompt for this task type.

        Args:
            task_request: The task request to build a plan prompt for.

        Returns:
            System prompt string for the planner subagent.
        """
        ...


TASK_REGISTRY: dict[TaskType, type[TaskExecutor]] = {}
"""Registry mapping task types to their executor classes.

Populated by each task module on import.
"""


def register_task(task_type: TaskType):
    """Decorator to register a TaskExecutor subclass in the registry."""

    def decorator(cls: type[TaskExecutor]) -> type[TaskExecutor]:
        TASK_REGISTRY[task_type] = cls
        return cls

    return decorator
