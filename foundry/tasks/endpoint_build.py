"""Task implementation: endpoint_build.

Builds a new API endpoint in unicorn-app following existing patterns.
Uses the planner, backend-implementer, and reviewer subagents.
"""


async def execute_endpoint_build(task_request: dict, worktree_path: str) -> dict:
    """Execute an endpoint build task.

    Args:
        task_request: Validated TaskRequest dict.
        worktree_path: Path to the isolated worktree.

    Returns:
        Task result with artifacts.
    """
    raise NotImplementedError
