"""Historical Foundry capabilities exposed through UCF transition interfaces."""

from __future__ import annotations

import asyncio
import hashlib
from typing import Literal
from uuid import UUID, uuid4

from foundry.contracts.review_models import ReviewVerdict
from foundry.contracts.shared import ReviewVerdictType, TaskType
from foundry.contracts.task_types import PlanArtifact, TaskRequest
from foundry.contracts.transition_models import (
    ActionProposal,
    EvidenceRef,
    StateSnapshot,
    TransitionOutcome,
    TransitionRequest,
    VerificationDecision,
)
from foundry.environments.git_observer import GitStateObserver
from foundry.environments.git_worktree import GitWorktreeEnvironment
from foundry.git.branch import generate_branch_name
from foundry.git.worktree import WorktreeManager
from foundry.orchestration.agent_runner import AgentRunner
from foundry.runtime.transition_engine import TransitionEngine
from foundry.storage.artifact_store import ArtifactStore
from foundry.storage.transition_journal import ArtifactStoreTransitionJournal
from foundry.verification.policy import (
    MIGRATION_GUARD_ALLOWED_TASK_TYPES,
    match_protected_paths,
)
from foundry.verification.runner import VerificationRunner


def _task_from_transition(request: TransitionRequest) -> TaskRequest:
    raw = request.metadata.get("foundry_task")
    if not isinstance(raw, dict):
        raise ValueError("TransitionRequest metadata is missing foundry_task")
    return TaskRequest.model_validate(raw)


def foundry_task_to_transition_request(
    task: TaskRequest,
    *,
    transition_id: UUID | None = None,
    language: Literal["go", "typescript"] = "go",
) -> TransitionRequest:
    """Translate a historical Foundry task into the general UCF request shape."""
    return TransitionRequest(
        id=transition_id or uuid4(),
        environment=task.repo,
        objective=task.prompt,
        constraints={
            "task_type": task.task_type.value,
            "target_paths": list(task.target_paths),
            "verify": task.verify,
            "open_pr": task.open_pr,
        },
        metadata={
            "foundry_task": task.model_dump(),
            "base_ref": task.base_branch,
            "transition_name": generate_branch_name(task.task_type, task.title),
            "language": language,
        },
    )


class FoundryPlannerAdapter:
    """Expose AgentRunner planning through the UCF TransitionPlanner contract."""

    def __init__(self, agent_runner: AgentRunner) -> None:
        self.agent_runner = agent_runner

    async def plan(
        self,
        request: TransitionRequest,
        current_state: StateSnapshot,
        workspace: str,
    ) -> ActionProposal:
        task = _task_from_transition(request)
        plan = await self.agent_runner.run_planner(task, workspace)
        return ActionProposal(
            kind="foundry-plan",
            description=(
                f"Apply {len(plan.steps)} planned steps to {request.environment} "
                f"from {current_state.state.get('head', 'unknown state')}"
            ),
            payload={"plan": plan.model_dump()},
        )


class FoundryExecutorAdapter:
    """Expose AgentRunner implementation through the UCF ActionExecutor contract."""

    def __init__(self, agent_runner: AgentRunner) -> None:
        self.agent_runner = agent_runner

    async def execute(
        self,
        request: TransitionRequest,
        action: ActionProposal,
        workspace: str,
    ) -> list[EvidenceRef]:
        if action.kind != "foundry-plan":
            raise ValueError(f"Unsupported Foundry action kind: {action.kind}")

        task = _task_from_transition(request)
        plan = PlanArtifact.model_validate(action.payload["plan"])
        language = request.metadata.get("language", "go")
        if language not in {"go", "typescript"}:
            raise ValueError(f"Unsupported Foundry implementation language: {language}")

        diff = await self.agent_runner.run_implementer(
            plan=plan,
            task_request=task,
            worktree_path=workspace,
            language=language,
        )
        checksum = hashlib.sha256(diff.encode("utf-8")).hexdigest()
        return [
            EvidenceRef(
                kind="git-diff",
                uri=f"sha256:{checksum}",
                description=f"Implementation produced {len(diff.encode('utf-8'))} diff bytes",
                checksum=checksum,
            )
        ]


async def _read_diff(workspace: str) -> str:
    proc = await asyncio.create_subprocess_exec(
        "git",
        "diff",
        "HEAD",
        cwd=workspace,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    stdout, stderr = await proc.communicate()
    if proc.returncode != 0:
        raise RuntimeError(
            f"git diff failed in {workspace}: {stderr.decode(errors='replace').strip()}"
        )
    return stdout.decode(errors="replace")


def _verification_evidence(check_type: str, passed: bool, output: str) -> EvidenceRef:
    status = "pass" if passed else "fail"
    return EvidenceRef(
        kind="verification",
        uri=f"verification://{check_type}/{status}",
        description=output[:500] or f"{check_type}: {status}",
    )


def _review_evidence(kind: str, review: ReviewVerdict) -> EvidenceRef:
    return EvidenceRef(
        kind=kind,
        uri=f"{kind}://{review.verdict.value}",
        description=review.summary,
    )


class FoundryVerifierAdapter:
    """Apply Foundry verification and blind review to a UCF transition."""

    def __init__(
        self,
        verification_runner: VerificationRunner,
        agent_runner: AgentRunner,
    ) -> None:
        self.verification_runner = verification_runner
        self.agent_runner = agent_runner

    async def verify(
        self,
        request: TransitionRequest,
        before: StateSnapshot,
        after: StateSnapshot,
        action: ActionProposal,
        action_evidence: list[EvidenceRef],
        workspace: str,
    ) -> VerificationDecision:
        del before, action, action_evidence
        task = _task_from_transition(request)
        changed_files = [
            str(path) for path in after.state.get("changed_files", [])
        ]
        evidence: list[EvidenceRef] = []

        if task.verify:
            results, passed = await self.verification_runner.run_all(
                workspace,
                changed_files,
                run_id=request.id,
            )
            evidence.extend(
                _verification_evidence(result.check_type, result.passed, result.output)
                for result in results
            )
            if not passed:
                failed = ", ".join(
                    result.check_type for result in results if not result.passed
                )
                return VerificationDecision(
                    accepted=False,
                    reason=f"Deterministic verification failed: {failed}",
                    evidence=evidence,
                )

        diff = await _read_diff(workspace)
        protected_files = match_protected_paths(changed_files)
        if protected_files:
            if task.task_type == TaskType.BUG_FIX:
                return VerificationDecision(
                    accepted=False,
                    reason=(
                        "Protected-path policy rejected bug-fix transition: "
                        + ", ".join(protected_files)
                    ),
                    evidence=evidence,
                )

            if task.task_type not in MIGRATION_GUARD_ALLOWED_TASK_TYPES:
                return VerificationDecision(
                    accepted=False,
                    reason=(
                        f"Task type {task.task_type.value} is not authorized "
                        f"for protected paths: {', '.join(protected_files)}"
                    ),
                    evidence=evidence,
                )

            guard = await self.agent_runner.run_migration_guard(
                diff=diff,
                changed_files=protected_files,
            )
            evidence.append(_review_evidence("migration-guard", guard))
            if guard.verdict == ReviewVerdictType.REJECT:
                return VerificationDecision(
                    accepted=False,
                    reason=f"Migration guard rejected transition: {guard.summary}",
                    evidence=evidence,
                )

        changed_summary = ", ".join(changed_files[:10]) or "no files detected"
        if len(changed_files) > 10:
            changed_summary += f" (+{len(changed_files) - 10} more)"

        review = await self.agent_runner.run_reviewer(
            diff=diff,
            pr_title=f"[Foundry] {task.task_type.value}: {task.title}",
            pr_description=f"{task.prompt[:500]}\n\nChanged files: {changed_summary}",
            changed_files=changed_files,
        )
        evidence.append(_review_evidence("review", review))

        accepted = review.verdict != ReviewVerdictType.REJECT
        if review.verdict == ReviewVerdictType.REQUEST_CHANGES:
            reason = (
                "Independent review requested changes; historical Foundry policy "
                "treats this verdict as advisory."
            )
        else:
            reason = review.summary

        return VerificationDecision(
            accepted=accepted,
            reason=reason,
            evidence=evidence,
        )


class FoundryTransitionRuntime:
    """Run historical Foundry work through the provider-neutral UCF loop."""

    def __init__(
        self,
        *,
        worktree_manager: WorktreeManager,
        agent_runner: AgentRunner,
        verification_runner: VerificationRunner,
        artifact_store: ArtifactStore,
    ) -> None:
        self.engine = TransitionEngine(
            environment=GitWorktreeEnvironment(worktree_manager),
            observer=GitStateObserver(),
            planner=FoundryPlannerAdapter(agent_runner),
            executor=FoundryExecutorAdapter(agent_runner),
            verifier=FoundryVerifierAdapter(verification_runner, agent_runner),
            journal=ArtifactStoreTransitionJournal(artifact_store),
        )

    async def execute_task(
        self,
        task: TaskRequest,
        *,
        transition_id: UUID | None = None,
        language: Literal["go", "typescript"] = "go",
    ) -> TransitionOutcome:
        request = foundry_task_to_transition_request(
            task,
            transition_id=transition_id,
            language=language,
        )
        return await self.engine.execute(request)
