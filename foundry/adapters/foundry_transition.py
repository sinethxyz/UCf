"""Historical Foundry capabilities exposed through UCF transition interfaces.

Use FoundryTransitionRuntime for persisted evidence. The optional stores on
individual adapters retain compatibility with isolated, non-persisting callers.
"""

from __future__ import annotations

import hashlib
import json
from typing import TYPE_CHECKING, Literal
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
from foundry.environments.git_patch import capture_patch
from foundry.environments.git_worktree import GitWorktreeEnvironment
from foundry.git.branch import generate_branch_name
from foundry.runtime.transition_engine import StateConflictError, TransitionEngine
from foundry.storage.artifact_store import ArtifactStore, ArtifactType
from foundry.storage.transition_journal import ArtifactStoreTransitionJournal
from foundry.verification.policy import (
    MIGRATION_GUARD_ALLOWED_TASK_TYPES,
    match_protected_paths,
)

if TYPE_CHECKING:
    from foundry.git.worktree import WorktreeManager
    from foundry.orchestration.agent_runner import AgentRunner
    from foundry.verification.runner import VerificationRunner


def _task_from_transition(request: TransitionRequest) -> TaskRequest:
    raw = request.metadata.get("foundry_task")
    if not isinstance(raw, dict):
        raise ValueError("TransitionRequest metadata is missing foundry_task")
    task = TaskRequest.model_validate(raw)
    return task.model_copy(update={"metadata": {**task.metadata, "run_id": str(request.id)}})


async def _store_evidence(
    store: ArtifactStore, request: TransitionRequest, kind: ArtifactType,
    filename: str, data: str | bytes,
) -> EvidenceRef:
    result = await store.store(request.id, kind, data, filename=filename)
    return EvidenceRef(
        kind=kind.value,
        uri=f"artifact://{result['storage_path']}",
        checksum=result["checksum"],
        description=f"{filename} ({result['size_bytes']} bytes)",
    )


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
    """Expose planning, persisting the plan before implementation when configured."""

    def __init__(
        self, agent_runner: AgentRunner, artifact_store: ArtifactStore | None = None,
    ) -> None:
        self.agent_runner = agent_runner
        self.artifact_store = artifact_store

    async def plan(
        self, request: TransitionRequest, current_state: StateSnapshot, workspace: str,
    ) -> ActionProposal:
        task = _task_from_transition(request)
        plan = await self.agent_runner.run_planner(task, workspace)
        payload = {"plan": plan.model_dump(), "base_head": current_state.state.get("head")}
        if self.artifact_store is not None:
            ref = await _store_evidence(
                self.artifact_store, request, ArtifactType.PLAN, "plan.json",
                plan.model_dump_json(indent=2),
            )
            payload["plan_evidence"] = ref.model_dump()
        return ActionProposal(
            kind="foundry-plan",
            description=f"Apply {len(plan.steps)} planned steps to {request.environment}",
            payload=payload,
        )


class FoundryExecutorAdapter:
    """Persist the actual workspace patch, not just a provider's claimed diff."""

    def __init__(
        self, agent_runner: AgentRunner, artifact_store: ArtifactStore | None = None,
    ) -> None:
        self.agent_runner = agent_runner
        self.artifact_store = artifact_store

    async def execute(
        self, request: TransitionRequest, action: ActionProposal, workspace: str,
    ) -> list[EvidenceRef]:
        if action.kind != "foundry-plan":
            raise ValueError(f"Unsupported Foundry action kind: {action.kind}")
        task = _task_from_transition(request)
        plan = PlanArtifact.model_validate(action.payload["plan"])
        language = request.metadata.get("language", "go")
        if language not in {"go", "typescript"}:
            raise ValueError(f"Unsupported Foundry implementation language: {language}")
        claimed_diff = await self.agent_runner.run_implementer(
            plan=plan, task_request=task, worktree_path=workspace, language=language,
        )
        if self.artifact_store is None:
            checksum = hashlib.sha256(claimed_diff.encode("utf-8")).hexdigest()
            return [EvidenceRef(kind="git-diff", uri=f"sha256:{checksum}", checksum=checksum)]
        base = action.payload.get("base_head")
        if not isinstance(base, str) or not base:
            raise ValueError("Persistent Git execution requires an observed base HEAD")
        patch = await capture_patch(workspace, base)
        ref = await _store_evidence(
            self.artifact_store, request, ArtifactType.DIFF, "diff.patch", patch.data,
        )
        refs = [ref]
        if "plan_evidence" in action.payload:
            refs.insert(0, EvidenceRef.model_validate(action.payload["plan_evidence"]))
        return refs


async def _read_diff(workspace: str) -> str:
    patch = await capture_patch(workspace)
    return patch.data.decode("utf-8", errors="replace")


def _verification_evidence(check_type: str, passed: bool, output: str) -> EvidenceRef:
    status = "pass" if passed else "fail"
    return EvidenceRef(
        kind="verification", uri=f"verification://{check_type}/{status}",
        description=output[:500] or f"{check_type}: {status}",
    )


def _review_evidence(kind: str, review: ReviewVerdict) -> EvidenceRef:
    return EvidenceRef(
        kind=kind, uri=f"{kind}://{review.verdict.value}", description=review.summary,
    )


class FoundryVerifierAdapter:
    """Persist full verification and review results; preserve historical verdict policy."""

    def __init__(
        self, verification_runner: VerificationRunner, agent_runner: AgentRunner,
        artifact_store: ArtifactStore | None = None,
    ) -> None:
        self.verification_runner = verification_runner
        self.agent_runner = agent_runner
        self.artifact_store = artifact_store

    async def _review_ref(
        self, request: TransitionRequest, kind: str, review: ReviewVerdict,
    ) -> EvidenceRef:
        if self.artifact_store is None:
            return _review_evidence(kind, review)
        return await _store_evidence(
            self.artifact_store, request, ArtifactType.REVIEW,
            f"{kind}.json", review.model_dump_json(indent=2),
        )

    async def verify(
        self, request: TransitionRequest, before: StateSnapshot, after: StateSnapshot,
        action: ActionProposal, action_evidence: list[EvidenceRef], workspace: str,
    ) -> VerificationDecision:
        task = _task_from_transition(request)
        changed_files = [str(path) for path in after.state.get("changed_files", [])]
        evidence: list[EvidenceRef] = []
        if self.artifact_store is not None:
            if before.state.get("head") != after.state.get("head"):
                raise StateConflictError("Executor changed Git HEAD; workspace retained for review")
            patch = await capture_patch(workspace)
            refs = [ref for ref in action_evidence if ref.kind == ArtifactType.DIFF.value]
            if len(refs) != 1 or not refs[0].uri.startswith("artifact://"):
                raise StateConflictError("Missing retrievable execution patch")
            saved = await self.artifact_store.retrieve(refs[0].uri.removeprefix("artifact://"))
            if hashlib.sha256(saved).hexdigest() != refs[0].checksum or saved != patch.data:
                raise StateConflictError("Saved patch does not match the verification workspace")
            diff = patch.data.decode("utf-8", errors="replace")
        else:
            diff = await _read_diff(workspace)

        if task.verify:
            results, passed = await self.verification_runner.run_all(
                workspace, changed_files, run_id=request.id,
            )
            if self.artifact_store is None:
                evidence.extend(
                    _verification_evidence(result.check_type, result.passed, result.output)
                    for result in results
                )
            else:
                report = {"passed": passed, "checks": [
                    {"check_type": result.check_type, "passed": result.passed,
                     "output": result.output, "duration_ms": result.duration_ms}
                    for result in results
                ]}
                evidence.append(await _store_evidence(
                    self.artifact_store, request, ArtifactType.VERIFICATION,
                    "verification.json", json.dumps(report, indent=2),
                ))
            if not passed:
                failed = ", ".join(result.check_type for result in results if not result.passed)
                return VerificationDecision(
                    accepted=False, reason=f"Deterministic verification failed: {failed}",
                    evidence=evidence,
                )

        protected_files = match_protected_paths(changed_files)
        if protected_files:
            if task.task_type == TaskType.BUG_FIX:
                return VerificationDecision(
                    accepted=False, reason="Protected-path policy rejected bug-fix transition: "
                    + ", ".join(protected_files), evidence=evidence,
                )
            if task.task_type not in MIGRATION_GUARD_ALLOWED_TASK_TYPES:
                return VerificationDecision(
                    accepted=False,
                    reason=(
                        f"Task type {task.task_type.value} is not authorized for protected paths"
                    ),
                    evidence=evidence,
                )
            guard = await self.agent_runner.run_migration_guard(
                diff=diff, changed_files=protected_files,
            )
            evidence.append(await self._review_ref(request, "migration-guard", guard))
            if guard.verdict == ReviewVerdictType.REJECT:
                return VerificationDecision(
                    accepted=False, reason=f"Migration guard rejected transition: {guard.summary}",
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
        evidence.append(await self._review_ref(request, "review", review))
        reason = review.summary
        if review.verdict == ReviewVerdictType.REQUEST_CHANGES:
            reason = (
                "Independent review requested changes; historical Foundry policy "
                "treats this verdict as advisory."
            )
        return VerificationDecision(
            accepted=review.verdict != ReviewVerdictType.REJECT,
            reason=reason, evidence=evidence,
        )


class FoundryTransitionRuntime:
    """Run Foundry work with persisted plans, patches, reports and outcomes."""

    def __init__(
        self, *, worktree_manager: WorktreeManager, agent_runner: AgentRunner,
        verification_runner: VerificationRunner, artifact_store: ArtifactStore,
    ) -> None:
        self.engine = TransitionEngine(
            environment=GitWorktreeEnvironment(worktree_manager),
            observer=GitStateObserver(),
            planner=FoundryPlannerAdapter(agent_runner, artifact_store),
            executor=FoundryExecutorAdapter(agent_runner, artifact_store),
            verifier=FoundryVerifierAdapter(verification_runner, agent_runner, artifact_store),
            journal=ArtifactStoreTransitionJournal(artifact_store),
        )

    async def execute_task(
        self, task: TaskRequest, *, transition_id: UUID | None = None,
        language: Literal["go", "typescript"] = "go",
    ) -> TransitionOutcome:
        request = foundry_task_to_transition_request(
            task, transition_id=transition_id, language=language,
        )
        return await self.engine.execute(request)
