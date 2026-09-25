"""Provider-neutral contracts for stateful UCF transitions.

These models describe the conceptual boundary of UCF without assuming Git,
source code, pull requests, or a particular intelligence provider.
"""

from __future__ import annotations

from datetime import datetime
from uuid import UUID, uuid4

from pydantic import Field

from foundry.contracts.shared import FoundryBaseModel


class EvidenceRef(FoundryBaseModel):
    """Reference to evidence supporting a state or transition claim."""

    kind: str
    uri: str
    description: str | None = None
    checksum: str | None = None


class StateSnapshot(FoundryBaseModel):
    """Explicit representation of an environment at a point in time."""

    id: UUID = Field(default_factory=uuid4)
    environment: str
    observed_at: datetime
    state: dict
    evidence: list[EvidenceRef] = Field(default_factory=list)


class TransitionRequest(FoundryBaseModel):
    """Request to move an environment from a known state toward an objective."""

    id: UUID = Field(default_factory=uuid4)
    environment: str
    objective: str
    before_state: StateSnapshot | None = None
    constraints: dict = Field(default_factory=dict)
    metadata: dict = Field(default_factory=dict)


class TransitionObservation(FoundryBaseModel):
    """Observed consequence of an attempted transition."""

    transition_id: UUID
    observed_state: StateSnapshot
    action_evidence: list[EvidenceRef] = Field(default_factory=list)
    verification_evidence: list[EvidenceRef] = Field(default_factory=list)


class TransitionOutcome(FoundryBaseModel):
    """Durable result of a transition after verification/evaluation."""

    transition_id: UUID
    accepted: bool
    before_state: StateSnapshot | None = None
    after_state: StateSnapshot | None = None
    observation: TransitionObservation | None = None
    reason: str | None = None
    metadata: dict = Field(default_factory=dict)
