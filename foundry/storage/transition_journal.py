"""Persist and reload outcomes independently from model or process memory."""

from __future__ import annotations

from uuid import UUID

from foundry.contracts.transition_models import TransitionOutcome
from foundry.storage.artifact_store import ArtifactStore, ArtifactType


class ArtifactStoreTransitionJournal:
    """Local atomic outcome storage; not a resumable execution scheduler."""

    def __init__(self, artifact_store: ArtifactStore) -> None:
        self.artifact_store = artifact_store

    async def record(self, outcome: TransitionOutcome) -> None:
        """Persist a decision, failure, or later cleanup warning under its ID."""
        await self.artifact_store.store(
            outcome.transition_id,
            ArtifactType.TRANSITION,
            outcome.model_dump_json(indent=2),
            filename="transition_outcome.json",
        )

    async def load(self, transition_id: UUID) -> TransitionOutcome:
        """Load and validate a persisted record after constructing a new journal."""
        data = await self.artifact_store.retrieve(
            f"runs/{transition_id}/transition_outcome.json"
        )
        outcome = TransitionOutcome.model_validate_json(data)
        if outcome.transition_id != transition_id:
            raise ValueError("Stored outcome has a different transition ID")
        return outcome
