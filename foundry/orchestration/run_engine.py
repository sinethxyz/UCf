"""Core run lifecycle state machine.

Manages transitions: queued -> creating_worktree -> planning -> implementing
-> verifying -> verification_passed -> reviewing -> pr_opened -> completed.

Terminal failure states: plan_failed, verification_failed, review_failed,
cancelled, errored.
"""

from __future__ import annotations

import json
import logging
import os
import time
import traceback as tb_module
from typing import TYPE_CHECKING
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

import redis.asyncio as aioredis

from foundry.contracts.review_models import ReviewIssue, ReviewVerdict
from foundry.contracts.run_models import RunResponse
from foundry.contracts.shared import (
    ReviewSeverity,
    ReviewVerdictType,
    RunState,
    TaskType,
)
from foundry.contracts.task_types import PlanArtifact, TaskRequest
from foundry.db.models import RunEvent as RunEventORM
from foundry.db.queries import artifacts as artifact_queries
from foundry.db.queries import runs as run_queries
from foundry.storage.artifact_store import ArtifactType

if TYPE_CHECKING:
    from foundry.git.pr import PRCreator
    from foundry.git.worktree import WorktreeManager
    from foundry.orchestration.agent_runner import AgentRunner
    from foundry.storage.artifact_store import ArtifactStore
    from foundry.verification.runner import VerificationRunner

logger = logging.getLogger(__name__)


async def _build_run_response(session: AsyncSession, run_id: UUID) -> RunResponse:
    """Build a RunResponse from the ORM Run object.

    Handles coercion of string state to RunState enum and
    metadata column to plain dict, which strict-mode Pydantic
    does not do automatically via model_validate.
    """
    run = await run_queries.get_run(session, run_id)
    if run is None:
        raise ValueError(f"Run {run_id} not found")
    return RunResponse(
        id=run.id,
        task_type=run.task_type,
        repo=run.repo,
        base_branch=run.base_branch,
        title=run.title,
        state=RunState(run.state),
        branch_name=run.branch_name,
        pr_url=run.pr_url,
        error_message=run.error_message,
        created_at=run.created_at,
        updated_at=run.updated_at,
        completed_at=run.completed_at,
        metadata=dict(run.metadata_) if run.metadata_ else {},
    )


# ---------------------------------------------------------------------------
# State machine: maps each state to the set of states it may transition to.
# "cancelled" is reachable from any non-terminal state via cancel_run().
# Failure states (plan_failed, verification_failed, review_failed) can
# transition back to queued for retry.
# ---------------------------------------------------------------------------

VALID_TRANSITIONS: dict[RunState, set[RunState]] = {
    # Happy path
    RunState.QUEUED: {
        RunState.CREATING_WORKTREE,
        RunState.CANCELLED,
    },
    RunState.CREATING_WORKTREE: {
        RunState.PLANNING,
        RunState.ERRORED,
        RunState.CANCELLED,
    },
    RunState.PLANNING: {
        RunState.IMPLEMENTING,
        RunState.PLAN_FAILED,
        RunState.ERRORED,
        RunState.CANCELLED,
    },
    RunState.IMPLEMENTING: {
        RunState.VERIFYING,
        RunState.ERRORED,
        RunState.CANCELLED,
    },
    RunState.VERIFYING: {
        RunState.VERIFICATION_PASSED,
        RunState.VERIFICATION_FAILED,
        RunState.ERRORED,
        RunState.CANCELLED,
    },
    RunState.VERIFICATION_PASSED: {
        RunState.REVIEWING,
        RunState.ERRORED,
    },
    RunState.REVIEWING: {
        RunState.PR_OPENED,
        RunState.REVIEW_FAILED,
        RunState.ERRORED,
        RunState.CANCELLED,
    },
    RunState.PR_OPENED: {
        RunState.COMPLETED,
        RunState.ERRORED,
    },
    # Retry: failure states and errored can go back to queued
    RunState.PLAN_FAILED: {
        RunState.QUEUED,
    },
    RunState.VERIFICATION_FAILED: {
        RunState.QUEUED,
    },
    RunState.REVIEW_FAILED: {
        RunState.QUEUED,
    },
    RunState.ERRORED: {
        RunState.QUEUED,
    },
    # Terminal states — no outgoing transitions
    RunState.COMPLETED: set(),
    RunState.CANCELLED: set(),
}

# States that can be cancelled via cancel_run()
_CANCELLABLE_STATES: set[RunState] = {
    RunState.QUEUED,
    RunState.CREATING_WORKTREE,
    RunState.PLANNING,
    RunState.IMPLEMENTING,
    RunState.VERIFYING,
    RunState.REVIEWING,
}

# States that can be retried via retry_run()
_RETRYABLE_STATES: set[RunState] = {
    RunState.PLAN_FAILED,
    RunState.VERIFICATION_FAILED,
    RunState.REVIEW_FAILED,
    RunState.ERRORED,
}

QUEUE_KEY = "foundry:runs"

# ---------------------------------------------------------------------------
# Protected path patterns for migration guard.
# Any changed file matching these triggers the migration guard subagent.
# ---------------------------------------------------------------------------

PROTECTED_PATH_PREFIXES: tuple[str, ...] = ("migrations/", "auth/", "infra/")
PROTECTED_PATH_GLOBS: tuple[str, ...] = ("Dockerfile*", "docker-compose*")
PROTECTED_PATH_KEYWORDS: tuple[str, ...] = ("secret", "credential", "token")

# Task types allowed to modify protected paths (escalated to LLM review).
# All other task types that touch protected paths are auto-rejected.
MIGRATION_GUARD_ALLOWED_TASK_TYPES: set[TaskType] = {
    TaskType.ENDPOINT_BUILD,
    TaskType.REFACTOR,
    TaskType.MIGRATION_PLAN,
    TaskType.CANON_UPDATE,
}


def _match_protected_paths(changed_files: list[str]) -> list[str]:
    """Return the subset of changed_files that match protected path patterns.

    Matches against:
    - Prefix: migrations/, auth/, infra/
    - Glob: Dockerfile*, docker-compose*
    - Keyword: *secret*, *credential*, *token* (case-insensitive)

    Args:
        changed_files: List of file paths from the diff.

    Returns:
        List of file paths that match at least one protected pattern.
    """
    import fnmatch

    protected: list[str] = []
    for f in changed_files:
        # Check prefix matches (handle both "migrations/..." and "some/migrations/...")
        if any(f.startswith(prefix) or f"/{prefix}" in f for prefix in PROTECTED_PATH_PREFIXES):
            protected.append(f)
            continue

        # Check glob matches against the basename
        basename = f.rsplit("/", 1)[-1] if "/" in f else f
        if any(fnmatch.fnmatch(basename, g) for g in PROTECTED_PATH_GLOBS):
            protected.append(f)
            continue

        # Check keyword matches (case-insensitive) against the full path
        f_lower = f.lower()
        if any(kw in f_lower for kw in PROTECTED_PATH_KEYWORDS):
            protected.append(f)
            continue

    return protected


def _extract_changed_files(diff: str) -> list[str]:
    """Extract changed file paths from a git diff."""
    files = []
    for line in diff.split("\n"):
        if line.startswith("diff --git"):
            parts = line.split(" b/", 1)
            if len(parts) == 2:
                files.append(parts[1])
    return files


class RunEngine:
    """Core run lifecycle state machine.

    States: queued -> creating_worktree -> planning -> implementing -> verifying ->
            verification_passed -> reviewing -> pr_opened -> completed

    Failure states: plan_failed, verification_failed, review_failed, cancelled, errored
    """

    def __init__(
        self,
        session: AsyncSession,
        artifact_store: ArtifactStore,
        worktree_manager: WorktreeManager,
        agent_runner: AgentRunner,
        pr_creator: PRCreator,
        verification_runner: VerificationRunner,
        redis: aioredis.Redis | None = None,
    ) -> None:
        self.session = session
        self.artifact_store = artifact_store
        self.worktree_manager = worktree_manager
        self.agent_runner = agent_runner
        self.pr_creator = pr_creator
        self.verification_runner = verification_runner
        self.redis = redis

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def execute_run(self, task_request: TaskRequest) -> RunResponse:
        """Main entry point: execute a full run lifecycle for the given task.

        Orchestrates the complete run pipeline:
        1. Create worktree for isolated execution.
        2. Run planning to produce a structured implementation plan.
        3. Run implementation to execute the plan.
        4. Run verification (build, test, lint, schema).
        5. Run review (blind — reviewer does not see the plan).
        6. If review passed, open a PR with all collected artifacts.

        On unexpected error: transitions to ERRORED, stores error artifact,
        logs traceback. Always cleans up the worktree in a finally block.

        Args:
            task_request: The validated task request to execute.

        Returns:
            RunResponse with final state and metadata.
        """

        # 1. Create run record in QUEUED state
        run = await run_queries.create_run(self.session, task_request)
        run_id = run.id
        worktree_path: str | None = None
        logger.info("Created run %s for task: %s", run_id, task_request.title)

        # Add initial event — run queued
        event = RunEventORM(
            run_id=run_id,
            state=RunState.QUEUED.value,
            message="Run accepted and queued",
            metadata_={
                "task_type": task_request.task_type.value,
                "repo": task_request.repo,
                "base_branch": task_request.base_branch,
                "title": task_request.title,
            },
        )
        await run_queries.add_run_event(self.session, event)

        try:
            # 2. Create worktree (handles QUEUED → CREATING_WORKTREE → PLANNING)
            worktree_path = await self._create_worktree(run_id, task_request)

            # 3. Run planning (CREATING_WORKTREE → PLANNING, stores plan artifact)
            plan = await self._run_planning(run_id, task_request, worktree_path)
            if plan is None:
                return await _build_run_response(self.session, run_id)

            # 4. Run implementation (PLANNING → IMPLEMENTING)
            diff = await self._run_implementation(run_id, plan, task_request, worktree_path)
            if diff is None:
                return await _build_run_response(self.session, run_id)

            # 5. Run verification (IMPLEMENTING → VERIFYING → PASSED/FAILED)
            verification_passed = await self._run_verification(run_id, worktree_path, task_request)

            if not verification_passed:
                return await _build_run_response(self.session, run_id)

            # 6. Run review (migration guard + blind review)
            # _run_review handles: migration guard check → standard blind review.
            # Transitions: VERIFICATION_PASSED → REVIEWING → REVIEW_FAILED (on reject).
            review = await self._run_review(run_id, diff, task_request)

            if review.verdict == ReviewVerdictType.REJECT:
                # _run_review already transitioned to REVIEW_FAILED and set error_message
                return await _build_run_response(self.session, run_id)

            # 7. Open PR (handles REVIEWING → PR_OPENED → COMPLETED transitions)
            await self._open_pr(run_id, task_request, worktree_path, plan, review, diff)

            return await _build_run_response(self.session, run_id)

        except Exception as e:
            full_traceback = tb_module.format_exc()
            logger.exception("Run %s failed unexpectedly: %s", run_id, full_traceback)
            state_at_failure = "unknown"
            try:
                run = await run_queries.get_run(self.session, run_id)
                if run and run.state not in ("completed", "cancelled", "errored"):
                    state_at_failure = run.state
                    current_state = RunState(run.state)
                    # Abbreviate traceback for metadata (last 1500 chars)
                    abbreviated_tb = full_traceback[-1500:] if len(full_traceback) > 1500 else full_traceback
                    if RunState.ERRORED in VALID_TRANSITIONS.get(current_state, set()):
                        await self._transition(
                            run_id, current_state, RunState.ERRORED,
                            f"Run failed: {e}",
                            metadata={"traceback": abbreviated_tb, "phase": state_at_failure},
                        )
                    else:
                        await run_queries.update_run_state(
                            self.session, run_id, RunState.ERRORED.value, str(e),
                        )
                        await self._add_event(
                            run_id, RunState.ERRORED,
                            f"Run failed: {e}",
                            metadata={"traceback": abbreviated_tb, "phase": state_at_failure},
                        )
            except Exception:
                logger.exception("Failed to transition run %s to errored state", run_id)

            # Fetch last event for diagnostics
            last_event_msg = ""
            try:
                events = await run_queries.get_run_events(self.session, run_id)
                if events:
                    last_event_msg = events[-1].message
            except Exception:
                pass

            # Store error artifact with full diagnostic context
            try:
                error_data = json.dumps({
                    "error": str(e),
                    "traceback": full_traceback,
                    "phase": "execute_run",
                    "state_at_failure": state_at_failure,
                    "last_event": last_event_msg,
                })
                result = await self.artifact_store.store(run_id, ArtifactType.ERROR_LOG, error_data)
                await artifact_queries.store_artifact(
                    self.session, run_id, ArtifactType.ERROR_LOG.value,
                    result["storage_path"], result["size_bytes"], result["checksum"],
                )
            except Exception:
                logger.exception("Failed to store error artifact for run %s", run_id)

            return await _build_run_response(self.session, run_id)

        finally:
            # Always clean up the worktree
            if worktree_path:
                try:
                    await self.worktree_manager.cleanup(worktree_path)
                except Exception:
                    logger.warning("Failed to clean up worktree at %s for run %s", worktree_path, run_id)

    async def cancel_run(self, run_id: UUID) -> RunResponse:
        """Cancel an in-progress run.

        Transitions the run to CANCELLED state if the current state allows it.

        Args:
            run_id: ID of the run to cancel.

        Returns:
            RunResponse reflecting the cancelled state.

        Raises:
            ValueError: If the run is in a terminal state and cannot be cancelled.
        """
        run = await run_queries.get_run(self.session, run_id)
        if run is None:
            raise ValueError(f"Run {run_id} not found")

        current_state = RunState(run.state)
        if current_state not in _CANCELLABLE_STATES:
            raise ValueError(f"Run {run_id} in state {current_state.value} cannot be cancelled")

        await self._transition(
            run_id, current_state, RunState.CANCELLED,
            "Run cancelled by user",
            metadata={"previous_state": current_state.value},
        )

        # Clean up worktree if it exists
        if run.worktree_path:
            try:
                await self.worktree_manager.cleanup(run.worktree_path)
            except Exception:
                logger.warning("Failed to clean up worktree for cancelled run %s", run_id)

        return await _build_run_response(self.session, run_id)

    async def retry_run(self, run_id: UUID) -> RunResponse:
        """Retry a failed run by transitioning it back to QUEUED.

        Only runs in plan_failed, verification_failed, review_failed,
        or errored states can be retried. Cleans up any existing worktree
        and re-enqueues the run for worker processing.

        Args:
            run_id: ID of the run to retry.

        Returns:
            RunResponse reflecting the re-queued state.

        Raises:
            ValueError: If the run is not in a retryable state.
        """
        run = await run_queries.get_run(self.session, run_id)
        if run is None:
            raise ValueError(f"Run {run_id} not found")

        current_state = RunState(run.state)
        if current_state not in _RETRYABLE_STATES:
            raise ValueError(
                f"Run {run_id} in state {current_state.value} is not retryable. "
                f"Only runs in {', '.join(s.value for s in sorted(_RETRYABLE_STATES, key=lambda s: s.value))} can be retried."
            )

        await self._transition(
            run_id, current_state, RunState.QUEUED,
            "Run retried, re-queued",
            metadata={"previous_state": current_state.value},
        )

        # Clean up worktree if it exists and clear the path on the run row
        if run.worktree_path:
            try:
                await self.worktree_manager.cleanup(run.worktree_path)
            except Exception:
                logger.warning("Failed to clean up worktree for retried run %s", run_id)
            run.worktree_path = None
            await self.session.flush()

        # Re-enqueue for worker processing
        if self.redis is not None:
            payload = json.dumps({
                "task_type": run.task_type,
                "repo": run.repo,
                "base_branch": run.base_branch,
                "title": run.title,
                "prompt": run.prompt,
                "mcp_profile": run.mcp_profile,
                "_run_id": str(run_id),
            })
            await self.redis.lpush(QUEUE_KEY, payload)

        return await _build_run_response(self.session, run_id)

    # ------------------------------------------------------------------
    # State machine
    # ------------------------------------------------------------------

    async def _transition(
        self,
        run_id: UUID,
        from_state: RunState,
        to_state: RunState,
        message: str = "",
        metadata: dict | None = None,
        model_used: str | None = None,
        tokens_in: int | None = None,
        tokens_out: int | None = None,
        duration_ms: int | None = None,
    ) -> None:
        """Validate and execute a state transition.

        Checks that the transition is allowed by VALID_TRANSITIONS, updates
        the run record in the database, and emits a RunEvent with full metadata.

        Args:
            run_id: ID of the run being transitioned.
            from_state: The current state (must match DB).
            to_state: The target state.
            message: Human-readable message for the RunEvent.
            metadata: Optional metadata dict for the event.
            model_used: Model name if a model was involved.
            tokens_in: Input tokens consumed.
            tokens_out: Output tokens generated.
            duration_ms: Duration of the phase in milliseconds.

        Raises:
            ValueError: If the transition is not valid.
        """
        allowed = VALID_TRANSITIONS.get(from_state, set())
        if to_state not in allowed:
            raise ValueError(
                f"Invalid transition: {from_state.value} -> {to_state.value}"
            )

        await run_queries.update_run_state(
            self.session, run_id, to_state.value,
        )
        event = RunEventORM(
            run_id=run_id,
            state=to_state.value,
            message=message or f"Transitioned to {to_state.value}",
            metadata_=metadata or {},
            model_used=model_used,
            tokens_in=tokens_in,
            tokens_out=tokens_out,
            duration_ms=duration_ms,
        )
        await run_queries.add_run_event(self.session, event)
        logger.info("Run %s: %s -> %s (%s)", run_id, from_state.value, to_state.value, message)

    async def _add_event(
        self,
        run_id: UUID,
        state: RunState,
        message: str,
        metadata: dict | None = None,
        model_used: str | None = None,
        tokens_in: int | None = None,
        tokens_out: int | None = None,
        duration_ms: int | None = None,
    ) -> None:
        """Emit a run event without a state transition.

        Used for intra-phase milestones (e.g. individual verification checks,
        planning/implementation progress) where the run state itself does not
        change but the event should be recorded in the timeline.
        """
        event = RunEventORM(
            run_id=run_id,
            state=state.value,
            message=message,
            metadata_=metadata or {},
            model_used=model_used,
            tokens_in=tokens_in,
            tokens_out=tokens_out,
            duration_ms=duration_ms,
        )
        await run_queries.add_run_event(self.session, event)

    # ------------------------------------------------------------------
    # Phase implementations
    # ------------------------------------------------------------------

    async def _create_worktree(
        self,
        run_id: UUID,
        task_request: TaskRequest,
    ) -> str:
        """Create an isolated git worktree for the run.

        Handles the full QUEUED → CREATING_WORKTREE → PLANNING transition:
        1. Transition to CREATING_WORKTREE
        2. Derive branch name from task type and title
        3. Create the worktree via WorktreeManager
        4. Update the run record with worktree_path and branch_name
        5. Transition to PLANNING

        Args:
            run_id: ID of the current run.
            task_request: Task request containing repo and branch info.

        Returns:
            Absolute path to the created worktree directory.
        """
        from foundry.git.branch import generate_branch_name

        # 1. Transition QUEUED → CREATING_WORKTREE
        await self._transition(
            run_id, RunState.QUEUED, RunState.CREATING_WORKTREE, "Creating worktree",
        )

        # 2. Derive branch name
        branch_name = generate_branch_name(task_request.task_type, task_request.title)

        # 3. Create worktree
        t0 = time.monotonic()
        worktree_path = await self.worktree_manager.create(
            repo=task_request.repo,
            branch_name=branch_name,
            run_id=run_id,
        )
        wt_ms = int((time.monotonic() - t0) * 1000)

        # 4. Update run record with worktree info
        run = await run_queries.get_run(self.session, run_id)
        if run is not None:
            run.worktree_path = worktree_path
            run.branch_name = branch_name
            await self.session.flush()

        # 5. Log worktree creation event
        await self._add_event(
            run_id, RunState.CREATING_WORKTREE,
            f"Worktree created at {worktree_path}, branch {branch_name}",
            metadata={"path": worktree_path, "branch": branch_name},
            duration_ms=wt_ms,
        )

        return worktree_path

    async def _run_planning(
        self,
        run_id: UUID,
        task_request: TaskRequest,
        worktree_path: str,
    ) -> PlanArtifact | None:
        """Run the planner subagent to produce a structured implementation plan.

        Handles the full planning phase:
        1. Transition to PLANNING state.
        2. Call agent_runner.run_planner() with the task request.
        3. Serialize plan to JSON, store via artifact_store as plan.json.
        4. Register artifact metadata in the database.
        5. On failure: transition to PLAN_FAILED and store error_log artifact.

        Args:
            run_id: ID of the current run.
            task_request: Task request with prompt and context.
            worktree_path: Path to the worktree for repo exploration.

        Returns:
            PlanArtifact with ordered implementation steps, or None if
            planning failed (run is transitioned to PLAN_FAILED).
        """
        # Determine model for planning
        from foundry.orchestration.model_router import resolve_model
        plan_model = resolve_model(task_request.task_type, "planner", task_request.model_override)

        # Transition to PLANNING
        await self._transition(
            run_id, RunState.CREATING_WORKTREE, RunState.PLANNING, "Starting planning",
        )

        # Log planning started
        await self._add_event(
            run_id, RunState.PLANNING,
            "Planning started",
            metadata={"model": plan_model},
            model_used=plan_model,
        )

        try:
            t0 = time.monotonic()
            plan = await self.agent_runner.run_planner(task_request, worktree_path)
            plan_ms = int((time.monotonic() - t0) * 1000)

            # Serialize plan to JSON, store as plan.json
            plan_json = plan.model_dump_json(indent=2)
            result = await self.artifact_store.store(
                run_id, ArtifactType.PLAN, plan_json, filename="plan.json",
            )
            await artifact_queries.store_artifact(
                self.session, run_id, ArtifactType.PLAN.value,
                result["storage_path"], result["size_bytes"], result["checksum"],
            )

            # Log planning completed
            step_count = len(plan.steps)
            await self._add_event(
                run_id, RunState.PLANNING,
                f"Plan generated with {step_count} steps",
                metadata={"artifact": "plan.json", "step_count": step_count},
                model_used=plan_model,
                duration_ms=plan_ms,
            )

            return plan
        except Exception as e:
            logger.error("Planning failed for run %s: %s", run_id, e)

            # Log planning failed
            await self._add_event(
                run_id, RunState.PLANNING,
                f"Planning failed: {e}",
                metadata={"error": str(e)},
                model_used=plan_model,
            )

            # Store error_log artifact
            error_data = json.dumps({"error": str(e), "phase": "planning"})
            try:
                result = await self.artifact_store.store(
                    run_id, ArtifactType.ERROR_LOG, error_data,
                )
                await artifact_queries.store_artifact(
                    self.session, run_id, ArtifactType.ERROR_LOG.value,
                    result["storage_path"], result["size_bytes"], result["checksum"],
                )
            except Exception:
                logger.exception("Failed to store error log for run %s", run_id)

            # Transition to PLAN_FAILED
            await self._transition(
                run_id, RunState.PLANNING, RunState.PLAN_FAILED,
                f"Planning failed: {e}",
                metadata={"error": str(e)},
            )
            return None

    async def _run_implementation(
        self,
        run_id: UUID,
        plan: PlanArtifact,
        task_request: TaskRequest,
        worktree_path: str,
    ) -> str | None:
        """Run the implementer subagent to execute the plan.

        Handles the full implementation phase:
        1. Transition to IMPLEMENTING state.
        2. Set environment variables for hooks (RUN_ID, RUN_STATE, etc.).
        3. Call agent_runner.run_implementer() with the plan.
        4. Clean up environment variables after execution.
        5. Store diff as artifact (diff.patch).
        6. On failure: store error_log artifact, transition to ERRORED.
        7. On success: return diff (verification handles the next transition).

        Args:
            run_id: ID of the current run.
            plan: The validated implementation plan.
            task_request: Original task request.
            worktree_path: Path to the worktree where edits are made.

        Returns:
            The git diff of all changes made, or None if implementation failed
            (run is transitioned to ERRORED).
        """
        # Determine model and language for implementation
        from foundry.orchestration.model_router import resolve_model
        impl_model = resolve_model(task_request.task_type, "implementer", task_request.model_override)
        language = "go"  # Go-only for Phase 1

        # Transition to IMPLEMENTING
        await self._transition(
            run_id, RunState.PLANNING, RunState.IMPLEMENTING, "Starting implementation",
        )

        # Log implementation started
        await self._add_event(
            run_id, RunState.IMPLEMENTING,
            "Implementation started",
            metadata={"model": impl_model, "language": language},
            model_used=impl_model,
        )

        # Set environment variables for hooks
        env_vars = {
            "RUN_ID": str(run_id),
            "RUN_STATE": RunState.IMPLEMENTING.value,
            "RUN_TASK_TYPE": task_request.task_type.value,
            "ARTIFACT_DIR": str(self.artifact_store.base_path / "runs" / str(run_id)),
            "WORKTREE_PATH": worktree_path,
        }
        old_env: dict[str, str | None] = {}
        for key, value in env_vars.items():
            old_env[key] = os.environ.get(key)
            os.environ[key] = value

        try:
            t0 = time.monotonic()
            diff = await self.agent_runner.run_implementer(
                plan=plan,
                task_request=task_request,
                worktree_path=worktree_path,
                language=language,
            )
            impl_ms = int((time.monotonic() - t0) * 1000)

            # Store diff artifact
            changed_files = _extract_changed_files(diff) if diff.strip() else []
            if diff.strip():
                result = await self.artifact_store.store(
                    run_id, ArtifactType.DIFF, diff,
                )
                await artifact_queries.store_artifact(
                    self.session, run_id, ArtifactType.DIFF.value,
                    result["storage_path"], result["size_bytes"], result["checksum"],
                )

            # Log implementation completed
            file_count = len(changed_files)
            await self._add_event(
                run_id, RunState.IMPLEMENTING,
                f"Implementation completed, {file_count} files changed",
                metadata={"artifact": "diff.patch", "files_changed": file_count},
                model_used=impl_model,
                duration_ms=impl_ms,
            )

            return diff

        except Exception as e:
            logger.error("Implementation failed for run %s: %s", run_id, e)

            # Store error_log artifact
            error_data = json.dumps({"error": str(e), "phase": "implementation"})
            try:
                result = await self.artifact_store.store(
                    run_id, ArtifactType.ERROR_LOG, error_data,
                )
                await artifact_queries.store_artifact(
                    self.session, run_id, ArtifactType.ERROR_LOG.value,
                    result["storage_path"], result["size_bytes"], result["checksum"],
                )
            except Exception:
                logger.exception("Failed to store error log for run %s", run_id)

            # Transition to ERRORED
            await self._transition(
                run_id, RunState.IMPLEMENTING, RunState.ERRORED,
                f"Implementation failed: {e}",
                metadata={"error": str(e)},
            )
            return None

        finally:
            # Restore original environment
            for key, original in old_env.items():
                if original is None:
                    os.environ.pop(key, None)
                else:
                    os.environ[key] = original

    async def _run_verification(
        self,
        run_id: UUID,
        worktree_path: str,
        task_request: TaskRequest,
    ) -> bool:
        """Run deterministic verification (build, test, lint, schema).

        Manages the full verification lifecycle:
        1. Transition IMPLEMENTING → VERIFYING.
        2. Extract changed files from stored diff artifact.
        3. Call verification_runner.run_all().
        4. Serialize results to JSON and store as verification.json artifact.
        5. Register artifact in DB with size and checksum.
        6. Persist each VerificationResult as a verification_results DB row
           (delegated to verification_runner when session is provided).
        7. On failure: set error_message on run, transition to VERIFICATION_FAILED.
        8. On success: transition to VERIFICATION_PASSED.

        Args:
            run_id: ID of the current run.
            worktree_path: Path to the worktree to verify.
            task_request: Task request for context on what to verify.

        Returns:
            True if all verification steps pass, False otherwise.
        """
        import asyncio

        # Determine check types expected
        check_types = ["go_build", "go_vet", "go_test"]

        # 1. Transition to VERIFYING
        await self._transition(
            run_id, RunState.IMPLEMENTING, RunState.VERIFYING,
            "Starting verification",
        )

        # Log verification started
        await self._add_event(
            run_id, RunState.VERIFYING,
            "Verification started",
            metadata={"checks": check_types},
        )

        # 2. Extract changed files from stored diff artifact
        changed_files: list[str] = []
        try:
            artifact_entries = await self.artifact_store.list_artifacts(run_id)
            for entry in artifact_entries:
                if "diff" in entry["filename"]:
                    storage_path = f"runs/{run_id}/{entry['filename']}"
                    raw = await self.artifact_store.retrieve(storage_path)
                    diff_text = raw.decode("utf-8", errors="replace")
                    for line in diff_text.split("\n"):
                        if line.startswith("diff --git"):
                            parts = line.split(" b/", 1)
                            if len(parts) == 2:
                                changed_files.append(parts[1])
                    break
        except Exception:
            logger.warning(
                "Could not parse diff artifact for run %s, falling back to git",
                run_id,
            )

        # Fallback to git if diff artifact was unavailable or empty
        if not changed_files:
            proc = await asyncio.create_subprocess_exec(
                "git", "diff", "--name-only", "HEAD",
                cwd=worktree_path,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, _ = await proc.communicate()
            changed_files = [f for f in stdout.decode().strip().split("\n") if f]

            proc2 = await asyncio.create_subprocess_exec(
                "git", "status", "--porcelain",
                cwd=worktree_path,
                stdout=asyncio.subprocess.PIPE,
            )
            stdout2, _ = await proc2.communicate()
            for line in stdout2.decode().strip().split("\n"):
                if line.startswith("?? "):
                    changed_files.append(line[3:])

        # 3. Run verification checks
        results, passed = await self.verification_runner.run_all(
            worktree_path,
            changed_files,
            run_id=run_id,
            session=self.session,
        )

        # 4. Log individual check results
        for r in results:
            status = "passed" if r.passed else "failed"
            output_snippet = r.output[:500] if r.output else ""
            await self._add_event(
                run_id, RunState.VERIFYING,
                f"{r.check_type} {status}",
                metadata={
                    "check_type": r.check_type,
                    "passed": r.passed,
                    "duration_ms": r.duration_ms,
                    "output_snippet": output_snippet,
                },
                duration_ms=r.duration_ms,
            )

        # 5. Serialize and store verification.json artifact
        verification_data = json.dumps(
            [
                {
                    "check_type": r.check_type,
                    "passed": r.passed,
                    "output": r.output[:5000],
                    "duration_ms": r.duration_ms,
                }
                for r in results
            ],
            indent=2,
        )
        result = await self.artifact_store.store(
            run_id, ArtifactType.VERIFICATION, verification_data,
            filename="verification.json",
        )
        await artifact_queries.store_artifact(
            self.session, run_id, ArtifactType.VERIFICATION.value,
            result["storage_path"], result["size_bytes"], result["checksum"],
        )

        # 6. Handle pass/fail with state transitions and run events
        if not passed:
            failed_checks = [r.check_type for r in results if not r.passed]
            error_summary = (
                f"Verification failed: {', '.join(failed_checks)} did not pass"
            )

            # Log verification overall result
            await self._add_event(
                run_id, RunState.VERIFYING,
                "Verification failed",
                metadata={"failed_checks": failed_checks},
            )

            # Attach error summary to run row
            run = await run_queries.get_run(self.session, run_id)
            if run is not None:
                run.error_message = error_summary
                await self.session.flush()

            # Transition to VERIFICATION_FAILED with descriptive message
            await self._transition(
                run_id, RunState.VERIFYING, RunState.VERIFICATION_FAILED,
                error_summary,
            )
            return False

        # All checks passed — log overall result
        await self._add_event(
            run_id, RunState.VERIFYING,
            "Verification passed",
            metadata={"checks_passed": [r.check_type for r in results]},
        )
        await self._transition(
            run_id, RunState.VERIFYING, RunState.VERIFICATION_PASSED,
            "All verification checks passed",
        )
        return True

    async def _run_review(
        self,
        run_id: UUID,
        diff: str,
        task_request: TaskRequest,
    ) -> ReviewVerdict:
        """Run review: migration guard (if needed) then standard blind review.

        Handles the full review lifecycle:
        1. Transition to REVIEWING state.
        2. Extract changed files from the diff.
        3. Run migration guard check BEFORE standard review.
           - If guard REJECT: store artifact, transition to REVIEW_FAILED, return.
           - If guard APPROVE/REQUEST_CHANGES: store artifact, continue.
           - If guard None (no protected paths): skip.
        4. Run standard blind review (reviewer does NOT see the plan).
        5. Store review.json artifact and handle verdict.

        Args:
            run_id: ID of the current run.
            diff: The git diff to review.
            task_request: Task request for context (title, type).

        Returns:
            ReviewVerdict with verdict, issues, and summary.
        """
        from foundry.orchestration.model_router import resolve_model

        review_model = resolve_model(task_request.task_type, "reviewer", task_request.model_override)

        # 1. Transition to REVIEWING
        await self._transition(
            run_id, RunState.VERIFICATION_PASSED, RunState.REVIEWING,
            "Starting review phase",
        )

        # 2. Extract changed files
        changed_files = _extract_changed_files(diff)

        # 3. Migration guard check — BEFORE standard blind review
        guard_verdict = await self._check_migration_guard(
            run_id, diff, changed_files, task_request,
        )

        if guard_verdict is not None:
            # Store migration_guard_review.json artifact
            guard_json = guard_verdict.model_dump_json(indent=2)
            guard_result = await self.artifact_store.store(
                run_id, ArtifactType.REVIEW, guard_json,
                filename="migration_guard_review.json",
            )
            await artifact_queries.store_artifact(
                self.session, run_id, ArtifactType.REVIEW.value,
                guard_result["storage_path"], guard_result["size_bytes"],
                guard_result["checksum"],
            )

            if guard_verdict.verdict == ReviewVerdictType.REJECT:
                # Migration guard rejects — fail review, skip standard review
                run = await run_queries.get_run(self.session, run_id)
                if run is not None:
                    run.error_message = f"Migration guard rejected: {guard_verdict.summary}"
                    await self.session.flush()

                await self._transition(
                    run_id, RunState.REVIEWING, RunState.REVIEW_FAILED,
                    f"Migration guard rejected: {guard_verdict.summary}",
                    metadata={
                        "verdict": guard_verdict.verdict.value,
                        "summary": guard_verdict.summary,
                    },
                )
                return guard_verdict

            # APPROVE or REQUEST_CHANGES — log and continue to standard review
            await self._add_event(
                run_id, RunState.REVIEWING,
                f"Migration guard verdict: {guard_verdict.verdict.value} "
                f"— proceeding to standard review",
                metadata={
                    "artifact": "migration_guard_review.json",
                    "verdict": guard_verdict.verdict.value,
                    "issue_count": len(guard_verdict.issues),
                },
            )

        # 4. Standard blind review
        await self._add_event(
            run_id, RunState.REVIEWING,
            "Blind review started",
            metadata={"model": review_model},
            model_used=review_model,
        )

        # Generate PR title and description
        pr_title = f"[Foundry] {task_request.task_type.value}: {task_request.title}"

        changes_summary = ", ".join(changed_files[:10]) if changed_files else "no files detected"
        if len(changed_files) > 10:
            changes_summary += f" (+{len(changed_files) - 10} more)"
        pr_description = (
            f"{task_request.prompt[:500]}\n\n"
            f"Changed files: {changes_summary}"
        )

        # Call reviewer (blind — no plan)
        t0 = time.monotonic()
        review = await self.agent_runner.run_reviewer(
            diff=diff,
            pr_title=pr_title,
            pr_description=pr_description,
            changed_files=changed_files,
        )
        review_ms = int((time.monotonic() - t0) * 1000)

        # 5. Serialize and store review.json artifact
        review_json = review.model_dump_json(indent=2)
        result = await self.artifact_store.store(
            run_id, ArtifactType.REVIEW, review_json,
            filename="review.json",
        )
        await artifact_queries.store_artifact(
            self.session, run_id, ArtifactType.REVIEW.value,
            result["storage_path"], result["size_bytes"], result["checksum"],
        )

        # 6. Log review completed
        issue_count = len(review.issues)
        await self._add_event(
            run_id, RunState.REVIEWING,
            f"Review verdict: {review.verdict.value}, {issue_count} issues",
            metadata={
                "artifact": "review.json",
                "verdict": review.verdict.value,
                "issue_count": issue_count,
                "confidence": review.confidence,
            },
            model_used=review_model,
            duration_ms=review_ms,
        )

        # 7. Handle verdict
        if review.verdict == ReviewVerdictType.REJECT:
            run = await run_queries.get_run(self.session, run_id)
            if run is not None:
                run.error_message = f"Review rejected: {review.summary}"
                await self.session.flush()

            await self._transition(
                run_id, RunState.REVIEWING, RunState.REVIEW_FAILED,
                f"Review rejected: {review.summary}",
                metadata={"verdict": review.verdict.value, "summary": review.summary},
            )

        elif review.verdict == ReviewVerdictType.REQUEST_CHANGES:
            await self._add_event(
                run_id, RunState.REVIEWING,
                f"Review requested changes ({issue_count} issues). "
                f"PR will include requested changes as comments.",
                metadata={"verdict": review.verdict.value, "issue_count": issue_count},
            )

        return review

    async def _check_migration_guard(
        self,
        run_id: UUID,
        diff: str,
        changed_files: list[str],
        task_request: TaskRequest,
    ) -> ReviewVerdict | None:
        """Check if the diff touches protected paths and run migration guard.

        Scans changed_files against protected path patterns. If no protected
        paths are touched, returns None. Otherwise:

        - For bug_fix tasks: returns an automatic REJECT without calling the LLM.
        - For allowed task types (endpoint_build, refactor, migration_plan,
          canon_update): escalates to the migration guard LLM subagent.
        - For all other task types: returns an automatic REJECT (unauthorized).

        Args:
            run_id: ID of the current run.
            diff: The git diff to review.
            changed_files: List of changed file paths from the diff.
            task_request: The task request for task type routing.

        Returns:
            ReviewVerdict if migration guard was triggered, None if no
            protected paths were touched.
        """
        protected_files = _match_protected_paths(changed_files)

        if not protected_files:
            return None

        # Log the trigger event
        await self._add_event(
            run_id, RunState.REVIEWING,
            f"Migration guard triggered: {protected_files}",
            metadata={"protected_files": protected_files},
        )

        logger.warning(
            "Run %s touches protected paths %s — task type: %s",
            run_id, protected_files, task_request.task_type.value,
        )

        # bug_fix tasks must not modify protected paths — auto-reject
        if task_request.task_type == TaskType.BUG_FIX:
            files_str = ", ".join(protected_files)
            return ReviewVerdict(
                verdict=ReviewVerdictType.REJECT,
                issues=[
                    ReviewIssue(
                        severity=ReviewSeverity.CRITICAL,
                        file_path=protected_files[0],
                        description=(
                            f"Bug fix tasks must not modify protected paths. "
                            f"Files: {files_str}"
                        ),
                    ),
                ],
                summary=f"Bug fix tasks must not modify protected paths. Files: {files_str}",
                confidence=1.0,
            )

        # Allowed task types get LLM-powered migration guard review
        if task_request.task_type in MIGRATION_GUARD_ALLOWED_TASK_TYPES:
            return await self.agent_runner.run_migration_guard(
                diff=diff,
                changed_files=protected_files,
            )

        # All other task types are not authorized — auto-reject
        files_str = ", ".join(protected_files)
        return ReviewVerdict(
            verdict=ReviewVerdictType.REJECT,
            issues=[
                ReviewIssue(
                    severity=ReviewSeverity.CRITICAL,
                    file_path=protected_files[0],
                    description=(
                        f"Task type {task_request.task_type.value} is not authorized "
                        f"to modify protected paths. Files: {files_str}"
                    ),
                ),
            ],
            summary=(
                f"Task type {task_request.task_type.value} is not authorized "
                f"to modify protected paths. Files: {files_str}"
            ),
            confidence=1.0,
        )

    async def _open_pr(
        self,
        run_id: UUID,
        task_request: TaskRequest,
        worktree_path: str,
        plan: PlanArtifact,
        review: ReviewVerdict,
        diff: str,
    ) -> str:
        """Open a pull request with the changes from the worktree.

        Handles the full PR opening lifecycle:
        1. Transition to PR_OPENED state.
        2. Stage and commit all changes in the worktree.
        3. Push the branch to the remote.
        4. Delegate PR creation to pr_creator with all collected artifacts.
        5. Store pr_metadata.json artifact with URL and number.
        6. Update run record with pr_url.
        7. Transition to COMPLETED state.

        Args:
            run_id: ID of the current run.
            task_request: Original task request.
            worktree_path: Path to the worktree with changes.
            plan: The plan artifact for inclusion in PR body.
            review: The review verdict for inclusion in PR body.
            diff: The git diff of all changes.

        Returns:
            URL of the opened pull request.
        """
        import asyncio

        # 1. Transition to PR_OPENED
        await self._transition(
            run_id, RunState.REVIEWING, RunState.PR_OPENED, "Opening PR",
            metadata={"branch": task_request.base_branch},
        )

        # 2. Stage all changes
        proc = await asyncio.create_subprocess_exec(
            "git", "add", "-A",
            cwd=worktree_path,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        await proc.communicate()

        # 3. Commit
        commit_msg = f"[Foundry] {task_request.task_type.value}: {task_request.title}"
        proc = await asyncio.create_subprocess_exec(
            "git", "commit", "-m", commit_msg,
            cwd=worktree_path,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        await proc.communicate()

        # 4. Push branch
        run = await run_queries.get_run(self.session, run_id)
        branch_name = run.branch_name if run else "unknown"

        proc = await asyncio.create_subprocess_exec(
            "git", "push", "-u", "origin", branch_name,
            cwd=worktree_path,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await proc.communicate()
        if proc.returncode != 0:
            logger.warning("Git push stderr: %s", stderr.decode())

        # 5. Load verification results from stored artifact (if available)
        verification_results: list[dict] = []
        try:
            artifact_entries = await self.artifact_store.list_artifacts(run_id)
            for entry in artifact_entries:
                if "verification" in entry["filename"]:
                    storage_path = f"runs/{run_id}/{entry['filename']}"
                    raw = await self.artifact_store.retrieve(storage_path)
                    verification_results = json.loads(raw)
                    break
        except Exception:
            logger.debug("Could not load verification artifact for PR body")

        # 6. Create PR via pr_creator with all collected artifacts
        pr_result = await self.pr_creator.create_pr(
            task_request=task_request,
            plan=plan,
            diff=diff,
            verification_results=verification_results,
            review_verdict=review,
            run_id=run_id,
            branch_name=branch_name,
            base_branch=task_request.base_branch,
        )

        pr_url = pr_result["url"]
        pr_number = pr_result["number"]

        # 7. Store PR metadata artifact
        pr_title = f"[Foundry] {task_request.task_type.value}: {task_request.title}"
        pr_metadata = json.dumps({
            "url": pr_url,
            "number": pr_number,
            "branch": branch_name,
            "base": task_request.base_branch,
            "title": pr_title,
            "labels": ["foundry", "needs-human-review", task_request.task_type.value],
        }, indent=2)
        pr_result_meta = await self.artifact_store.store(
            run_id, ArtifactType.PR_METADATA, pr_metadata,
        )
        await artifact_queries.store_artifact(
            self.session, run_id, ArtifactType.PR_METADATA.value,
            pr_result_meta["storage_path"], pr_result_meta["size_bytes"],
            pr_result_meta["checksum"],
        )

        # 8. Log PR opened event
        await self._add_event(
            run_id, RunState.PR_OPENED,
            f"PR #{pr_number} opened",
            metadata={"url": pr_url, "number": pr_number, "artifact": "pr_metadata.json"},
        )

        # 9. Update run with PR URL
        if run:
            run.pr_url = pr_url
            await self.session.flush()

        # 10. Transition to COMPLETED
        await self._transition(
            run_id, RunState.PR_OPENED, RunState.COMPLETED,
            "Run completed successfully",
        )

        return pr_url
