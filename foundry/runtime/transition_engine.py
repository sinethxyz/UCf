"""Minimal provider-neutral state transition engine.

This runs alongside the historical Foundry RunEngine. It exists to prove the
general UCF loop before legacy Git/PR terminology is migrated.
"""

from __future__ import annotations

from foundry.contracts.transition_models import (
    TransitionObservation,
    TransitionOutcome,
    TransitionRequest,
)
from foundry.environments.base import ExecutionEnvironment
from foundry.runtime.interfaces import (
    ActionExecutor,
    StateObserver,
    TransitionJournal,
    TransitionPlanner,
    TransitionVerifier,
)


class TransitionEngine:
    """Coordinate one explicit state transition from observation to outcome."""

    def __init__(
        self,
        environment: ExecutionEnvironment,
        observer: StateObserver,
        planner: TransitionPlanner,
        executor: ActionExecutor,
        verifier: TransitionVerifier,
        journal: TransitionJournal,
    ) -> None:
        self.environment = environment
        self.observer = observer
        self.planner = planner
        self.executor = executor
        self.verifier = verifier
        self.journal = journal

    async def execute(self, request: TransitionRequest) -> TransitionOutcome:
        workspace = await self.environment.prepare(
            target=request.environment,
            base_ref=str(request.metadata.get("base_ref", "current")),
            transition_id=request.id,
            transition_name=str(request.metadata.get("transition_name", request.id)),
        )

        try:
            before = request.before_state
            if before is None:
                before = await self.observer.observe(request, workspace)

            action = await self.planner.plan(request, before, workspace)
            action_evidence = await self.executor.execute(request, action, workspace)
            after = await self.observer.observe(request, workspace)

            decision = await self.verifier.verify(
                request=request,
                before=before,
                after=after,
                action=action,
                action_evidence=action_evidence,
            )

            observation = TransitionObservation(
                transition_id=request.id,
                observed_state=after,
                action_evidence=action_evidence,
                verification_evidence=decision.evidence,
            )
            outcome = TransitionOutcome(
                transition_id=request.id,
                accepted=decision.accepted,
                before_state=before,
                after_state=after,
                observation=observation,
                reason=decision.reason,
                metadata={"action_kind": action.kind},
            )
            await self.journal.record(outcome)
            return outcome
        finally:
            await self.environment.cleanup(workspace)
