"""Pydantic models for run lifecycle: events, artifacts, and responses."""

from datetime import datetime
from uuid import UUID

from pydantic import Field

from foundry.contracts.shared import (
    ArtifactType,
    FoundryBaseModel,
    RunState,
    TaskType,
)


class RunEvent(FoundryBaseModel):
    """An event emitted during a run's state transitions.

    Every state change, subagent invocation, and significant action
    produces a RunEvent for observability and debugging.
    """

    run_id: UUID = Field(description="The run that emitted this event.")
    timestamp: datetime = Field(description="When this event occurred.")
    state: RunState = Field(description="The run state at the time of this event.")
    message: str = Field(description="Human-readable description of what happened.")
    artifact_ids: list[UUID] = Field(
        default_factory=list,
        description="Artifacts produced during this state transition.",
    )
    metadata: dict = Field(
        default_factory=dict,
        description="Additional structured data about the event.",
    )
    duration_ms: int | None = Field(
        default=None,
        description="Time spent in this state, in milliseconds.",
    )
    model_used: str | None = Field(
        default=None,
        description="Claude model used during this state, if any.",
    )
    tokens_in: int | None = Field(
        default=None,
        description="Input tokens consumed during this state.",
    )
    tokens_out: int | None = Field(
        default=None,
        description="Output tokens generated during this state.",
    )


class RunArtifact(FoundryBaseModel):
    """Metadata for a stored run artifact.

    Artifacts are the durable outputs of a run: plans, diffs, patches,
    verification results, reviews, and logs. Every artifact is stored
    and tracked for auditability.
    """

    id: UUID = Field(description="Unique identifier for this artifact.")
    run_id: UUID = Field(description="The run that produced this artifact.")
    artifact_type: ArtifactType = Field(description="Classification of this artifact.")
    storage_path: str = Field(description="Path to the artifact in object storage.")
    size_bytes: int | None = Field(
        default=None,
        description="Size of the artifact in bytes.",
    )
    checksum: str | None = Field(
        default=None,
        description="SHA-256 checksum of the artifact contents.",
    )
    created_at: datetime = Field(description="When this artifact was stored.")


class RunResponse(FoundryBaseModel):
    """API response model for a run.

    Returned by GET /v1/runs/{id} and POST /v1/runs. Contains the
    current state and metadata of a run without its full event history.
    """

    id: UUID = Field(description="Unique identifier for this run.")
    task_type: TaskType = Field(description="The type of task being executed.")
    repo: str = Field(description="Target repository for this run.")
    state: RunState = Field(description="Current lifecycle state of the run.")
    title: str = Field(description="Human-readable title of the run.")
    branch_name: str | None = Field(
        default=None,
        description="Git branch name for the worktree, if created.",
    )
    pr_url: str | None = Field(
        default=None,
        description="URL of the opened PR, if any.",
    )
    error_message: str | None = Field(
        default=None,
        description="Error message if the run failed.",
    )
    created_at: datetime = Field(description="When this run was created.")
    updated_at: datetime = Field(description="When this run was last updated.")
    completed_at: datetime | None = Field(
        default=None,
        description="When this run reached a terminal state.",
    )
