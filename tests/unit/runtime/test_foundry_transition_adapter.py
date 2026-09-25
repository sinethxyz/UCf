"""Integration tests for historical Foundry capabilities running through UCF."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from foundry.adapters.foundry_transition import (
    FoundryExecutorAdapter,
    FoundryPlannerAdapter,
    FoundryTransitionRuntime,
    FoundryVerifierAdapter,
    foundry_task_to_transition_request,
)
from foundry.contracts.review_models import ReviewVerdict
from foundry.contracts.shared import (
    Complexity,
    MCPProfile,
    ReviewVerdictType,
    TaskType,
)
from foundry.contracts.task_types import PlanArtifact, PlanStep, TaskRequest
from foundry.contracts.transition_models import (
    ActionProposal,
    StateSnapshot,
)
from foundry.git.worktree import WorktreeManager
from foundry.storage.artifact_store import ArtifactStore
from foundry.verification.go_verify import VerificationResult


def _task() -> TaskRequest:
    return TaskRequest(
        task_type=TaskType.BUG_FIX,
        repo="example-repo",
        base_branch="main",
        title="Fix greeting",
        prompt="Change the greeting from hello to hi",
        mcp_profile=MCPProfile.NONE,
    )


def _plan() -> PlanArtifact:
    return PlanArtifact(
        task_id=uuid4(),
        steps=[
            PlanStep(
                file_path="main.py",
                action="modify",
                rationale="Update the greeting",
            )
        ],
        risks=[],
        open_questions=[],
        estimated_complexity=Complexity.SMALL,
    )


def _state(*, dirty: bool, changed_files: list[str]) -> StateSnapshot:
    from datetime import UTC, datetime

    return StateSnapshot(
        environment="example-repo",
        observed_at=datetime.now(UTC),
        state={
            "head": "abc123",
            "dirty": dirty,
            "changed_files": changed_files,
            "diff_checksum": "0" * 64,
        },
    )


def _init_git_repo(path: Path) -> None:
    path.mkdir()
    subprocess.run(["git", "init"], cwd=path, check=True, capture_output=True)
    subprocess.run(
        ["git", "config", "user.email", "ucf-tests@example.invalid"],
        cwd=path,
        check=True,
    )
    subprocess.run(
        ["git", "config", "user.name", "UCF Tests"],
        cwd=path,
        check=True,
    )
    (path / "main.py").write_text('GREETING = "hello"\n', encoding="utf-8")
    subprocess.run(["git", "add", "main.py"], cwd=path, check=True)
    subprocess.run(
        ["git", "commit", "-m", "initial"],
        cwd=path,
        check=True,
        capture_output=True,
    )


def test_foundry_task_maps_to_general_transition_request() -> None:
    task = _task()
    transition_id = uuid4()

    request = foundry_task_to_transition_request(task, transition_id=transition_id)

    assert request.id == transition_id
    assert request.environment == "example-repo"
    assert request.objective == task.prompt
    assert request.constraints["task_type"] == "bug_fix"
    assert request.metadata["base_ref"] == "main"
    assert request.metadata["transition_name"].startswith("foundry/bug-fix-")
    restored = TaskRequest.model_validate(request.metadata["foundry_task"])
    assert restored == task


@pytest.mark.asyncio
async def test_planner_and_executor_wrap_existing_agent_runner() -> None:
    runner = MagicMock()
    runner.run_planner = AsyncMock(return_value=_plan())
    runner.run_implementer = AsyncMock(return_value="diff --git a/main.py b/main.py\n")

    request = foundry_task_to_transition_request(_task())
    planner = FoundryPlannerAdapter(runner)
    action = await planner.plan(request, _state(dirty=False, changed_files=[]), "/tmp/work")

    assert action.kind == "foundry-plan"
    assert len(action.payload["plan"]["steps"]) == 1

    executor = FoundryExecutorAdapter(runner)
    evidence = await executor.execute(request, action, "/tmp/work")

    assert evidence[0].kind == "git-diff"
    assert evidence[0].checksum is not None
    runner.run_implementer.assert_awaited_once()


@pytest.mark.asyncio
async def test_verifier_preserves_deterministic_and_blind_review_policy() -> None:
    verification_runner = MagicMock()
    verification_runner.run_all = AsyncMock(
        return_value=(
            [
                VerificationResult(
                    check_type="go_test",
                    passed=True,
                    output="ok",
                    duration_ms=4,
                )
            ],
            True,
        )
    )
    agent_runner = MagicMock()
    agent_runner.run_reviewer = AsyncMock(
        return_value=ReviewVerdict(
            verdict=ReviewVerdictType.APPROVE,
            issues=[],
            summary="Looks good",
            confidence=0.95,
        )
    )

    verifier = FoundryVerifierAdapter(verification_runner, agent_runner)
    request = foundry_task_to_transition_request(_task())

    with patch(
        "foundry.adapters.foundry_transition._read_diff",
        new=AsyncMock(return_value="diff --git a/main.go b/main.go\n"),
    ):
        decision = await verifier.verify(
            request=request,
            before=_state(dirty=False, changed_files=[]),
            after=_state(dirty=True, changed_files=["main.go"]),
            action=ActionProposal(
                kind="foundry-plan",
                description="test",
                payload={"plan": _plan().model_dump()},
            ),
            action_evidence=[],
            workspace="/tmp/work",
        )

    assert decision.accepted is True
    assert {item.kind for item in decision.evidence} == {"verification", "review"}
    agent_runner.run_reviewer.assert_awaited_once()


@pytest.mark.asyncio
async def test_bug_fix_protected_path_is_rejected_before_review() -> None:
    verification_runner = MagicMock()
    verification_runner.run_all = AsyncMock(
        return_value=(
            [
                VerificationResult(
                    check_type="none",
                    passed=True,
                    output="ok",
                    duration_ms=0,
                )
            ],
            True,
        )
    )
    agent_runner = MagicMock()
    agent_runner.run_reviewer = AsyncMock()

    verifier = FoundryVerifierAdapter(verification_runner, agent_runner)
    request = foundry_task_to_transition_request(_task())

    with patch(
        "foundry.adapters.foundry_transition._read_diff",
        new=AsyncMock(return_value="diff --git a/migrations/001.sql b/migrations/001.sql\n"),
    ):
        decision = await verifier.verify(
            request=request,
            before=_state(dirty=False, changed_files=[]),
            after=_state(dirty=True, changed_files=["migrations/001.sql"]),
            action=ActionProposal(
                kind="foundry-plan",
                description="test",
                payload={"plan": _plan().model_dump()},
            ),
            action_evidence=[],
            workspace="/tmp/work",
        )

    assert decision.accepted is False
    assert "Protected-path policy" in (decision.reason or "")
    agent_runner.run_reviewer.assert_not_awaited()


@pytest.mark.asyncio
async def test_real_git_foundry_path_runs_through_transition_engine(tmp_path: Path) -> None:
    source_repo = tmp_path / "source"
    _init_git_repo(source_repo)

    transition_id = uuid4()
    worktree_base = tmp_path / "worktrees"
    worktree_manager = WorktreeManager(
        repo_path=str(source_repo),
        worktree_base=str(worktree_base),
    )

    agent_runner = MagicMock()
    agent_runner.run_planner = AsyncMock(return_value=_plan())

    async def implement(**kwargs) -> str:
        workspace = Path(kwargs["worktree_path"])
        (workspace / "main.py").write_text('GREETING = "hi"\n', encoding="utf-8")
        proc = subprocess.run(
            ["git", "diff", "HEAD"],
            cwd=workspace,
            check=True,
            capture_output=True,
            text=True,
        )
        return proc.stdout

    agent_runner.run_implementer = AsyncMock(side_effect=implement)
    agent_runner.run_reviewer = AsyncMock(
        return_value=ReviewVerdict(
            verdict=ReviewVerdictType.APPROVE,
            issues=[],
            summary="Transition is valid",
            confidence=0.99,
        )
    )

    verification_runner = MagicMock()
    verification_runner.run_all = AsyncMock(
        return_value=(
            [
                VerificationResult(
                    check_type="python-test",
                    passed=True,
                    output="ok",
                    duration_ms=2,
                )
            ],
            True,
        )
    )

    artifact_store = ArtifactStore(base_path=str(tmp_path / "artifacts"))
    runtime = FoundryTransitionRuntime(
        worktree_manager=worktree_manager,
        agent_runner=agent_runner,
        verification_runner=verification_runner,
        artifact_store=artifact_store,
    )

    outcome = await runtime.execute_task(_task(), transition_id=transition_id)

    assert outcome.accepted is True
    assert outcome.before_state is not None
    assert outcome.after_state is not None
    assert outcome.before_state.state["dirty"] is False
    assert outcome.after_state.state["dirty"] is True
    assert outcome.after_state.state["changed_files"] == ["main.py"]
    assert not (worktree_base / str(transition_id)).exists()

    artifact = (
        tmp_path
        / "artifacts"
        / "runs"
        / str(transition_id)
        / "transition_outcome.json"
    )
    payload = json.loads(artifact.read_text(encoding="utf-8"))
    assert payload["accepted"] is True
    assert payload["after_state"]["state"]["changed_files"] == ["main.py"]
