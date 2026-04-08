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
from typing import TYPE_CHECKING
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

import redis.asyncio as aioredis

from foundry.contracts.review_models import ReviewVerdict
from foundry.contracts.run_models import RunResponse
from foundry.contracts.shared import RunState
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
        import traceback

        from foundry.contracts.shared import ReviewVerdictType

        # 1. Create run record in QUEUED state
        run = await run_queries.create_run(self.session, task_request)
        run_id = run.id
        worktree_path: str | None = None
        logger.info("Created run %s for task: %s", run_id, task_request.title)

        # Add initial event
        event = RunEventORM(
            run_id=run_id,
            state=RunState.QUEUED.value,
            message=f"Run created for {task_request.task_type.value}: {task_request.title}",
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

            # 6. Run review (blind — reviewer does not see the plan)
            # _run_review handles VERIFICATION_PASSED → REVIEWING transition,
            # artifact storage, run events, and REJECT → REVIEW_FAILED internally.
            review = await self._run_review(run_id, diff, task_request)

            if review.verdict == ReviewVerdictType.REJECT:
                # _run_review already transitioned to REVIEW_FAILED and set error_message
                return await _build_run_response(self.session, run_id)

            # Check migration guard if needed (only if review didn't reject)
            guard_verdict = await self._check_migration_guard(run_id, diff)
            if guard_verdict and guard_verdict.verdict == ReviewVerdictType.REJECT:
                await self._transition(run_id, RunState.REVIEWING, RunState.REVIEW_FAILED, "Migration guard rejected")
                return await _build_run_response(self.session, run_id)

            # 7. Open PR (handles REVIEWING → PR_OPENED → COMPLETED transitions)
            await self._open_pr(run_id, task_request, worktree_path, plan, review, diff)

            return await _build_run_response(self.session, run_id)

        except Exception as e:
            logger.exception("Run %s failed unexpectedly: %s", run_id, traceback.format_exc())
            try:
                run = await run_queries.get_run(self.session, run_id)
                if run and run.state not in ("completed", "cancelled", "errored"):
                    current_state = RunState(run.state)
                    if RunState.ERRORED in VALID_TRANSITIONS.get(current_state, set()):
                        await self._transition(run_id, current_state, RunState.ERRORED, f"Unexpected error: {e}")
                    else:
                        await run_queries.update_run_state(
                            self.session, run_id, RunState.ERRORED.value, str(e),
                        )
            except Exception:
                logger.exception("Failed to transition run %s to errored state", run_id)

            # Store error artifact
            try:
                error_data = json.dumps({
                    "error": str(e),
                    "traceback": traceback.format_exc(),
                    "phase": "execute_run",
                })
                await self.artifact_store.store(run_id, ArtifactType.ERROR_LOG, error_data)
            except Exception:
                pass

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

        await self._transition(run_id, current_state, RunState.CANCELLED, "Cancelled by user")

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

        await self._transition(run_id, current_state, RunState.QUEUED, "Retrying run")

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
    ) -> None:
        """Validate and execute a state transition.

        Checks that the transition is allowed by VALID_TRANSITIONS, updates
        the run record in the database, and emits a RunEvent.

        Args:
            run_id: ID of the run being transitioned.
            from_state: The current state (must match DB).
            to_state: The target state.
            message: Human-readable message for the RunEvent.

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
        )
        await run_queries.add_run_event(self.session, event)
        logger.info("Run %s: %s -> %s (%s)", run_id, from_state.value, to_state.value, message)

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
        worktree_path = await self.worktree_manager.create(
            repo=task_request.repo,
            branch_name=branch_name,
            run_id=run_id,
        )

        # 4. Update run record with worktree info
        run = await run_queries.get_run(self.session, run_id)
        if run is not None:
            run.worktree_path = worktree_path
            run.branch_name = branch_name
            await self.session.flush()

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
        # Transition to PLANNING
        await self._transition(
            run_id, RunState.CREATING_WORKTREE, RunState.PLANNING, "Starting planning",
        )

        try:
            plan = await self.agent_runner.run_planner(task_request, worktree_path)

            # Serialize plan to JSON, store as plan.json
            plan_json = plan.model_dump_json(indent=2)
            storage_path = await self.artifact_store.store(
                run_id, ArtifactType.PLAN, plan_json, filename="plan.json",
            )
            await artifact_queries.store_artifact(
                self.session, run_id, ArtifactType.PLAN.value,
                storage_path, len(plan_json.encode()),
                self.artifact_store.get_checksum(plan_json),
            )

            return plan
        except Exception as e:
            logger.error("Planning failed for run %s: %s", run_id, e)

            # Store error_log artifact
            error_data = json.dumps({"error": str(e), "phase": "planning"})
            try:
                storage_path = await self.artifact_store.store(
                    run_id, ArtifactType.ERROR_LOG, error_data,
                )
                await artifact_queries.store_artifact(
                    self.session, run_id, ArtifactType.ERROR_LOG.value,
                    storage_path, len(error_data.encode()),
                )
            except Exception:
                logger.exception("Failed to store error log for run %s", run_id)

            # Transition to PLAN_FAILED
            await self._transition(
                run_id, RunState.PLANNING, RunState.PLAN_FAILED,
                f"Planning failed: {e}",
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
        # Transition to IMPLEMENTING
        await self._transition(
            run_id, RunState.PLANNING, RunState.IMPLEMENTING, "Starting implementation",
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
            # Determine language from target paths (Go-only for Phase 1)
            language = "go"

            diff = await self.agent_runner.run_implementer(
                plan=plan,
                task_request=task_request,
                worktree_path=worktree_path,
                language=language,
            )

            # Store diff artifact
            if diff.strip():
                storage_path = await self.artifact_store.store(
                    run_id, ArtifactType.DIFF, diff,
                )
                await artifact_queries.store_artifact(
                    self.session, run_id, ArtifactType.DIFF.value,
                    storage_path, len(diff.encode()),
                    self.artifact_store.get_checksum(diff),
                )

            return diff

        except Exception as e:
            logger.error("Implementation failed for run %s: %s", run_id, e)

            # Store error_log artifact
            error_data = json.dumps({"error": str(e), "phase": "implementation"})
            try:
                storage_path = await self.artifact_store.store(
                    run_id, ArtifactType.ERROR_LOG, error_data,
                )
                await artifact_queries.store_artifact(
                    self.session, run_id, ArtifactType.ERROR_LOG.value,
                    storage_path, len(error_data.encode()),
                )
            except Exception:
                logger.exception("Failed to store error log for run %s", run_id)

            # Transition to ERRORED
            await self._transition(
                run_id, RunState.IMPLEMENTING, RunState.ERRORED,
                f"Implementation failed: {e}",
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

        # 1. Transition to VERIFYING
        await self._transition(
            run_id, RunState.IMPLEMENTING, RunState.VERIFYING,
            "Starting verification",
        )

        # 2. Extract changed files from stored diff artifact
        changed_files: list[str] = []
        try:
            artifact_paths = await self.artifact_store.list_artifacts(run_id)
            for path in artifact_paths:
                if "diff" in path:
                    raw = await self.artifact_store.retrieve(path)
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

        # 4. Serialize and store verification.json artifact
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
        storage_path = await self.artifact_store.store(
            run_id, ArtifactType.VERIFICATION, verification_data,
            filename="verification.json",
        )
        checksum = self.artifact_store.get_checksum(verification_data)
        await artifact_queries.store_artifact(
            self.session, run_id, ArtifactType.VERIFICATION.value,
            storage_path, len(verification_data.encode()), checksum,
        )

        # 5. Handle pass/fail with state transitions and run events
        if not passed:
            failed_checks = [r.check_type for r in results if not r.passed]
            error_summary = (
                f"Verification failed: {', '.join(failed_checks)} did not pass"
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

        # All checks passed
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
        """Run the reviewer subagent to independently review the diff.

        The reviewer does NOT see the plan — it judges the diff on its own
        merits to prevent confirmation bias.

        Handles the full review lifecycle:
        1. Transition to REVIEWING state.
        2. Generate PR title and description for reviewer context.
        3. Extract changed files from the diff.
        4. Call agent_runner.run_reviewer() with diff, title, description, changed_files.
        5. Serialize ReviewVerdict to JSON and store as review.json artifact.
        6. Register artifact in DB with size and checksum.
        7. Add run event with review summary (verdict, issue count, confidence).
        8. If REJECT: transition to REVIEW_FAILED, attach rejection summary to error_message.
        9. If REQUEST_CHANGES: add event noting advisory changes will be in PR.

        Args:
            run_id: ID of the current run.
            diff: The git diff to review.
            task_request: Task request for context (title, type).

        Returns:
            ReviewVerdict with verdict, issues, and summary.
        """
        from foundry.contracts.shared import ReviewVerdictType

        # 1. Transition to REVIEWING
        await self._transition(
            run_id, RunState.VERIFICATION_PASSED, RunState.REVIEWING,
            "Starting blind review",
        )

        # 2. Generate PR title and description
        pr_title = f"[Foundry] {task_request.task_type.value}: {task_request.title}"

        changed_files = _extract_changed_files(diff)
        changes_summary = ", ".join(changed_files[:10]) if changed_files else "no files detected"
        if len(changed_files) > 10:
            changes_summary += f" (+{len(changed_files) - 10} more)"
        pr_description = (
            f"{task_request.prompt[:500]}\n\n"
            f"Changed files: {changes_summary}"
        )

        # 3. Call reviewer (blind — no plan)
        review = await self.agent_runner.run_reviewer(
            diff=diff,
            pr_title=pr_title,
            pr_description=pr_description,
            changed_files=changed_files,
        )

        # 4. Serialize and store review.json artifact
        review_json = review.model_dump_json(indent=2)
        storage_path = await self.artifact_store.store(
            run_id, ArtifactType.REVIEW, review_json,
            filename="review.json",
        )
        await artifact_queries.store_artifact(
            self.session, run_id, ArtifactType.REVIEW.value,
            storage_path, len(review_json.encode()),
            self.artifact_store.get_checksum(review_json),
        )

        # 5. Add run event with review summary
        issue_count = len(review.issues)
        review_event = RunEventORM(
            run_id=run_id,
            state=RunState.REVIEWING.value,
            message=(
                f"Review complete — verdict: {review.verdict.value}, "
                f"issues: {issue_count}, confidence: {review.confidence:.2f}"
            ),
        )
        await run_queries.add_run_event(self.session, review_event)

        # 6. Handle verdict
        if review.verdict == ReviewVerdictType.REJECT:
            run = await run_queries.get_run(self.session, run_id)
            if run is not None:
                run.error_message = f"Review rejected: {review.summary}"
                await self.session.flush()

            await self._transition(
                run_id, RunState.REVIEWING, RunState.REVIEW_FAILED,
                f"Review rejected: {review.summary}",
            )

        elif review.verdict == ReviewVerdictType.REQUEST_CHANGES:
            advisory_event = RunEventORM(
                run_id=run_id,
                state=RunState.REVIEWING.value,
                message=(
                    f"Review requested changes ({issue_count} issues). "
                    f"PR will include requested changes as comments."
                ),
            )
            await run_queries.add_run_event(self.session, advisory_event)

        return review

    async def _check_migration_guard(
        self,
        run_id: UUID,
        diff: str,
    ) -> ReviewVerdict | None:
        """Check if the diff touches protected paths and run migration guard.

        Automatically invoked if any changed file matches: migrations/, auth/,
        infra/, *.env*, docker-compose*, Dockerfile*.

        Args:
            run_id: ID of the current run.
            diff: The git diff to check.

        Returns:
            ReviewVerdict if migration guard was triggered, None otherwise.
        """
        import re
        from foundry.contracts.shared import ReviewVerdictType

        # Check if diff touches protected paths
        protected_patterns = [
            r"[ab]/migrations/",
            r"[ab]/auth/",
            r"[ab]/infra/",
            r"[ab]/.*Dockerfile",
            r"[ab]/.*docker-compose",
        ]
        touches_protected = any(
            re.search(pattern, line)
            for pattern in protected_patterns
            for line in diff.split("\n")
            if line.startswith("diff --git") or line.startswith("---") or line.startswith("+++")
        )

        if not touches_protected:
            return None

        logger.warning("Run %s touches protected paths — invoking migration guard", run_id)
        guard_verdict = await self.agent_runner.run_migration_guard(diff)
        return guard_verdict

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
            artifact_paths = await self.artifact_store.list_artifacts(run_id)
            for path in artifact_paths:
                if "verification" in path:
                    raw = await self.artifact_store.retrieve(path)
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

        # 7. Store PR metadata artifact
        pr_title = f"[Foundry] {task_request.task_type.value}: {task_request.title}"
        pr_metadata = json.dumps({
            "url": pr_url,
            "number": pr_result["number"],
            "branch": branch_name,
            "base": task_request.base_branch,
            "title": pr_title,
        }, indent=2)
        storage_path = await self.artifact_store.store(
            run_id, ArtifactType.PR_METADATA, pr_metadata,
        )
        await artifact_queries.store_artifact(
            self.session, run_id, ArtifactType.PR_METADATA.value,
            storage_path, len(pr_metadata.encode()),
        )

        # 8. Update run with PR URL
        if run:
            run.pr_url = pr_url
            await self.session.flush()

        # 9. Transition to COMPLETED
        await self._transition(
            run_id, RunState.PR_OPENED, RunState.COMPLETED,
            f"PR opened: {pr_url}",
        )

        return pr_url
