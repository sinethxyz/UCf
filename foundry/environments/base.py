"""Provider-neutral execution environment contracts.

An execution environment is the boundary in which a requested state transition
is prepared, performed, observed, and cleaned up. Git worktrees are the first
implementation, not the definition of the abstraction.
"""

from __future__ import annotations

from typing import Protocol
from uuid import UUID


class ExecutionEnvironment(Protocol):
    """Minimal environment lifecycle required by a controlled transition."""

    async def prepare(
        self,
        target: str,
        base_ref: str,
        transition_id: UUID,
        transition_name: str,
    ) -> str:
        """Prepare an isolated workspace and return its location/identifier."""
        ...

    async def observe_changes(self, workspace: str) -> str:
        """Return a durable representation of changes produced in the workspace."""
        ...

    async def cleanup(self, workspace: str) -> None:
        """Release resources associated with the workspace."""
        ...
