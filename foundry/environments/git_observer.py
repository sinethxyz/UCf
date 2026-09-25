"""Git-backed state observation for UCF execution environments."""

from __future__ import annotations

import asyncio
import hashlib
from datetime import UTC, datetime

from foundry.contracts.transition_models import EvidenceRef, StateSnapshot, TransitionRequest


async def _git(workspace: str, *args: str) -> str:
    proc = await asyncio.create_subprocess_exec(
        "git",
        *args,
        cwd=workspace,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    stdout, stderr = await proc.communicate()
    if proc.returncode != 0:
        raise RuntimeError(
            f"git {' '.join(args)} failed in {workspace}: "
            f"{stderr.decode(errors='replace').strip()}"
        )
    return stdout.decode(errors="replace")


def _changed_paths(status: str) -> list[str]:
    paths: list[str] = []
    for raw_line in status.splitlines():
        if len(raw_line) < 4:
            continue
        path = raw_line[3:]
        if " -> " in path:
            path = path.split(" -> ", 1)[1]
        paths.append(path)
    return paths


class GitStateObserver:
    """Represent the current Git workspace as explicit UCF state."""

    async def observe(self, request: TransitionRequest, workspace: str) -> StateSnapshot:
        head = (await _git(workspace, "rev-parse", "HEAD")).strip()
        status = await _git(workspace, "status", "--porcelain")
        diff = await _git(workspace, "diff", "HEAD")
        checksum = hashlib.sha256(diff.encode("utf-8")).hexdigest()
        changed_files = _changed_paths(status)

        return StateSnapshot(
            environment=request.environment,
            observed_at=datetime.now(UTC),
            state={
                "head": head,
                "dirty": bool(status.strip()),
                "changed_files": changed_files,
                "diff_checksum": checksum,
            },
            evidence=[
                EvidenceRef(
                    kind="git-head",
                    uri=f"git://commit/{head}",
                    description="Observed repository HEAD",
                ),
                EvidenceRef(
                    kind="git-diff",
                    uri=f"sha256:{checksum}",
                    description="Checksum of working tree diff against HEAD",
                    checksum=checksum,
                ),
            ],
        )
