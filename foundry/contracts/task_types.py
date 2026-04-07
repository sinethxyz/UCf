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


class PlanStep(FoundryBaseModel):
    """A single step in an implementation plan.

    Each step targets one file and describes the action to take,
    the rationale behind it, and any dependencies on other files
    that must be modified first.
    """

    file_path: str = Field(description="Path to the file to create, modify, or delete.")
    action: Literal["create", "modify", "delete"] = Field(
        description="The operation to perform on the file."
    )
    rationale: str = Field(description="Why this change is needed for the plan.")
    dependencies: list[str] = Field(
        default_factory=list,
        description="File paths that must be modified before this step.",
    )


class PlanArtifact(FoundryBaseModel):
    """Structured implementation plan produced by the planner subagent.

    Every non-trivial change starts with a planning pass that produces
    this artifact. No implementation begins without a stored plan.
    """

    task_id: UUID = Field(description="The task this plan was generated for.")
    steps: list[PlanStep] = Field(description="Ordered list of implementation steps.")
    risks: list[str] = Field(description="Identified risks that could affect implementation.")
    open_questions: list[str] = Field(
        description="Unresolved questions that may need human input."
    )
    estimated_complexity: Complexity | None = Field(
        default=None,
        description="Estimated complexity of the implementation.",
    )


class TaskRequest(FoundryBaseModel):
    """A task submitted to Foundry for execution.

    This is the primary input to the run engine. It specifies what to build,
    where to build it, what tools to use, and how to verify the result.
    """

    task_type: TaskType = Field(description="The type of task to execute.")
    repo: Literal["unicorn-app", "unicorn-foundry"] = Field(
        description="Target repository for the task."
    )
    base_branch: str = Field(
        default="main",
        description="Branch to create the worktree from.",
    )
    title: str = Field(description="Human-readable title for the task and resulting PR.")
    prompt: str = Field(description="Full natural-language specification of the task.")
    target_paths: list[str] = Field(
        default_factory=list,
        description="File or directory paths the task is expected to touch.",
    )
    allowed_tools: list[str] = Field(
        default_factory=lambda: ["Read", "Edit", "Write", "Bash", "Grep", "Glob"],
        description="Claude Code tools the agent is permitted to use.",
    )
    mcp_profile: MCPProfile = Field(
        default=MCPProfile.NONE,
        description="MCP server profile controlling external tool access.",
    )
    model_override: str | None = Field(
        default=None,
        description="Override the default model routing for this task.",
    )
    verify: bool = Field(
        default=True,
        description="Whether to run deterministic verification before PR.",
    )
    open_pr: bool = Field(
        default=True,
        description="Whether to open a PR after successful verification.",
    )
    priority: int = Field(
        default=0,
        description="Task priority. Higher values are processed first.",
    )
    metadata: dict = Field(
        default_factory=dict,
        description="Arbitrary metadata attached to the task request.",
    )
