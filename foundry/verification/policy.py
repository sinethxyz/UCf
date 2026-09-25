"""Shared verification policy for protected-path changes.

This policy originated in the historical Foundry RunEngine. It lives outside
that state machine so both the legacy lifecycle and the UCF transition adapter
apply the same safety boundary.
"""

from __future__ import annotations

import fnmatch

from foundry.contracts.shared import TaskType

PROTECTED_PATH_PREFIXES: tuple[str, ...] = ("migrations/", "auth/", "infra/")
PROTECTED_PATH_GLOBS: tuple[str, ...] = ("Dockerfile*", "docker-compose*")
PROTECTED_PATH_KEYWORDS: tuple[str, ...] = ("secret", "credential", "token")

MIGRATION_GUARD_ALLOWED_TASK_TYPES: set[TaskType] = {
    TaskType.ENDPOINT_BUILD,
    TaskType.REFACTOR,
    TaskType.MIGRATION_PLAN,
    TaskType.CANON_UPDATE,
}


def match_protected_paths(changed_files: list[str]) -> list[str]:
    """Return changed paths that require migration-guard scrutiny."""
    protected: list[str] = []
    for path in changed_files:
        if any(
            path.startswith(prefix) or f"/{prefix}" in path
            for prefix in PROTECTED_PATH_PREFIXES
        ):
            protected.append(path)
            continue

        basename = path.rsplit("/", 1)[-1] if "/" in path else path
        if any(fnmatch.fnmatch(basename, pattern) for pattern in PROTECTED_PATH_GLOBS):
            protected.append(path)
            continue

        lowered = path.lower()
        if any(keyword in lowered for keyword in PROTECTED_PATH_KEYWORDS):
            protected.append(path)

    return protected
