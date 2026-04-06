"""Task implementation: migration_plan.

Produces a migration plan artifact using Opus for high-scrutiny planning.
Does not execute the migration — produces plan artifact only.
"""


async def execute_migration_plan(task_request: dict, worktree_path: str) -> dict:
    """Execute a migration planning task."""
    raise NotImplementedError
