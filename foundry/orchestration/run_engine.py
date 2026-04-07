"""Core run lifecycle state machine.

Manages transitions: queued -> creating_worktree -> planning -> implementing
-> verifying -> verification_passed -> reviewing -> pr_opened -> completed.

Terminal failure states: plan_failed, verification_failed, review_failed,
cancelled, errored.
"""

from __future__ import annotations

import logging
from typing import Any
from uuid import UUID

from foundry.contracts.review_models import ReviewVerdict
from foundry.contracts.run_models import RunResponse
from foundry.contracts.shared import RunState
from foundry.contracts.task_types import PlanArtifact, TaskRequest

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

    def __init__(self) -> None:
        pass

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
        raise NotImplementedError("Run execution not yet implemented")

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
        raise NotImplementedError("Run cancellation not yet implemented")

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
        raise NotImplementedError("Run retry not yet implemented")

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
        raise NotImplementedError("State transition not yet implemented")

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
        raise NotImplementedError("Worktree creation not yet implemented")

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
        raise NotImplementedError("Planning phase not yet implemented")

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
        raise NotImplementedError("Implementation phase not yet implemented")

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
        raise NotImplementedError("Verification phase not yet implemented")

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
        raise NotImplementedError("Review phase not yet implemented")

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
        raise NotImplementedError("Migration guard not yet implemented")

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
        raise NotImplementedError("PR creation not yet implemented")
