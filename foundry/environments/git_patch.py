"""Capture a replayable Git-visible patch without changing the user's index.

Includes tracked edits/deletions and non-ignored additions, including binaries.
Ignored files are outside this contract. This is not a sandbox for Git filters.
"""

from __future__ import annotations

import asyncio
import fnmatch
import os
import tempfile
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class GitPatch:
    """A patch relative to one pinned commit, with literal UTF-8 changed paths."""

    base_commit: str
    data: bytes
    changed_files: tuple[str, ...]


async def _git(
    workspace: str,
    *args: str,
    env: dict[str, str] | None = None,
    stdin: bytes | None = None,
) -> bytes:
    proc = await asyncio.create_subprocess_exec(
        "git", "--literal-pathspecs", *args,
        cwd=workspace,
        env=env,
        stdin=asyncio.subprocess.PIPE if stdin is not None else asyncio.subprocess.DEVNULL,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    try:
        stdout, _ = await asyncio.wait_for(proc.communicate(stdin), timeout=30)
    except (TimeoutError, asyncio.CancelledError):
        if proc.returncode is None:
            proc.kill()
        await proc.wait()
        raise
    if proc.returncode != 0:
        # Do not copy arbitrary Git/filter stderr into persisted exception messages.
        raise RuntimeError(f"Git evidence command failed: {args[0]} (exit {proc.returncode})")
    return stdout


def _sensitive_path(path: str) -> bool:
    lowered = path.lower()
    patterns = ("*.env", "*.env.*", "*.pem", "*.key", "*secrets*", "*credentials*",
                "*service-account*")
    return any(fnmatch.fnmatch(lowered, pattern) for pattern in patterns)


async def capture_patch(workspace: str, base_ref: str = "HEAD") -> GitPatch:
    """Capture a complete patch against base_ref, failing before secret-path reads.

    A temporary index stages only the candidate paths. The real index remains
    untouched. The caller must persist data before deleting the workspace.
    """
    base = (await _git(
        workspace, "rev-parse", "--verify", "--end-of-options", f"{base_ref}^{{commit}}"
    )).decode("ascii").strip()
    tracked = await _git(
        workspace, "diff", "--no-ext-diff", "--no-textconv", "--no-renames",
        "--name-only", "-z", base, "--",
    )
    untracked = await _git(workspace, "ls-files", "--others", "--exclude-standard", "-z")
    paths = sorted({part.decode("utf-8") for part in (tracked + untracked).split(b"\0") if part})
    if any(_sensitive_path(path) for path in paths):
        raise PermissionError("Refusing to capture a secret-shaped changed path")
    with tempfile.TemporaryDirectory(prefix="ucf-index-") as staging:
        env = os.environ.copy()
        env["GIT_INDEX_FILE"] = str(Path(staging) / "index")
        await _git(workspace, "read-tree", base, env=env)
        if paths:
            literals = b"".join(path.encode("utf-8") + b"\0" for path in paths)
            await _git(
                workspace, "add", "--all", "--pathspec-from-file=-", "--pathspec-file-nul",
                env=env, stdin=literals,
            )
        data = await _git(
            workspace, "diff", "--cached", "--binary", "--full-index", "--no-ext-diff",
            "--no-textconv", "--no-renames", base, "--", env=env,
        )
    return GitPatch(base_commit=base, data=data, changed_files=tuple(paths))
