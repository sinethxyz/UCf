"""Pydantic models for run lifecycle: events, artifacts, and responses."""

from datetime import datetime
from uuid import UUID

from pydantic import Field

from foundry.contracts.shared import FoundryBaseModel, RunState


class RunEvent(FoundryBaseModel):
    """An event emitted during a run's state transitions."""

    run_id: UUID
    timestamp: datetime
    state: RunState
    message: str
    artifact_ids: list[UUID] = Field(default_factory=list)
    metadata: dict = Field(default_factory=dict)
    duration_ms: int | None = None
    model_used: str | None = None
    tokens_in: int | None = None
    tokens_out: int | None = None


class RunArtifact(FoundryBaseModel):
    """Metadata for a stored run artifact."""

    id: UUID
    run_id: UUID
    artifact_type: str
    storage_path: str
    size_bytes: int | None = None
    checksum: str | None = None
    created_at: datetime


class RunResponse(FoundryBaseModel):
    """API response model for a run."""

    id: UUID
    task_type: str
    repo: str
    base_branch: str
    title: str
    state: RunState
    branch_name: str | None = None
    pr_url: str | None = None
    error_message: str | None = None
    created_at: datetime
    updated_at: datetime
    completed_at: datetime | None = None
    metadata: dict = Field(default_factory=dict)
