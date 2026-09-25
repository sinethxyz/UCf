"""Evidence-preserving transition execution, not automatic crash recovery.

Outcomes describe observed work, not publication or deployment. Processing and
journal failures retain the workspace; a failed operation never becomes accepted.
"""

from __future__ import annotations

import asyncio
import logging

from foundry.contracts.transition_models import (
    ActionProposal,
    EvidenceRef,
    StateSnapshot,
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

logger = logging.getLogger(__name__)


class StateConflictError(ValueError):
    """Observed state does not match the transition's environment or precondition."""


def _validate_snapshot(snapshot: StateSnapshot, request: TransitionRequest) -> None:
    if snapshot.environment != request.environment:
        raise StateConflictError("Observation belongs to a different environment")


class TransitionEngine:
    """Execute, observe, verify and journal; preserve evidence on failure.

    Adapters are trusted capabilities, not a security sandbox. A supplied
    before_state is a precondition to compare with a fresh observation, not a
    replacement for observation. State equality is adapter-defined via `state`.
    """

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
        """Return a journaled decision, or re-raise a recorded processing failure.

        No automatic retry is attempted. A retained workspace needs explicit
        inspection and cleanup. Persistence failures are surfaced to the caller.
        """
        phase = "prepare"
        workspace: str | None = None
        before: StateSnapshot | None = None
        after: StateSnapshot | None = None
        action: ActionProposal | None = None
        evidence: list[EvidenceRef] = []
        try:
            workspace = await self.environment.prepare(
                target=request.environment,
                base_ref=str(request.metadata.get("base_ref", "current")),
                transition_id=request.id,
                transition_name=str(request.metadata.get("transition_name", request.id)),
            )
            phase = "observe_before"
            before = (await self.observer.observe(request, workspace)).model_copy(deep=True)
            _validate_snapshot(before, request)
            if request.before_state is not None:
                _validate_snapshot(request.before_state, request)
                if request.before_state.state != before.state:
                    raise StateConflictError("Supplied before_state is stale")

            phase = "plan"
            action = await self.planner.plan(request, before.model_copy(deep=True), workspace)
            phase = "execute"
            evidence = await self.executor.execute(request, action, workspace)
            phase = "observe_after"
            after = (await self.observer.observe(request, workspace)).model_copy(deep=True)
            _validate_snapshot(after, request)
            phase = "verify"
            decision = await self.verifier.verify(
                request=request,
                before=before.model_copy(deep=True),
                after=after.model_copy(deep=True),
                action=action.model_copy(deep=True),
                action_evidence=[item.model_copy(deep=True) for item in evidence],
                workspace=workspace,
            )
            phase = "observe_verified"
            verified = await self.observer.observe(request, workspace)
            _validate_snapshot(verified, request)
            if verified.state != after.state:
                after = verified.model_copy(deep=True)
                raise StateConflictError("Environment changed during verification")
        except (Exception, asyncio.CancelledError) as error:
            # Failure is not a verification rejection. Do not erase partial work.
            failed = TransitionOutcome(
                transition_id=request.id,
                accepted=False,
                before_state=before,
                after_state=after,
                observation=(
                    TransitionObservation(
                        transition_id=request.id,
                        observed_state=after,
                        action_evidence=evidence,
                    )
                    if after is not None else None
                ),
                reason=f"Transition failed during {phase}",
                metadata={
                    "status": (
                        "cancelled" if isinstance(error, asyncio.CancelledError) else "failed"
                    ),
                    "phase": phase,
                    "error_type": type(error).__name__,
                    "environment": request.environment,
                    "retained_workspace": workspace,
                },
            )
            try:
                await self.journal.record(failed)
            except Exception as journal_error:
                # Keep the original exception and make the missing record explicit.
                error.add_note(f"Failure journal also failed: {type(journal_error).__name__}")
                logger.error("Failure journal unavailable for transition %s", request.id)
            error.add_note(f"UCF retained workspace: {workspace!r}; no automatic retry")
            raise

        outcome = TransitionOutcome(
            transition_id=request.id,
            accepted=decision.accepted,
            before_state=before,
            after_state=after,
            observation=TransitionObservation(
                transition_id=request.id,
                observed_state=after,
                action_evidence=evidence,
                verification_evidence=decision.evidence,
            ),
            reason=decision.reason,
            metadata={
                "status": "accepted" if decision.accepted else "rejected",
                "action_kind": action.kind,
            },
        )
        # A successful call to record is required BEFORE destructive cleanup.
        try:
            await self.journal.record(outcome)
        except Exception as error:
            error.add_note(f"Outcome not confirmed durable; retained workspace: {workspace!r}")
            raise
        try:
            await self.environment.cleanup(workspace)
        except (Exception, asyncio.CancelledError) as error:
            outcome.metadata.update({
                "cleanup_status": "failed",
                "cleanup_error_type": type(error).__name__,
                "retained_workspace": workspace,
            })
            # Persist the resource warning without changing the verification decision.
            await self.journal.record(outcome)
            if isinstance(error, asyncio.CancelledError):
                raise
            logger.warning("Cleanup failed for transition %s", request.id)
        return outcome
