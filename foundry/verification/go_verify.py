"""Go verification: build, test, vet, and lint."""

import subprocess
from pathlib import Path


async def verify_go(worktree_path: str) -> dict:
    """Run Go verification suite on a worktree.

    Executes in order: go build, go vet, go test.

    Args:
        worktree_path: Path to the worktree to verify.

    Returns:
        Dict with check results: {check_type: {passed, output, duration_ms}}.
    """
    raise NotImplementedError
