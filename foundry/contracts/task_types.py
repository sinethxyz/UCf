"""Pydantic models for task requests and planning artifacts."""

from typing import Literal
from uuid import UUID

from pydantic import Field

from foundry.contracts.shared import (
    Complexity,
    FoundryBaseModel,
    MCPProfile,
    TaskType,
)


class TaskRequest(FoundryBaseModel):
    """A task submitted to Foundry for execution."""

    task_type: TaskType
    repo: Literal["unicorn-app", "unicorn-foundry"]
    base_branch: str = "main"
    title: str
    prompt: str
    target_paths: list[str] = Field(default_factory=list)
    allowed_tools: list[str] = Field(
        default_factory=lambda: ["Read", "Edit", "Write", "Bash", "Grep", "Glob"]
    )
    mcp_profile: MCPProfile = MCPProfile.NONE
    model_override: str | None = None
    verify: bool = True
    open_pr: bool = True
    priority: int = 0
    metadata: dict = Field(default_factory=dict)


class PlanStep(FoundryBaseModel):
    """A single step in an implementation plan."""

    file_path: str
    action: Literal["create", "modify", "delete"]
    rationale: str
    dependencies: list[str] = Field(default_factory=list)


class PlanArtifact(FoundryBaseModel):
    """Structured implementation plan produced by the planner subagent."""

    task_id: UUID
    steps: list[PlanStep]
    risks: list[str]
    open_questions: list[str]
    estimated_complexity: Complexity
