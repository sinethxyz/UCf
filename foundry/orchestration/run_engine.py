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
from typing import TYPE_CHECKING, Any
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

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
    },
    RunState.PLANNING: {
        RunState.IMPLEMENTING,
        RunState.PLAN_FAILED,
        RunState.ERRORED,
    },
    RunState.IMPLEMENTING: {
        RunState.VERIFYING,
        RunState.ERRORED,
    },
    RunState.VERIFYING: {
        RunState.VERIFICATION_PASSED,
        RunState.VERIFICATION_FAILED,
        RunState.ERRORED,
    },
    RunState.VERIFICATION_PASSED: {
        RunState.REVIEWING,
        RunState.ERRORED,
    },
    RunState.REVIEWING: {
        RunState.PR_OPENED,
        RunState.REVIEW_FAILED,
        RunState.ERRORED,
    },
    RunState.PR_OPENED: {
        RunState.COMPLETED,
        RunState.ERRORED,
    },
    # Retry: failure states can go back to queued
    RunState.PLAN_FAILED: {
        RunState.QUEUED,
    },
    RunState.VERIFICATION_FAILED: {
        RunState.QUEUED,
    },
    RunState.REVIEW_FAILED: {
        RunState.QUEUED,
    },
    # Terminal states — no outgoing transitions
    RunState.COMPLETED: set(),
    RunState.CANCELLED: set(),
    RunState.ERRORED: set(),
}

# States that can be cancelled via cancel_run()
_CANCELLABLE_STATES: set[RunState] = {
    RunState.QUEUED,
    RunState.CREATING_WORKTREE,
    RunState.PLANNING,
    RunState.IMPLEMENTING,
    RunState.VERIFYING,
    RunState.VERIFICATION_PASSED,
    RunState.REVIEWING,
    RunState.PR_OPENED,
    RunState.PLAN_FAILED,
    RunState.VERIFICATION_FAILED,
    RunState.REVIEW_FAILED,
}


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
    ) -> None:
        self.session = session
        self.artifact_store = artifact_store
        self.worktree_manager = worktree_manager
        self.agent_runner = agent_runner
        self.pr_creator = pr_creator
        self.verification_runner = verification_runner

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def execute_run(self, task_request: TaskRequest) -> RunResponse:
        """Main entry point: execute a full run lifecycle for the given task.

        Creates a run record, drives it through all phases (worktree creation,
        planning, implementation, verification, review, PR creation), and
        returns the final run response.

        Args:
            task_request: The validated task request to execute.

        Returns:
            RunResponse with final state and metadata.
        """
        from foundry.contracts.shared import ReviewVerdictType
        from foundry.contracts.run_models import RunResponse

        # 1. Create run record in QUEUED state
        run = await run_queries.create_run(self.session, task_request)
        run_id = run.id
        logger.info("Created run %s for task: %s", run_id, task_request.title)

        # Add initial event
        event = RunEventORM(
            run_id=run_id,
            state=RunState.QUEUED.value,
            message=f"Run created for {task_request.task_type.value}: {task_request.title}",
        )
        await run_queries.add_run_event(self.session, event)

        try:
            # 2. Create worktree
            await self._transition(run_id, RunState.QUEUED, RunState.CREATING_WORKTREE, "Creating worktree")
            worktree_path = await self._create_worktree(run_id, task_request)
            await self._transition(run_id, RunState.CREATING_WORKTREE, RunState.PLANNING, "Worktree created")

            # 3. Run planning
            try:
                plan = await self._run_planning(run_id, task_request, worktree_path)
            except Exception as e:
                await self._transition(run_id, RunState.PLANNING, RunState.PLAN_FAILED, f"Planning failed: {e}")
                return RunResponse.model_validate(await run_queries.get_run(self.session, run_id))

            await self._transition(run_id, RunState.PLANNING, RunState.IMPLEMENTING, "Plan approved")

            # 4. Run implementation
            try:
                diff = await self._run_implementation(run_id, plan, task_request, worktree_path)
            except Exception as e:
                await self._transition(run_id, RunState.IMPLEMENTING, RunState.ERRORED, f"Implementation failed: {e}")
                return RunResponse.model_validate(await run_queries.get_run(self.session, run_id))

            # 5. Run verification (if required)
            await self._transition(run_id, RunState.IMPLEMENTING, RunState.VERIFYING, "Starting verification")
            verification_passed = await self._run_verification(run_id, worktree_path, task_request)

            if not verification_passed:
                await self._transition(run_id, RunState.VERIFYING, RunState.VERIFICATION_FAILED, "Verification failed")
                return RunResponse.model_validate(await run_queries.get_run(self.session, run_id))

            await self._transition(run_id, RunState.VERIFYING, RunState.VERIFICATION_PASSED, "All checks passed")

            # 6. Run review (blind — reviewer does not see the plan)
            await self._transition(run_id, RunState.VERIFICATION_PASSED, RunState.REVIEWING, "Starting review")
            review = await self._run_review(run_id, diff, task_request)

            # Check migration guard if needed
            guard_verdict = await self._check_migration_guard(run_id, diff)
            if guard_verdict and guard_verdict.verdict == ReviewVerdictType.REJECT:
                await self._transition(run_id, RunState.REVIEWING, RunState.REVIEW_FAILED, "Migration guard rejected")
                return RunResponse.model_validate(await run_queries.get_run(self.session, run_id))

            if review.verdict == ReviewVerdictType.REJECT:
                await self._transition(run_id, RunState.REVIEWING, RunState.REVIEW_FAILED, f"Review rejected: {review.summary}")
                return RunResponse.model_validate(await run_queries.get_run(self.session, run_id))

            # 7. Open PR
            await self._transition(run_id, RunState.REVIEWING, RunState.PR_OPENED, "Opening PR")
            pr_url = await self._open_pr(run_id, task_request, worktree_path, plan, review)

            # 8. Complete
            await self._transition(run_id, RunState.PR_OPENED, RunState.COMPLETED, f"PR opened: {pr_url}")

            return RunResponse.model_validate(await run_queries.get_run(self.session, run_id))

        except Exception as e:
            logger.exception("Run %s failed unexpectedly", run_id)
            try:
                # Try to transition to errored
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
                error_data = json.dumps({"error": str(e), "phase": "execute_run"})
                await self.artifact_store.store(run_id, ArtifactType.ERROR_LOG, error_data)
            except Exception:
                pass

            return RunResponse.model_validate(await run_queries.get_run(self.session, run_id))

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

        from foundry.contracts.run_models import RunResponse
        return RunResponse.model_validate(await run_queries.get_run(self.session, run_id))

    async def retry_run(self, run_id: UUID) -> RunResponse:
        """Retry a failed run by transitioning it back to QUEUED.

        Only runs in plan_failed, verification_failed, or review_failed
        states can be retried.

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
        retryable = {RunState.PLAN_FAILED, RunState.VERIFICATION_FAILED, RunState.REVIEW_FAILED}
        if current_state not in retryable:
            raise ValueError(
                f"Run {run_id} in state {current_state.value} is not retryable. "
                f"Only runs in {', '.join(s.value for s in retryable)} can be retried."
            )

        await self._transition(run_id, current_state, RunState.QUEUED, "Retrying run")

        from foundry.contracts.run_models import RunResponse
        return RunResponse.model_validate(await run_queries.get_run(self.session, run_id))

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

        Args:
            run_id: ID of the current run.
            task_request: Task request containing repo and branch info.

        Returns:
            Absolute path to the created worktree directory.
        """
        import re

        # Generate deterministic branch name
        slug = re.sub(r"[^a-z0-9]+", "-", task_request.title.lower().strip())
        slug = slug.strip("-")[:40].rstrip("-")
        task_type_slug = task_request.task_type.value.replace("_", "-")
        branch_name = f"foundry/{task_type_slug}-{slug}"

        worktree_path = await self.worktree_manager.create(
            repo=task_request.repo,
            branch_name=branch_name,
            run_id=run_id,
        )

        # Update run record with worktree info
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
    ) -> PlanArtifact:
        """Run the planner subagent to produce a structured implementation plan.

        Args:
            run_id: ID of the current run.
            task_request: Task request with prompt and context.
            worktree_path: Path to the worktree for repo exploration.

        Returns:
            PlanArtifact with ordered implementation steps.
        """
        try:
            plan = await self.agent_runner.run_planner(task_request, worktree_path)

            # Store plan artifact
            plan_json = plan.model_dump_json(indent=2)
            storage_path = await self.artifact_store.store(
                run_id, ArtifactType.PLAN, plan_json,
            )
            await artifact_queries.store_artifact(
                self.session, run_id, ArtifactType.PLAN.value,
                storage_path, len(plan_json.encode()),
                self.artifact_store.get_checksum(plan_json),
            )

            return plan
        except Exception as e:
            # Store error log
            error_data = json.dumps({"error": str(e), "phase": "planning"})
            storage_path = await self.artifact_store.store(
                run_id, ArtifactType.ERROR_LOG, error_data,
            )
            await artifact_queries.store_artifact(
                self.session, run_id, ArtifactType.ERROR_LOG.value,
                storage_path, len(error_data.encode()),
            )
            raise

    async def _run_implementation(
        self,
        run_id: UUID,
        plan: PlanArtifact,
        task_request: TaskRequest,
        worktree_path: str,
    ) -> str:
        """Run the implementer subagent to execute the plan.

        Selects the appropriate implementer (Go or TypeScript) based on
        the task request's target paths and language context.

        Args:
            run_id: ID of the current run.
            plan: The validated implementation plan.
            task_request: Original task request.
            worktree_path: Path to the worktree where edits are made.

        Returns:
            The git diff of all changes made.
        """
        # Set environment variables for hooks
        env_vars = {
            "RUN_ID": str(run_id),
            "RUN_STATE": RunState.IMPLEMENTING.value,
            "RUN_TASK_TYPE": task_request.task_type.value,
            "ARTIFACT_DIR": str(self.artifact_store.base_path / "runs" / str(run_id)),
            "WORKTREE_PATH": worktree_path,
        }
        old_env = {}
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

        Executes verification steps appropriate for the language and task type:
        Go (build, vet, test), TypeScript (tsc, eslint), JSON Schema validation.

        Args:
            run_id: ID of the current run.
            worktree_path: Path to the worktree to verify.
            task_request: Task request for context on what to verify.

        Returns:
            True if all verification steps pass, False otherwise.
        """
        import asyncio

        # Extract changed files from the worktree
        proc = await asyncio.create_subprocess_exec(
            "git", "diff", "--name-only", "HEAD",
            cwd=worktree_path,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, _ = await proc.communicate()
        changed_files = [f for f in stdout.decode().strip().split("\n") if f]

        # Also check untracked files
        proc2 = await asyncio.create_subprocess_exec(
            "git", "status", "--porcelain",
            cwd=worktree_path,
            stdout=asyncio.subprocess.PIPE,
        )
        stdout2, _ = await proc2.communicate()
        for line in stdout2.decode().strip().split("\n"):
            if line.startswith("?? "):
                changed_files.append(line[3:])

        results = await self.verification_runner.run_all(worktree_path, changed_files)

        # Store verification artifact
        verification_data = json.dumps(
            [{"check_type": r.check_type, "passed": r.passed, "output": r.output[:5000], "duration_ms": r.duration_ms} for r in results],
            indent=2,
        )
        storage_path = await self.artifact_store.store(
            run_id, ArtifactType.VERIFICATION, verification_data,
        )
        await artifact_queries.store_artifact(
            self.session, run_id, ArtifactType.VERIFICATION.value,
            storage_path, len(verification_data.encode()),
        )

        # Persist individual VerificationResult rows
        from foundry.db.models import VerificationResult as VRModel
        for r in results:
            vr = VRModel(
                run_id=run_id,
                check_type=r.check_type,
                passed=r.passed,
                output=r.output[:10000],
                duration_ms=r.duration_ms,
            )
            self.session.add(vr)
        await self.session.flush()

        return all(r.passed for r in results)

    async def _run_review(
        self,
        run_id: UUID,
        diff: str,
        task_request: TaskRequest,
    ) -> ReviewVerdict:
        """Run the reviewer subagent to independently review the diff.

        The reviewer does NOT see the plan — it judges the diff on its own
        merits to prevent confirmation bias.

        Args:
            run_id: ID of the current run.
            diff: The git diff to review.
            task_request: Task request for context (title, type).

        Returns:
            ReviewVerdict with verdict, issues, and summary.
        """
        from foundry.contracts.shared import ReviewVerdictType

        # Generate PR title/description for the reviewer
        task_type_slug = task_request.task_type.value.replace("_", " ")
        pr_title = f"[Foundry] {task_type_slug}: {task_request.title}"
        pr_description = task_request.prompt[:500]

        review = await self.agent_runner.run_reviewer(
            diff=diff,
            pr_title=pr_title,
            pr_description=pr_description,
        )

        # Store review artifact
        review_json = review.model_dump_json(indent=2)
        storage_path = await self.artifact_store.store(
            run_id, ArtifactType.REVIEW, review_json,
        )
        await artifact_queries.store_artifact(
            self.session, run_id, ArtifactType.REVIEW.value,
            storage_path, len(review_json.encode()),
            self.artifact_store.get_checksum(review_json),
        )

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
            r"^[ab]/migrations/",
            r"^[ab]/auth/",
            r"^[ab]/infra/",
            r"^[ab]/.*Dockerfile",
            r"^[ab]/.*docker-compose",
        ]
        touches_protected = any(
            re.search(pattern, line, re.MULTILINE)
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
    ) -> str:
        """Open a pull request with the changes from the worktree.

        Constructs the PR title, body (with plan, changes, verification,
        review artifacts), and labels per PR standards.

        Args:
            run_id: ID of the current run.
            task_request: Original task request.
            worktree_path: Path to the worktree with committed changes.
            plan: The plan artifact for inclusion in PR body.
            review: The review verdict for inclusion in PR body.

        Returns:
            URL of the opened pull request.
        """
        import asyncio

        # Commit all changes in the worktree
        proc = await asyncio.create_subprocess_exec(
            "git", "add", "-A",
            cwd=worktree_path,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        await proc.communicate()

        commit_msg = f"[Foundry] {task_request.task_type.value}: {task_request.title}"
        proc = await asyncio.create_subprocess_exec(
            "git", "commit", "-m", commit_msg,
            cwd=worktree_path,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        await proc.communicate()

        # Push branch
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

        # Build PR title and body
        task_type_display = task_request.task_type.value.replace("_", " ")
        pr_title = f"[Foundry] {task_request.task_type.value}: {task_request.title}"

        review_summary = review.summary if review else "No review"
        review_verdict = review.verdict.value if review else "N/A"

        pr_body = f"""\
## Summary
{task_request.prompt[:500]}

## Plan
Complexity: {plan.estimated_complexity.value}
Steps: {len(plan.steps)}
Risks: {', '.join(plan.risks) if plan.risks else 'None identified'}

## Changes
{chr(10).join(f'- `{step.file_path}`: {step.action} — {step.rationale}' for step in plan.steps)}

## Verification
- [x] Verification completed

## Review
Verdict: {review_verdict}
{review_summary}

## Run Metadata
- Run ID: {run_id}
- Task Type: {task_request.task_type.value}
"""

        # Determine repo target
        repo_slug = "sinethxyz/unicorn-app" if task_request.repo == "unicorn-app" else "sinethxyz/ucf"

        pr_result = await self.pr_creator.create_pr(
            repo=repo_slug,
            branch=branch_name,
            base_branch=task_request.base_branch,
            title=pr_title,
            body=pr_body,
            labels=[task_request.task_type.value.replace("_", "-")],
        )

        pr_url = pr_result["url"]

        # Store PR metadata artifact
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
            self.session, run_id, "pr_metadata",
            storage_path, len(pr_metadata.encode()),
        )

        # Update run with PR URL
        if run:
            run.pr_url = pr_url
            await self.session.flush()

        return pr_url
