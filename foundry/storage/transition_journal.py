"""Transition journal backed by the existing Foundry artifact store."""

from __future__ import annotations

from foundry.contracts.transition_models import TransitionOutcome
from foundry.storage.artifact_store import ArtifactStore, ArtifactType


class ArtifactStoreTransitionJournal:
    """Persist verified UCF outcomes using Foundry's durable artifact storage."""

    def __init__(self, artifact_store: ArtifactStore) -> None:
        self.artifact_store = artifact_store

    async def record(self, outcome: TransitionOutcome) -> None:
        await self.artifact_store.store(
            outcome.transition_id,
            ArtifactType.TRANSITION,
            outcome.model_dump_json(indent=2),
            filename="transition_outcome.json",
        )
