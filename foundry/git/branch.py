"""Branch naming and validation utilities.

Convention: foundry/{task-type}-{slugified-title} (max 60 chars).
"""

import re

from foundry.contracts.shared import TaskType


def generate_branch_name(task_type: TaskType, title: str) -> str:
    """Generate a branch name following Foundry conventions.

    Args:
        task_type: The Foundry task type enum value.
        title: Short human-readable description of the change.

    Returns:
        Branch name like 'foundry/endpoint-build-company-timeline',
        truncated to a maximum of 60 characters.
    """
    slug = task_type.value.replace("_", "-")
    desc_slug = re.sub(r"[^a-z0-9]+", "-", title.lower()).strip("-")
    full = f"foundry/{slug}-{desc_slug}"
    if len(full) > 60:
        full = full[:60].rstrip("-")
    return full


def is_foundry_branch(branch_name: str) -> bool:
    """Check whether a branch name follows the Foundry naming convention.

    Args:
        branch_name: The branch name to validate.

    Returns:
        True if the branch starts with 'foundry/' prefix.
    """
    return branch_name.startswith("foundry/")
