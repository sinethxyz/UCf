"""Git worktree implementation of the UCF execution-environment contract."""

from __future__ import annotations

import asyncio
from uuid import UUID

from foundry.git.worktree import WorktreeManager


class GitWorktreeEnvironment:
    """Adapt the historical WorktreeManager to the general environment boundary."""

    def __init__(self, manager: WorktreeManager) -> None:
        self.manager = manager

    async def prepare(
        self,
        target: str,
        base_ref: str,
        transition_id: UUID,
        transition_name: str,
    ) -> str:
        # WorktreeManager currently creates from HEAD; base_ref remains explicit
        # in the interface so a future implementation can honor arbitrary refs.
        del base_ref
        return await self.manager.create(target, transition_name, transition_id)

    async def observe_changes(self, workspace: str) -> str:
        proc = await asyncio.create_subprocess_exec(
            "git",
            "diff",
            "HEAD",
            cwd=workspace,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, _ = await proc.communicate()
        return stdout.decode(errors="replace")

    async def cleanup(self, workspace: str) -> None:
        await self.manager.cleanup(workspace)
