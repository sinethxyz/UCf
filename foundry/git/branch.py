"""Branch naming and management utilities.

Convention: foundry/{task-type}-{short-kebab-description}
"""


def make_branch_name(task_type: str, description: str) -> str:
    """Generate a branch name following Foundry conventions.

    Args:
        task_type: The task type (e.g., 'endpoint_build').
        description: Short description of the change.

    Returns:
        Branch name like 'foundry/endpoint-build-company-timeline'.
    """
    slug = task_type.replace("_", "-")
    desc_slug = description.lower().replace(" ", "-").replace("_", "-")
    # Truncate to keep branch names reasonable
    desc_slug = desc_slug[:50].rstrip("-")
    return f"foundry/{slug}-{desc_slug}"
