"""Real Git/index/artifact tests; model and verifier behavior is deterministic."""

from __future__ import annotations

import hashlib
import subprocess
from dataclasses import dataclass
from pathlib import Path
from uuid import UUID, uuid4

import pytest

from foundry.adapters.foundry_transition import FoundryTransitionRuntime
from foundry.contracts.review_models import ReviewVerdict
from foundry.contracts.shared import Complexity, ReviewVerdictType, TaskType
from foundry.contracts.task_types import PlanArtifact, PlanStep, TaskRequest
from foundry.environments.git_patch import capture_patch
from foundry.git.worktree import WorktreeManager
from foundry.runtime.transition_engine import StateConflictError
from foundry.storage.artifact_store import ArtifactStore
from foundry.storage.transition_journal import ArtifactStoreTransitionJournal


def git(root: Path, *args: str, data: bytes | None = None) -> bytes:
    return subprocess.run(
        ["git", *args], cwd=root, input=data, check=True, capture_output=True,
    ).stdout


def repository(root: Path) -> Path:
    source = root / "source"
    source.mkdir()
    git(source, "init", "-b", "main")
    git(source, "config", "user.email", "ucf-test@example.invalid")
    git(source, "config", "user.name", "UCF Test")
    (source / "main.py").write_text("before\n", encoding="utf-8")
    (source / "remove.txt").write_text("remove this\n", encoding="utf-8")
    git(source, "add", ".")
    git(source, "commit", "-m", "Initial fixture")
    return source


@pytest.mark.parametrize("name", ["new file.txt", "new\nline.txt", ":(glob)*.txt", "--flag.txt"])
async def test_patch_replays_additions_deletions_and_binary_without_changing_index(
    tmp_path: Path, name: str,
) -> None:
    source = repository(tmp_path)
    (source / "main.py").write_text("after\n", encoding="utf-8")
    git(source, "add", "main.py")
    index_before = git(source, "diff", "--cached", "--binary")
    (source / "remove.txt").unlink()
    (source / name).write_text("added\n", encoding="utf-8")
    (source / "new.bin").write_bytes(b"\x00\xff\x00new")
    patch = await capture_patch(str(source))
    assert git(source, "diff", "--cached", "--binary") == index_before
    assert set(patch.changed_files) == {"main.py", "remove.txt", "new.bin", name}
    assert b"GIT binary patch" in patch.data
    git(source, "reset", "--hard")
    git(source, "clean", "-fd")
    git(source, "apply", "--binary", "-", data=patch.data)
    assert (source / "main.py").read_text(encoding="utf-8") == "after\n"
    assert not (source / "remove.txt").exists()
    assert (source / name).read_text(encoding="utf-8") == "added\n"
    assert (source / "new.bin").read_bytes() == b"\x00\xff\x00new"


async def test_secret_shaped_paths_are_rejected_before_staging(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    source = repository(tmp_path)
    (source / ".env").write_text("synthetic fixture, not a credential", encoding="utf-8")

    def unexpected_staging(*args: object, **kwargs: object) -> None:
        raise AssertionError("Sensitive-path rejection must happen before opening an index")

    monkeypatch.setattr(
        "foundry.environments.git_patch.tempfile.TemporaryDirectory", unexpected_staging,
    )
    with pytest.raises(PermissionError, match="secret-shaped"):
        await capture_patch(str(source))
    assert git(source, "diff", "--cached") == b""


async def test_clean_patch_and_invalid_refs_are_not_confused(tmp_path: Path) -> None:
    source = repository(tmp_path)
    clean = await capture_patch(str(source))
    assert clean.data == b"" and not clean.changed_files
    with pytest.raises(RuntimeError, match="Git evidence command failed"):
        await capture_patch(str(source), "missing-reference")


@dataclass
class Check:
    check_type: str = "fixture-check"
    passed: bool = True
    output: str = "Checked actual fixture files"
    duration_ms: int = 1


class DeterministicRunner:
    """Writes actual files but returns a deliberately false claimed diff."""

    def __init__(self, fail: str = "") -> None:
        self.fail = fail
        self.implementations = 0

    async def run_planner(self, task: TaskRequest, workspace: str) -> PlanArtifact:
        return PlanArtifact(
            task_id=UUID(task.metadata["run_id"]),
            steps=[PlanStep(file_path="main.py", action="modify", rationale="Fixture edit")],
            risks=[], open_questions=[], estimated_complexity=Complexity.SMALL,
        )

    async def run_implementer(
        self, plan: PlanArtifact, task_request: TaskRequest, worktree_path: str, language: str,
    ) -> str:
        self.implementations += 1
        workspace = Path(worktree_path)
        (workspace / "main.py").write_text("after\n", encoding="utf-8")
        (workspace / "new file.txt").write_text("added\n", encoding="utf-8")
        (workspace / "new.bin").write_bytes(b"\0\xfffixture")
        if self.fail == "execute":
            raise RuntimeError("Synthetic partial execution error")
        if self.fail == "commit":
            git(workspace, "add", ".")
            git(workspace, "commit", "-m", "Unexpected executor commit")
        return "This is not the actual Git diff"

    async def run_reviewer(
        self, diff: str, pr_title: str, pr_description: str, changed_files: list[str],
    ) -> ReviewVerdict:
        assert "new file.txt" in diff and "GIT binary patch" in diff
        assert "This is not the actual Git diff" not in diff
        if self.fail == "review":
            raise RuntimeError("Synthetic review failure")
        return ReviewVerdict(
            verdict=ReviewVerdictType.APPROVE, issues=[],
            summary="Inspected fixture patch", confidence=1.0,
        )


class DeterministicVerifier:
    def __init__(self, mutate: bool = False) -> None:
        self.mutate = mutate

    async def run_all(
        self, workspace: str, changed_files: list[str], *, run_id: UUID,
    ) -> tuple[list[Check], bool]:
        root = Path(workspace)
        assert (root / "main.py").read_text(encoding="utf-8") == "after\n"
        assert (root / "new.bin").read_bytes() == b"\0\xfffixture"
        if self.mutate:
            (root / "main.py").write_text("changed during verification\n", encoding="utf-8")
        return [Check()], True


def runtime(
    root: Path, runner: DeterministicRunner, mutate: bool = False,
) -> FoundryTransitionRuntime:
    source = repository(root)
    return FoundryTransitionRuntime(
        worktree_manager=WorktreeManager(str(source), str(root / "worktrees")),
        agent_runner=runner,
        verification_runner=DeterministicVerifier(mutate),
        artifact_store=ArtifactStore(str(root / "artifacts")),
    )


def task() -> TaskRequest:
    return TaskRequest(
        task_type=TaskType.BUG_FIX, repo="fixture", title="Evidence retention",
        prompt="Apply fixture edit", open_pr=False,
    )


async def test_full_adapter_evidence_is_retrievable_after_workspace_cleanup(tmp_path: Path) -> None:
    identity = uuid4()
    result = await runtime(tmp_path, DeterministicRunner()).execute_task(
        task(), transition_id=identity,
    )
    assert result.accepted
    assert not (tmp_path / "worktrees" / str(identity)).exists()
    journal = ArtifactStoreTransitionJournal(ArtifactStore(str(tmp_path / "artifacts")))
    reloaded = await journal.load(identity)
    assert result == reloaded
    refs = reloaded.observation.action_evidence + reloaded.observation.verification_evidence
    assert len(refs) == 4  # Plan, patch, full check output, full review.
    for ref in refs:
        assert ref.uri.startswith("artifact://")
        data = await journal.artifact_store.retrieve(ref.uri.removeprefix("artifact://"))
        assert hashlib.sha256(data).hexdigest() == ref.checksum
    patch = await journal.artifact_store.retrieve(f"runs/{identity}/diff.patch")
    assert b"This is not the actual Git diff" not in patch
    source = tmp_path / "source"
    assert (source / "main.py").read_text(encoding="utf-8") == "before\n"  # Not deployed.
    git(source, "apply", "--binary", "-", data=patch)
    assert (source / "main.py").read_text(encoding="utf-8") == "after\n"
    assert (source / "new.bin").read_bytes() == b"\0\xfffixture"


@pytest.mark.parametrize("failure,phase", [("execute", "execute"), ("review", "verify")])
async def test_real_partial_failure_keeps_workspace_and_records_failure(
    tmp_path: Path, failure: str, phase: str,
) -> None:
    identity = uuid4()
    subject = runtime(tmp_path, DeterministicRunner(failure))
    with pytest.raises(RuntimeError):
        await subject.execute_task(task(), transition_id=identity)
    record = await ArtifactStoreTransitionJournal(
        ArtifactStore(str(tmp_path / "artifacts"))
    ).load(identity)
    assert not record.accepted and record.metadata["phase"] == phase
    retained = Path(record.metadata["retained_workspace"])
    assert (retained / "main.py").read_text(encoding="utf-8") == "after\n"
    assert (tmp_path / "artifacts" / "runs" / str(identity) / "plan.json").exists()
    if failure == "review":
        assert (tmp_path / "artifacts" / "runs" / str(identity) / "diff.patch").exists()


async def test_mutating_verifier_cannot_leave_an_accepted_outcome(tmp_path: Path) -> None:
    identity = uuid4()
    with pytest.raises(StateConflictError, match="during verification"):
        await runtime(tmp_path, DeterministicRunner(), mutate=True).execute_task(
            task(), transition_id=identity,
        )
    record = await ArtifactStoreTransitionJournal(
        ArtifactStore(str(tmp_path / "artifacts"))
    ).load(identity)
    assert not record.accepted and record.metadata["phase"] == "observe_verified"
    assert Path(record.metadata["retained_workspace"]).exists()


async def test_executor_commit_requires_inspection_not_silent_cleanup(tmp_path: Path) -> None:
    identity = uuid4()
    with pytest.raises(StateConflictError, match="Git HEAD"):
        await runtime(tmp_path, DeterministicRunner("commit")).execute_task(
            task(), transition_id=identity,
        )
    record = await ArtifactStoreTransitionJournal(
        ArtifactStore(str(tmp_path / "artifacts"))
    ).load(identity)
    assert not record.accepted and Path(record.metadata["retained_workspace"]).exists()
    patch = await ArtifactStore(str(tmp_path / "artifacts")).retrieve(f"runs/{identity}/diff.patch")
    assert b"GIT binary patch" in patch  # Captured against the original observed HEAD.
