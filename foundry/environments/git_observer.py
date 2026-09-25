"""Observe Git-visible state using the same patch capture as durable evidence."""

from __future__ import annotations

import hashlib
from datetime import UTC, datetime

from foundry.contracts.transition_models import EvidenceRef, StateSnapshot, TransitionRequest
from foundry.environments.git_patch import capture_patch


class GitStateObserver:
    """Represent tracked and non-ignored untracked changes, not only tracked diffs."""

    async def observe(self, request: TransitionRequest, workspace: str) -> StateSnapshot:
        patch = await capture_patch(workspace)
        checksum = hashlib.sha256(patch.data).hexdigest()
        return StateSnapshot(
            environment=request.environment,
            observed_at=datetime.now(UTC),
            state={
                "head": patch.base_commit,
                "dirty": bool(patch.changed_files),
                "changed_files": list(patch.changed_files),
                "diff_checksum": checksum,
            },
            evidence=[
                EvidenceRef(
                    kind="git-head",
                    uri=f"git://commit/{patch.base_commit}",
                    description="Observed repository HEAD",
                ),
                EvidenceRef(
                    kind="git-diff",
                    uri=f"sha256:{checksum}",
                    description="Fingerprint; retrievable patch is stored by the executor",
                    checksum=checksum,
                ),
            ],
        )
