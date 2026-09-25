"""Capability interfaces for the provider-neutral UCF transition loop."""

from __future__ import annotations

from typing import Protocol

from foundry.contracts.transition_models import (
    ActionProposal,
    EvidenceRef,
    StateSnapshot,
    TransitionRequest,
    VerificationDecision,
)


class StateObserver(Protocol):
    """Observe an environment and return explicit state."""

    async def observe(self, request: TransitionRequest, workspace: str) -> StateSnapshot:
        ...


class TransitionPlanner(Protocol):
    """Propose an action from objective plus current state."""

    async def plan(
        self,
        request: TransitionRequest,
        current_state: StateSnapshot,
        workspace: str,
    ) -> ActionProposal:
        ...


class ActionExecutor(Protocol):
    """Apply an action proposal inside an execution environment."""

    async def execute(
        self,
        request: TransitionRequest,
        action: ActionProposal,
        workspace: str,
    ) -> list[EvidenceRef]:
        ...


class TransitionVerifier(Protocol):
    """Judge the observed consequence independently from action generation."""

    async def verify(
        self,
        request: TransitionRequest,
        before: StateSnapshot,
        after: StateSnapshot,
        action: ActionProposal,
        action_evidence: list[EvidenceRef],
    ) -> VerificationDecision:
        ...
