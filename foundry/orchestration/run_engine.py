"""Core run lifecycle state machine.

Manages transitions: queued -> creating_worktree -> planning -> implementing
-> verifying -> reviewing -> pr_opened -> completed.

Terminal failure states: plan_failed, verification_failed, review_failed,
cancelled, errored.
"""

from uuid import UUID

from foundry.contracts.shared import RunState


# Valid state transitions
TRANSITIONS: dict[RunState, list[RunState]] = {
    RunState.QUEUED: [RunState.CREATING_WORKTREE, RunState.CANCELLED, RunState.ERRORED],
    RunState.CREATING_WORKTREE: [RunState.PLANNING, RunState.ERRORED],
    RunState.PLANNING: [RunState.IMPLEMENTING, RunState.PLAN_FAILED, RunState.ERRORED],
    RunState.IMPLEMENTING: [RunState.VERIFYING, RunState.ERRORED],
    RunState.VERIFYING: [
        RunState.VERIFICATION_PASSED,
        RunState.VERIFICATION_FAILED,
        RunState.ERRORED,
    ],
    RunState.VERIFICATION_PASSED: [RunState.REVIEWING, RunState.ERRORED],
    RunState.REVIEWING: [RunState.PR_OPENED, RunState.REVIEW_FAILED, RunState.ERRORED],
    RunState.PR_OPENED: [RunState.COMPLETED, RunState.ERRORED],
}


class RunEngine:
    """Manages the lifecycle of a single Foundry run."""

    def __init__(self, run_id: UUID) -> None:
        self.run_id = run_id
        self.state = RunState.QUEUED

    def can_transition(self, target: RunState) -> bool:
        """Check if a transition to the target state is valid."""
        allowed = TRANSITIONS.get(self.state, [])
        return target in allowed

    async def transition(self, target: RunState, message: str = "") -> None:
        """Transition the run to a new state.

        Args:
            target: The target state.
            message: Human-readable message for the transition event.

        Raises:
            ValueError: If the transition is not valid from the current state.
        """
        if not self.can_transition(target):
            raise ValueError(
                f"Invalid transition: {self.state.value} -> {target.value}"
            )
        self.state = target

    async def execute(self) -> None:
        """Execute the full run lifecycle.

        Drives the run through all phases: worktree creation, planning,
        implementation, verification, review, and PR creation.
        """
        raise NotImplementedError("Run execution not yet implemented")
